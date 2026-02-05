"""
FastAPI wrapper service for CasePeer API with automated authentication via Playwright.

This service provides a proxy endpoint for fetching case documents from CasePeer,
handling authentication automatically when needed.
"""

import logging
import asyncio
import imaplib
import email
import re
import time
import os
import json
from typing import Optional, Dict, Any
from contextlib import asynccontextmanager
from urllib.parse import urlparse
from fastapi import FastAPI, HTTPException, Request, UploadFile, Form, Depends
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from playwright.sync_api import sync_playwright, Browser, Page
import requests
from bs4 import BeautifulSoup
from sqlalchemy.orm import Session
import models, schemas, crud
from database import SessionLocal, engine, get_db

# Create database tables
# Create database tables (Done in lifespan now for better logging)
# models.Base.metadata.create_all(bind=engine)

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler("app.log"),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# Helper to get settings with defaults
def get_config(db: Session, key: str, default: str = None) -> str:
    """
    Get a setting from Env Var (priority), then DB, with retry logic and silent fallback.
    Rules:
    1. Env Vars (uppercase) always take precedence.
    2. DB settings are second.
    3. Default value is last resort.
    """
    # 1. Check Environment Variable (uppercased key)
    env_val = os.getenv(key.upper())
    if env_val:
        return env_val

    # 2. Check Database with Retry Logic
    retries = 3
    for attempt in range(retries):
        try:
            setting = crud.get_setting(db, key)
            if setting:
                return setting.value
            return default
        except Exception as e:
            msg = str(e)
            if "no such table" in msg or "OperationalError" in msg:
                if attempt < retries - 1:
                    logger.warning(f"get_config failed (attempt {attempt+1}): {msg}. Retrying...")
                    time.sleep(1)
                    continue
            logger.error(f"get_config critical error: {msg}")
            # If DB is broken to the point of no tables, we MUST fallback to defaults 
            # effectively ignoring the DB config, to let startup proceed (if possible).
            # But authentication needs real credentials from somewhere.
            return default
    return default

def seed_settings(db: Session):
    """Seed default settings if they don't exist."""
    defaults = {
        "casepeer_username": os.getenv("CASEPEER_USERNAME", DEFAULT_CASEPEER_USERNAME),
        "casepeer_password": os.getenv("CASEPEER_PASSWORD", DEFAULT_CASEPEER_PASSWORD),
        "casepeer_base_url": os.getenv("CASEPEER_BASE_URL", DEFAULT_CASEPEER_BASE_URL),
        "gmail_email": os.getenv("GMAIL_EMAIL", DEFAULT_GMAIL_EMAIL),
        "gmail_app_password": os.getenv("GMAIL_APP_PASSWORD", DEFAULT_GMAIL_APP_PASSWORD),
        "otp_retry_count": os.getenv("OTP_RETRY_COUNT", "10"),
        "otp_retry_delay": os.getenv("OTP_RETRY_DELAY", "5"),
    }
    
    for key, value in defaults.items():
        try:
            if not crud.get_setting(db, key):
                logger.info(f"Seeding default setting: {key}")
                crud.set_setting(db, schemas.AppSettingCreate(key=key, value=value, description="Default value"))
        except Exception as e:
             logger.error(f"Failed to seed setting {key}: {e}")
    
    logger.info("✓ Settings seeding completed")

# Global session and token storage
# TODO: Move to environment variables or secure storage in production
ACCESS_TOKEN: Optional[str] = None
REFRESH_TOKEN: Optional[str] = None
CSRF_TOKEN: Optional[str] = None
session: requests.Session = requests.Session()

# CasePeer credentials (will be loaded from DB)
# Default values for fallback or initial setup
DEFAULT_CASEPEER_USERNAME = "SalehAI"
DEFAULT_CASEPEER_PASSWORD = "B$hSkWCr9n4gJ6U"
DEFAULT_CASEPEER_BASE_URL = "https://my.casepeer.com"
DEFAULT_GMAIL_EMAIL = "salehai@beverlylaw.org"
DEFAULT_GMAIL_APP_PASSWORD = "vzqucligkxfgoopn"

CASEPEER_API_BASE = f"{DEFAULT_CASEPEER_BASE_URL}"


# ============================================================================
# Application Lifespan
# ============================================================================

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Handle application startup and shutdown events."""
    # Startup
    logger.info("Starting CasePeer API Wrapper...")

    # Robust startup with retry logic - app MUST connect to database
    MAX_RETRIES = 10
    RETRY_DELAY = 3  # seconds
    
    db_ready = False
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            logger.info(f"Database connection attempt {attempt}/{MAX_RETRIES}...")
            
            # 1. Verify Database Connection
            with engine.connect() as connection:
                from sqlalchemy import text
                connection.execute(text("SELECT 1"))
                logger.info("✓ Database connection successful")
            
            # 2. Ensure Schema Exists
            logger.info("Ensuring database schema exists...")
            models.Base.metadata.create_all(bind=engine)
            
            # 3. Check tables exist
            from sqlalchemy import inspect
            inspector = inspect(engine)
            tables = inspector.get_table_names()
            logger.info(f"Existing tables in DB: {tables}")
            
            if "app_settings" not in tables:
                logger.warning(f"app_settings table not found yet, retrying...")
                time.sleep(RETRY_DELAY)
                continue
            
            logger.info("✓ app_settings table found")
            
            # 4. Seed and verify settings
            with SessionLocal() as db:
                seed_settings(db)
                
                # Verify we can actually read settings
                test_setting = get_config(db, "casepeer_username")
                if test_setting:
                    logger.info(f"✓ Settings verified (casepeer_username exists)")
                    db_ready = True
                    break
                else:
                    logger.warning("Settings not readable yet, retrying...")
                    
        except Exception as e:
            logger.warning(f"Startup attempt {attempt} failed: {e}")
        
        if attempt < MAX_RETRIES:
            logger.info(f"Retrying in {RETRY_DELAY} seconds...")
            time.sleep(RETRY_DELAY)
    
    if not db_ready:
        logger.error("CRITICAL: Failed to connect to database after all retries!")
        logger.error("The app will start but functionality will be broken.")
    else:
        logger.info("✓ Database fully operational")

    logger.info("Performing authentication on startup...")

    # First attempt to restore from database
    try:
        auth_success = await try_restore_session()
        
        if not auth_success:
            logger.info("No valid session in database, performing fresh login...")
            # Authenticate immediately on startup to ensure cookies are ready
            auth_success = await refresh_authentication()

        if auth_success:
            logger.info("✓ Startup authentication successful - proxy ready to use")
        else:
            logger.error("✗ Startup authentication failed - requests may fail")
            logger.error("  The proxy will attempt to re-authenticate on first 401/403 error")
            
    except Exception as e:
        logger.error(f"Startup Authentication Error: {e}", exc_info=True)

    yield

    # Shutdown (if needed in future)
    logger.info("Shutting down CasePeer API Wrapper...")


# Initialize FastAPI app
app = FastAPI(
    title="CasePeer API Wrapper",
    description="FastAPI wrapper for CasePeer API with automated authentication",
    version="1.0.0",
    lifespan=lifespan
)

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Allow all origins for development
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Mount Dashboard static files if the dist folder exists
# This handles /dashboard and its assets
dashboard_dist_path = os.path.join(os.getcwd(), "dashboard", "dist")
if os.path.exists(dashboard_dist_path):
    logger.info(f"Mounting dashboard from: {dashboard_dist_path}")
    app.mount("/dashboard", StaticFiles(directory=dashboard_dist_path, html=True), name="dashboard")
else:
    logger.warning(f"Dashboard dist folder not found at {dashboard_dist_path}. Dashboard will not be available.")


# ============================================================================
# Authentication Module
# ============================================================================

def fetch_otp_from_gmail(max_retries: int = 10, retry_delay: int = 5) -> Optional[str]:
    """
    Fetch OTP code from Gmail using IMAP.

    Args:
        max_retries: Maximum number of times to check for new emails
        retry_delay: Seconds to wait between retries

    Returns:
        str: The OTP code, or None if not found
    """
    logger.info("Connecting to Gmail to fetch OTP...")

    try:
        # Fetch credentials from DB
        with SessionLocal() as db:
            gmail_email = get_config(db, "gmail_email", DEFAULT_GMAIL_EMAIL)
            gmail_password = get_config(db, "gmail_app_password", DEFAULT_GMAIL_APP_PASSWORD)

        # Connect to Gmail IMAP server
        mail = imaplib.IMAP4_SSL("imap.gmail.com", 993)
        mail.login(gmail_email, gmail_password)
        mail.select("inbox")

        logger.info("Successfully connected to Gmail")

        # Poll for OTP email
        for attempt in range(max_retries):
            logger.info(f"Checking for OTP email (attempt {attempt + 1}/{max_retries})...")

            # Search for recent emails from CasePeer
            # Search for emails from the last 5 minutes
            status, messages = mail.search(None, 'FROM "casepeer" UNSEEN')

            if status == "OK" and messages[0]:
                email_ids = messages[0].split()

                # Get the most recent email
                latest_email_id = email_ids[-1]
                status, msg_data = mail.fetch(latest_email_id, "(RFC822)")

                if status == "OK":
                    # Parse email content
                    email_body = msg_data[0][1]
                    email_message = email.message_from_bytes(email_body)

                    # Extract email body
                    body = ""
                    if email_message.is_multipart():
                        for part in email_message.walk():
                            if part.get_content_type() == "text/plain":
                                body = part.get_payload(decode=True).decode()
                                break
                    else:
                        body = email_message.get_payload(decode=True).decode()

                    logger.info(f"Email body preview: {body[:200]}...")

                    # Extract OTP using regex (looking for 6-digit code)
                    otp_patterns = [
                        r'\b(\d{6})\b',  # 6-digit code
                        r'code.*?(\d{6})',  # "code: 123456"
                        r'OTP.*?(\d{6})',  # "OTP: 123456"
                        r'passcode.*?(\d{6})',  # "passcode: 123456"
                    ]

                    for pattern in otp_patterns:
                        match = re.search(pattern, body, re.IGNORECASE)
                        if match:
                            otp = match.group(1)
                            logger.info(f"Successfully extracted OTP: {otp}")
                            mail.close()
                            mail.logout()
                            return otp

            # Wait before next retry
            if attempt < max_retries - 1:
                logger.info(f"No OTP found, waiting {retry_delay} seconds...")
                time.sleep(retry_delay)

        logger.error("Failed to find OTP email after all retries")
        mail.close()
        mail.logout()
        return None

    except Exception as e:
        logger.error(f"Gmail OTP fetch failed: {str(e)}", exc_info=True)
        return None


def playwright_login(username: str, password: str, base_url: str, otp_retry_count: int, otp_retry_delay: int) -> tuple[Optional[str], Optional[str], Optional[str]]:
    """
    Authenticate with CasePeer using Playwright and extract tokens.

    Returns:
        tuple: (access_token, refresh_token, csrf_token) or (None, None, None) on failure
    """
    logger.info("Starting Playwright login flow...")

    try:
        with sync_playwright() as p:
            # Hardcode headless mode for server deployment
            is_headless = True
            logger.info(f"Launching browser (headless={is_headless})...")
            
            browser: Browser = p.chromium.launch(headless=is_headless)
            context = browser.new_context(
                user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/141.0.0.0 Safari/537.36'
            )
            page: Page = context.new_page()

            # (Credentials are now passed in as arguments)


            # Navigate to login page
            logger.info(f"Navigating to {base_url}...")
            page.goto(base_url)
            page.wait_for_load_state("networkidle")

            # Fill in credentials and submit
            logger.info("Filling in login credentials...")
            page.fill('input[name="username"], input[type="text"]', username)
            page.fill('input[name="password"], input[type="password"]', password)

            # Click login button
            page.click('button[type="submit"], input[type="submit"]')
            logger.info("Submitted login form...")

            # Wait for page to load
            page.wait_for_load_state("networkidle", timeout=30000)

            # Check if OTP is required
            logger.info("Checking for OTP input field...")
            otp_input_selectors = [
                'input[name="otp_token"]',  # CasePeer specific
                'input[id="id_otp_token"]',  # CasePeer specific
                'input[placeholder="Authentication Code"]',  # CasePeer specific
                'input[type="text"][name*="otp"]',
                'input[type="text"][id*="otp_token"]',
                'input[type="text"][placeholder*="code"]',
                'input[name="otp"]',
                'input[placeholder*="OTP"]'
            ]

            otp_field_found = False
            for selector in otp_input_selectors:
                try:
                    if page.locator(selector).count() > 0:
                        logger.info(f"OTP field detected with selector: {selector}")
                        otp_field_found = True

                        # Click Remember Me checkbox if it exists (it's often on the OTP page)
                        try:
                            remember_me_selectors = [
                                'input[name="remember_me"]',
                                'input[id="id_remember_me"]',
                                'input[type="checkbox"]',
                                'label:has-text("Remember me")'
                            ]
                            for rm_selector in remember_me_selectors:
                                if page.locator(rm_selector).count() > 0:
                                    logger.info(f"Clicking 'Remember Me' checkbox on OTP page (selector: {rm_selector})")
                                    page.click(rm_selector)
                                    break
                        except Exception as e:
                            logger.warning(f"Could not click 'Remember Me' checkbox on OTP page: {e}")

                        # Fetch OTP from Gmail
                        otp_code = fetch_otp_from_gmail(max_retries=otp_retry_count, retry_delay=otp_retry_delay)

                        if otp_code:
                            logger.info(f"Filling OTP code: {otp_code}")

                            # Wait for the OTP field to be ready
                            try:
                                page.wait_for_selector(selector, state="visible", timeout=5000)
                                logger.info(f"OTP field is visible and ready")
                            except:
                                logger.warning(f"Timeout waiting for OTP field, proceeding anyway")

                            # Try multiple methods to fill the OTP
                            fill_success = False
                            try:
                                # Method 1: Standard fill
                                page.fill(selector, otp_code)
                                logger.info("OTP filled using page.fill()")
                                fill_success = True
                            except Exception as e:
                                logger.warning(f"page.fill() failed: {e}")
                                try:
                                    # Method 2: Locator fill
                                    page.locator(selector).fill(otp_code)
                                    logger.info("OTP filled using locator.fill()")
                                    fill_success = True
                                except Exception as e2:
                                    logger.warning(f"locator.fill() failed: {e2}")
                                    try:
                                        # Method 3: Type character by character
                                        page.click(selector)
                                        page.keyboard.type(otp_code)
                                        logger.info("OTP filled using keyboard.type()")
                                        fill_success = True
                                    except Exception as e3:
                                        logger.error(f"All fill methods failed: {e3}")

                            if not fill_success:
                                logger.error("Failed to fill OTP field")
                                page.screenshot(path="otp_fill_failed.png")
                                #browser.close()
                                return None, None, None

                            # Take screenshot after filling
                            page.screenshot(path="otp_filled.png")
                            logger.info("Screenshot saved: otp_filled.png")

                            # Submit OTP (look for submit button)
                            submit_selectors = [
                                'button[type="submit"]',
                                'input[type="submit"]',
                                'button:has-text("Verify")',
                                'button:has-text("Submit")',
                                'button:has-text("Continue")',
                                'button:has-text("Log in")',
                                'button:has-text("Login")'
                            ]

                            submitted = False
                            for submit_selector in submit_selectors:
                                try:
                                    button_count = page.locator(submit_selector).count()
                                    logger.info(f"Checking selector '{submit_selector}': found {button_count} element(s)")

                                    if button_count > 0:
                                        logger.info(f"Attempting to click: {submit_selector}")
                                        page.click(submit_selector, timeout=3000)
                                        logger.info(f"Successfully clicked submit button: {submit_selector}")
                                        submitted = True
                                        break
                                except Exception as e:
                                    logger.warning(f"Failed to click '{submit_selector}': {e}")
                                    continue

                            if not submitted:
                                logger.error("Could not find or click submit button")
                                page.screenshot(path="submit_button_not_found.png")
                                # Try pressing Enter as fallback
                                logger.info("Trying Enter key as fallback...")
                                try:
                                    page.keyboard.press("Enter")
                                    logger.info("Pressed Enter key")
                                    submitted = True
                                except Exception as e:
                                    logger.error(f"Enter key failed: {e}")

                            if not submitted:
                                logger.error("All submit methods failed")
                                #browser.close()
                                return None, None, None

                            # Wait for authentication to complete
                            page.wait_for_load_state("networkidle", timeout=30000)
                            logger.info("OTP authentication completed")
                        else:
                            logger.error("Failed to retrieve OTP from Gmail")
                            #browser.close()
                            return None, None, None

                        break
                except:
                    continue

            if not otp_field_found:
                logger.info("No OTP field detected, proceeding without 2FA")

            # Extract tokens from localStorage
            access_token = page.evaluate("() => localStorage.getItem('ACCESS_TOKEN')")
            refresh_token = page.evaluate("() => localStorage.getItem('REFRESH_TOKEN')")

            # Extract all cookies including CSRF token and sessionid
            csrf_token = None
            session_id = None
            cookies = context.cookies()

            logger.info(f"Extracting {len(cookies)} cookies from authenticated session...")

            for cookie in cookies:
                cookie_name = cookie['name']
                cookie_value = cookie['value']

                # Log important cookies
                if cookie_name in ['csrftoken', 'sessionid', 'ACCESS_TOKEN', 'REFRESH_TOKEN']:
                    logger.info(f"Found cookie: {cookie_name} = {cookie_value[:20]}...")

                # Extract CSRF token
                if cookie_name == 'csrftoken':
                    csrf_token = cookie_value
                    logger.info(f"Extracted CSRF token: {csrf_token[:20]}...")

                # Extract session ID (critical for form submissions)
                elif cookie_name == 'sessionid':
                    session_id = cookie_value
                    logger.info(f"Extracted sessionid: {session_id[:20]}...")

                # If tokens not in localStorage, check cookies
                elif cookie_name == 'ACCESS_TOKEN':
                    access_token = cookie_value
                elif cookie_name == 'REFRESH_TOKEN':
                    refresh_token = cookie_value

                # Add all cookies to session
                session.cookies.set(
                    cookie_name,
                    cookie_value,
                    domain=cookie.get('domain', ''),
                    path=cookie.get('path', '/')
                )

            logger.info(f"Added {len(cookies)} cookies to session")

            #browser.close()

            if csrf_token:
                logger.info("Successfully extracted CSRF token and cookies")
                
                # Save session to DB
                session_data = {
                    "access_token": access_token,
                    "refresh_token": refresh_token,
                    "csrf_token": csrf_token,
                    "cookies": [
                        {
                            "name": c['name'],
                            "value": c['value'],
                            "domain": c.get('domain', ''),
                            "path": c.get('path', '/')
                        } for c in cookies
                    ]
                }
                with SessionLocal() as db:
                    crud.save_session(db, json.dumps(session_data))
                logger.info("Session state saved to database")

                return access_token, refresh_token, csrf_token
            else:
                logger.error("Failed to extract CSRF token")
                return None, None, None

    except Exception as e:
        logger.error(f"Playwright login failed: {str(e)}", exc_info=True)
        return None, None, None


async def refresh_authentication() -> bool:
    """
    Refresh authentication tokens using Playwright login.
    Runs Playwright in a separate thread to avoid async loop conflicts.

    Returns:
        bool: True if authentication successful, False otherwise
    """
    global ACCESS_TOKEN, REFRESH_TOKEN, CSRF_TOKEN

    logger.info("Refreshing authentication...")

    # First attempt to restore from database to see if we can avoid Playwright
    if await try_restore_session():
        logger.info("Session restored from database, skipping Playwright login")
        return True

    # Run Playwright in a separate thread to avoid async loop issues
    # Fetch credentials in MAIN thread to avoid DB threading issues
    with SessionLocal() as db:
        casepeer_base_url = get_config(db, "casepeer_base_url", DEFAULT_CASEPEER_BASE_URL)
        username = get_config(db, "casepeer_username", DEFAULT_CASEPEER_USERNAME)
        password = get_config(db, "casepeer_password", DEFAULT_CASEPEER_PASSWORD)
        otp_retry_count = int(get_config(db, "otp_retry_count", "10"))
        otp_retry_delay = int(get_config(db, "otp_retry_delay", "5"))

    # Pass credentials to the thread
    access_token, refresh_token, csrf_token = await asyncio.to_thread(
        playwright_login, 
        username, 
        password, 
        casepeer_base_url, 
        otp_retry_count, 
        otp_retry_delay
    )

    # Re-fetch base URL if needed (though we have it) or just use the local var
    # casepeer_base_url is already fetched above

    if csrf_token:
        ACCESS_TOKEN = access_token
        REFRESH_TOKEN = refresh_token
        CSRF_TOKEN = csrf_token

        # Update session headers with all required headers
        session.headers.update({
            'Accept': 'application/json, text/plain, */*',
            'Accept-Encoding': 'gzip, deflate, br, zstd',
            'Accept-Language': 'en-GB,en-US;q=0.9,en;q=0.8',
            'Referer': f'{casepeer_base_url}/',
            'X-CSRFToken': CSRF_TOKEN,
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/141.0.0.0 Safari/537.36',
            'sec-fetch-dest': 'empty',
            'sec-fetch-mode': 'cors',
            'sec-fetch-site': 'same-origin',
            'sec-ch-ua': '"Google Chrome";v="141", "Not?A_Brand";v="8", "Chromium";v="141"',
            'sec-ch-ua-mobile': '?0',
            'sec-ch-ua-platform': '"Windows"'
        })

        # Add Authorization header if access token exists
        if ACCESS_TOKEN:
            session.headers['Authorization'] = f'Bearer {ACCESS_TOKEN}'

        logger.info("Authentication refreshed successfully")
        return True
    else:
        logger.error("Failed to refresh authentication")
        return False


async def try_restore_session() -> bool:
    """
    Attempt to restore authentication session from the database.
    
    Returns:
        bool: True if session was restored, False otherwise
    """
    global ACCESS_TOKEN, REFRESH_TOKEN, CSRF_TOKEN
    
    logger.info("Attempting to restore session from database...")
    
    try:
        with SessionLocal() as db:
            db_session = crud.get_latest_session(db)
            if not db_session:
                logger.info("No saved session found in database")
                return False
            
            session_data = json.loads(db_session.session_data)
            
            # Check if session is too old (e.g., > 30 days)
            # For now, we'll try to use it and let it fail naturally if expired
            
            ACCESS_TOKEN = session_data.get("access_token")
            REFRESH_TOKEN = session_data.get("refresh_token")
            CSRF_TOKEN = session_data.get("csrf_token")
            stored_cookies = session_data.get("cookies", [])
            
            # Restore cookies to requests session
            for cookie in stored_cookies:
                session.cookies.set(
                    cookie['name'],
                    cookie['value'],
                    domain=cookie.get('domain', ''),
                    path=cookie.get('path', '/')
                )
            
            # Fetch base URL from DB for headers
            casepeer_base_url = get_config(db, "casepeer_base_url", DEFAULT_CASEPEER_BASE_URL)
            
            # Update session headers
            session.headers.update({
                'Accept': 'application/json, text/plain, */*',
                'Accept-Language': 'en-GB,en-US;q=0.9,en;q=0.8',
                'Referer': f'{casepeer_base_url}/',
                'X-CSRFToken': CSRF_TOKEN,
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/141.0.0.0 Safari/537.36',
            })
            
            if ACCESS_TOKEN:
                session.headers['Authorization'] = f'Bearer {ACCESS_TOKEN}'
                
            logger.info(f"✓ Session successfully restored from database (Updated: {db_session.updated_at})")
            return True
            
    except Exception as e:
        logger.error(f"Failed to restore session: {e}")
        return False


# ============================================================================
# API Client Module
# ============================================================================

async def make_api_request(endpoint: str, method: str = "GET", data: Any = None, content_type: str = "application/json", **kwargs):
    """
    Make an API request to CasePeer with automatic token refresh on 401/403.

    Args:
        endpoint: API endpoint path (e.g., "/case/case-documents/123/")
        method: HTTP method (GET, POST, etc.)
        data: Request body data for POST/PUT/PATCH requests
        content_type: Content type of the request (JSON or form)
        **kwargs: Additional arguments to pass to requests

    Returns:
        Response object from requests

    Raises:
        HTTPException: On API errors
    """
    # Fetch base URL from DB
    with SessionLocal() as db:
        casepeer_base_url = get_config(db, "casepeer_base_url", DEFAULT_CASEPEER_BASE_URL)
        
    url = f"{casepeer_base_url}{endpoint}"
    logger.info(f"Making {method} request to {url}")

    # Log current session cookies for debugging
    cookie_names = list(session.cookies.keys())
    logger.info(f"Session cookies: {cookie_names}")
    if 'sessionid' in cookie_names:
        logger.info(f"✓ sessionid cookie present")
    else:
        logger.warning(f"⚠ sessionid cookie MISSING - form submissions may fail")

    # Ensure we have authentication
    if ACCESS_TOKEN:
        session.headers.update({
            'Authorization': f'Bearer {ACCESS_TOKEN}',
        })

    try:
        # Prepare request arguments
        request_kwargs = kwargs.copy()
        if data is not None:
            # Determine how to send the data based on content type
            if "multipart/form-data" in content_type:
                files = kwargs.pop('files', None)  # Expect files dict from caller
                request_kwargs['data'] = data  # regular form fields
                if files:
                    request_kwargs['files'] = files
                session.headers.pop('Content-Type', None)      # actual file uploads
    # Do NOT set Content-Type manually; requests sets boundary automatically
            else:
                # Send as JSON (default)
                request_kwargs['json'] = data
                session.headers['Content-Type'] = 'application/json'

        # Make the request in a separate thread to avoid blocking
        response = await asyncio.to_thread(session.request, method, url, **request_kwargs)

        # Handle 401/403 - Unauthorized/Forbidden (both indicate authentication needed)
        if response.status_code in (401, 403):
            logger.warning(f"Received {response.status_code}, refreshing authentication...")

            # Attempt to refresh authentication
            if await refresh_authentication():
                logger.info("Retrying request after authentication refresh...")
                # Retry the request once
                response = await asyncio.to_thread(session.request, method, url, **request_kwargs)
            else:
                logger.error("Authentication refresh failed")
                raise HTTPException(
                    status_code=401,
                    detail="Authentication failed. Unable to refresh tokens."
                )

        # Return response object (not just JSON)
        logger.info(f"Request completed with status {response.status_code}")
        return response

    except requests.exceptions.RequestException as e:
        logger.error(f"Request exception: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail=f"Failed to communicate with CasePeer API: {str(e)}"
        )


# ============================================================================
# Form Data Helper Functions
# ============================================================================

def extract_csrf_from_html(html_content: str) -> Optional[str]:
    """
    Extract CSRF token from HTML form.

    Args:
        html_content: HTML content containing the form

    Returns:
        CSRF token string or None if not found
    """
    try:
        soup = BeautifulSoup(html_content, 'html.parser')
        csrf_input = soup.find('input', {'name': 'csrfmiddlewaretoken'})
        if csrf_input and csrf_input.get('value'):
            return csrf_input['value']
    except Exception as e:
        logger.warning(f"BeautifulSoup CSRF extraction failed: {e}")

    try:
        match = re.search(r'name="csrfmiddlewaretoken"\s+value="([^"]+)"', html_content)
        if match:
            return match.group(1)
    except Exception as e:
        logger.warning(f"Regex CSRF extraction failed: {e}")

    return None


def parse_form_fields(html_content: str) -> Dict[str, Any]:
    """
    Parse all form fields from HTML to preserve existing data.

    Args:
        html_content: HTML content containing the form

    Returns:
        Dictionary with all form field values
    """
    form_data = {}

    try:
        soup = BeautifulSoup(html_content, 'html.parser')

        # Parse input fields
        for input_field in soup.find_all('input'):
            field_name = input_field.get('name')
            field_value = input_field.get('value', '')
            field_type = input_field.get('type', 'text')

            if field_name and field_name != 'csrfmiddlewaretoken':
                if field_type == 'checkbox':
                    if input_field.get('checked'):
                        if field_name in form_data:
                            if isinstance(form_data[field_name], list):
                                form_data[field_name].append(field_value)
                            else:
                                form_data[field_name] = [form_data[field_name], field_value]
                        else:
                            form_data[field_name] = field_value
                else:
                    if field_name in form_data:
                        if isinstance(form_data[field_name], list):
                            form_data[field_name].append(field_value)
                        else:
                            form_data[field_name] = [form_data[field_name], field_value]
                    else:
                        form_data[field_name] = field_value if field_value else ''

        # Parse textarea fields
        for textarea in soup.find_all('textarea'):
            field_name = textarea.get('name')
            if field_name:
                form_data[field_name] = textarea.get_text(strip=False)

        # Parse select fields
        for select in soup.find_all('select'):
            field_name = select.get('name')
            if field_name:
                selected_option = select.find('option', selected=True)
                if selected_option:
                    form_data[field_name] = selected_option.get('value', '')
                else:
                    first_option = select.find('option')
                    form_data[field_name] = first_option.get('value', '') if first_option else ''

        logger.info(f"Parsed {len(form_data)} form fields from HTML")

    except Exception as e:
        logger.error(f"Error parsing form data: {e}", exc_info=True)

    return form_data


# ============================================================================
# FastAPI Routes
# ============================================================================


@app.post("/api/authenticate")
async def manual_authenticate():
    """
    Manual authentication endpoint to force re-authentication.

    Use this endpoint if:
    - Startup authentication failed
    - Session cookies expired
    - You need to refresh authentication manually

    Returns:
        JSON response with authentication status
    """
    logger.info("Manual authentication requested via /api/authenticate endpoint")

    success = await refresh_authentication()

    if success:
        cookie_names = list(session.cookies.keys())
        return {
            "success": True,
            "message": "Authentication successful",
            "authenticated": True,
            "cookies_count": len(cookie_names),
            "has_sessionid": 'sessionid' in cookie_names,
            "has_csrftoken": 'csrftoken' in cookie_names
        }
    else:
        raise HTTPException(
            status_code=500,
            detail="Authentication failed. Check server logs for details."
        )


@app.post("/api/proxy_upload_file/{case_id}")
async def proxy_upload_file(
    case_id: str,
    file: UploadFile,
    folder_id: Optional[str] = Form(None),
    save_to_linked: Optional[str] = Form(None),
    csrfmiddlewaretoken: Optional[str] = Form(None) # Allow N8N to provide CSRF
):
    """
    Proxy endpoint for uploading files to CasePeer.
    
    This endpoint is designed for direct file uploads to CasePeer's
    `/case/{case_id}/upload-file/` endpoint. It accepts a file and
    additional form fields.

    It will attempt to use the global CSRF_TOKEN if not provided,
    bypassing the automatic GET-then-POST logic of the generic proxy.

    Args:
        case_id: The ID of the case to upload the file to.
        file: The file to upload (FastAPI UploadFile).
        folder_id: Optional ID of the folder to save the file in.
        save_to_linked: Optional field to link the document.
        csrfmiddlewaretoken: Optional CSRF token. If not provided,
                             the global CSRF_TOKEN will be used.
    """
    logger.info(f"File upload requested for case_id: {case_id}")

    # Validate CSRF token
    final_csrf_token = csrfmiddlewaretoken or CSRF_TOKEN
    if not final_csrf_token:
        logger.error("No CSRF token found in request or globally. Cannot proceed with upload.")
        raise HTTPException(
            status_code=400,
            detail="CSRF token is missing. Please authenticate first or provide it in the request."
        )
    file_content = await file.read()
    files = {
        'file': (file.filename, file_content, file.content_type)
    }

    # Prepare form data including the file
    form_data = {
        'csrfmiddlewaretoken': final_csrf_token,
        'submitButton': 'upload' # Common submit button name for uploads
    }

    if folder_id:
        form_data['folder_id'] = folder_id
        logger.info(f"Adding folder_id: {folder_id}")
    if save_to_linked:
        form_data['save_to_linked'] = save_to_linked
        logger.info(f"Adding save_to_linked: {save_to_linked}")

    # The actual CasePeer endpoint for file uploads
    endpoint = f"/case/{case_id}/document/upload-file/"
    logger.info(f"Attempting to upload file to CasePeer endpoint: {endpoint}")

    try:
        # Use make_api_request with multipart/form-data content type
        # The 'data' parameter will handle both form fields and the UploadFile object
        response = await make_api_request(
            endpoint,
            method="POST",
            data=form_data,
            files=files,
            content_type="multipart/form-data" # Explicitly set for file uploads
        )

        # CasePeer often redirects or returns HTML on successful form submissions
        if response.status_code in (200, 201, 302, 303):
            logger.info(f"File upload response status: {response.status_code}")

            # Check for success indicators in the response content (e.g., redirect to case page, success message)
            if "login" in response.text.lower() or "sign in" in response.text.lower():
                raise HTTPException(
                    status_code=401,
                    detail="Authentication required. Session may have expired during file upload."
                )

            # Attempt to parse JSON if available, otherwise return text
            try:
                return response.json()
            except requests.exceptions.JSONDecodeError:
                logger.warning("Upload response is not JSON, returning text content.")
                return {
                    "success": True,
                    "message": "File upload process initiated/completed. CasePeer returned HTML.",
                    "filename": file.filename,
                    "status_code": response.status_code,
                    "response_text_preview": response.text[:200]
                }
        else:
            logger.error(f"File upload failed with status code: {response.status_code}. Response: {response.text}")
            raise HTTPException(
                status_code=response.status_code,
                detail=f"File upload failed: {response.status_code} - {response.text}"
            )

    except HTTPException:
        raise # Re-raise known HTTPExceptions
    except Exception as e:
        logger.error(f"Error during file upload: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail=f"Internal server error during file upload: {str(e)}"
        )


# ============================================================================
# Dashboard API Endpoints
# ============================================================================

# ============================================================================
# Dashboard API Endpoints
# ============================================================================

# Cases
@app.post("/api/cases", response_model=schemas.Case)
def create_case(case: schemas.CaseCreate, db: Session = Depends(get_db)):
    return crud.create_new_case(db=db, case=case)

@app.get("/api/cases", response_model=list[schemas.Case])
def read_cases(skip: int = 0, limit: int = 100, db: Session = Depends(get_db)):
    return crud.get_all_cases(db=db, skip=skip, limit=limit)

@app.get("/api/cases/{case_id}", response_model=schemas.Case)
def read_case(case_id: str, db: Session = Depends(get_db)):
    db_case = crud.get_case_by_id(db, case_id=case_id)
    if db_case is None:
        raise HTTPException(status_code=404, detail="Case not found")
    return db_case

# Negotiations
@app.post("/api/negotiations", response_model=schemas.Negotiation)
def create_negotiation(negotiation: schemas.NegotiationCreate, db: Session = Depends(get_db)):
    # Verify case exists
    db_case = crud.get_case_by_id(db, case_id=negotiation.case_id)
    if not db_case:
        raise HTTPException(status_code=404, detail="Case not found")
    return crud.create_negotiation(db=db, negotiation=negotiation)

@app.get("/api/negotiations", response_model=list[schemas.Negotiation])
def read_negotiations(case_id: str, db: Session = Depends(get_db)):
    return crud.get_negotiations_by_case(db=db, case_id=case_id)

# Classifications
@app.post("/api/classifications", response_model=schemas.Classification)
def create_classification(classification: schemas.ClassificationCreate, db: Session = Depends(get_db)):
    # Verify case exists
    db_case = crud.get_case_by_id(db, case_id=classification.case_id)
    if not db_case:
        raise HTTPException(status_code=404, detail="Case not found")
    return crud.create_classification(db=db, classification=classification)

@app.get("/api/classifications", response_model=list[schemas.Classification])
def read_classifications(case_id: str, db: Session = Depends(get_db)):
    return crud.get_classifications_by_case(db=db, case_id=case_id)

# Reminders
@app.post("/api/reminders", response_model=schemas.Reminder)
def create_reminder(reminder: schemas.ReminderCreate, db: Session = Depends(get_db)):
    # Verify case exists
    db_case = crud.get_case_by_id(db, case_id=reminder.case_id)
    if not db_case:
        raise HTTPException(status_code=404, detail="Case not found")
    return crud.create_reminder(db=db, reminder=reminder)

@app.get("/api/reminders", response_model=list[schemas.Reminder])
def read_reminders(case_id: str, db: Session = Depends(get_db)):
    return crud.get_reminders_by_case(db=db, case_id=case_id)

# Token Usage
@app.post("/api/token_usage", response_model=schemas.TokenUsage)
def create_token_usage(usage: schemas.TokenUsageCreate, db: Session = Depends(get_db)):
    return crud.create_token_usage(db=db, usage=usage)

@app.get("/api/token_usage", response_model=list[schemas.TokenUsage])
def read_token_usage(skip: int = 0, limit: int = 100, db: Session = Depends(get_db)):
    return crud.get_token_usage(db=db, skip=skip, limit=limit)


@app.get("/api/settings/", response_model=list[schemas.AppSetting])
def read_settings(skip: int = 0, limit: int = 100, db: Session = Depends(get_db)):
    return crud.get_settings(db, skip=skip, limit=limit)

@app.post("/api/settings/", response_model=schemas.AppSetting)
def create_or_update_setting(setting: schemas.AppSettingCreate, db: Session = Depends(get_db)):
    return crud.set_setting(db=db, setting=setting)

@app.get("/api/logs")
def get_logs(limit: int = 100):
    """Get the last N lines of logs."""
    log_file = "app.log"
    if not os.path.exists(log_file):
        return {"logs": []}
    
    try:
        with open(log_file, "r") as f:
            lines = f.readlines()
            return {"logs": lines[-limit:]}
    except Exception as e:
        logger.error(f"Failed to read logs: {e}")
        return {"logs": [f"Error reading logs: {e}"]}

# ============================================================================
# NEW ENDPOINT: Update Provider Email (Added for n8n integration)
# ============================================================================

@app.post("/api/update-provider-email")
async def update_provider_email(request: Request):
    """
    Update provider email address while preserving all other fields.

    This endpoint:
    1. Fetches current provider form data
    2. Updates only the email field
    3. Submits the form with all preserved data

    Request body (JSON):
    {
        "email": "newemail@example.com",
        "provider_id": "142681",
        "case_id": "0"  (optional, defaults to "0")
    }

    Returns:
        JSON response with success status and details
    """
    try:
        from bs4 import BeautifulSoup
    except ImportError:
        raise HTTPException(
            status_code=500,
            detail="BeautifulSoup not installed. Run: pip install beautifulsoup4"
        )

    logger.info("Provider email update requested via /api/update-provider-email")

    # Parse request body
    try:
        body = await request.json()
        email = body.get("email")
        provider_id = body.get("provider_id")
        case_id = body.get("case_id", "0")

        if not email or not provider_id:
            raise HTTPException(
                status_code=400,
                detail="Missing required fields: email and provider_id"
            )

        logger.info(f"Updating email for provider {provider_id} to {email}")

    except Exception as e:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid request body: {str(e)}"
        )

    # Step 1: Fetch current provider form data
    endpoint = f"/case/{case_id}/contact/provider/{provider_id}/"
    logger.info(f"Step 1: Fetching current form data from {endpoint}")

    try:
        response = await make_api_request(endpoint, method="GET")

        if response.status_code != 200:
            raise HTTPException(
                status_code=response.status_code,
                detail=f"Failed to fetch provider form: {response.status_code}"
            )

        # Extract HTML content
        try:
            data = response.json()
            if 'response' in data and isinstance(data['response'], str):
                html_content = data['response']
            else:
                html_content = response.text
        except:
            html_content = response.text

        logger.info("Successfully fetched provider form")

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to fetch provider form: {str(e)}"
        )

    # Step 2: Parse all form fields to preserve existing data
    logger.info("Step 2: Parsing existing form fields")
    form_data = {}

    try:
        soup = BeautifulSoup(html_content, 'html.parser')

        # Find all input fields
        for input_field in soup.find_all('input'):
            field_name = input_field.get('name')
            field_value = input_field.get('value', '')
            field_type = input_field.get('type', 'text')

            if field_name and field_name != 'csrfmiddlewaretoken':
                if field_type == 'checkbox':
                    if input_field.get('checked'):
                        if field_name in form_data:
                            if isinstance(form_data[field_name], list):
                                form_data[field_name].append(field_value)
                            else:
                                form_data[field_name] = [form_data[field_name], field_value]
                        else:
                            form_data[field_name] = field_value
                else:
                    if field_name in form_data:
                        if isinstance(form_data[field_name], list):
                            form_data[field_name].append(field_value)
                        else:
                            form_data[field_name] = [form_data[field_name], field_value]
                    else:
                        form_data[field_name] = field_value if field_value else ''

        # Find all textarea fields
        for textarea in soup.find_all('textarea'):
            field_name = textarea.get('name')
            if field_name:
                form_data[field_name] = textarea.get_text(strip=False)

        # Find all select fields
        for select in soup.find_all('select'):
            field_name = select.get('name')
            if field_name:
                selected_option = select.find('option', selected=True)
                if selected_option:
                    form_data[field_name] = selected_option.get('value', '')
                else:
                    first_option = select.find('option')
                    form_data[field_name] = first_option.get('value', '') if first_option else ''

        logger.info(f"Parsed {len(form_data)} form fields")

        if len(form_data) < 5:
            raise HTTPException(
                status_code=500,
                detail=f"Form parsing failed. Only found {len(form_data)} fields (expected 20+). May need re-authentication."
            )

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to parse form data: {str(e)}"
        )

    # Step 3: Update only the email field
    logger.info(f"Step 3: Updating email from '{form_data.get('email-email', 'N/A')}' to '{email}'")
    old_email = form_data.get('email-email', 'N/A')
    form_data['email-email'] = email

    # Ensure submitButton is included
    if 'submitButton' not in form_data:
        form_data['submitButton'] = 'Submit'

    # CSRF token will be auto-injected by the proxy

    # Step 4: Submit the updated form
    logger.info("Step 4: Submitting updated form")

    try:
        response = await make_api_request(
            endpoint,
            method="POST",
            data=form_data,
            content_type="application/x-www-form-urlencoded"
        )

        if response.status_code in (200, 201, 302, 303):
            # Check if we got a login page (shouldn't happen with auto-auth)
            if "Please Sign In" in response.text or "sign-overlay" in response.text:
                raise HTTPException(
                    status_code=401,
                    detail="Authentication required. Session may have expired."
                )

            logger.info("✅ Email updated successfully")

            return {
                "success": True,
                "message": f"Email updated successfully to {email}",
                "provider_id": provider_id,
                "case_id": case_id,
                "old_email": old_email,
                "new_email": email,
                "fields_preserved": len(form_data) - 1,
                "status_code": response.status_code
            }
        else:
            raise HTTPException(
                status_code=response.status_code,
                detail=f"Form submission failed with status {response.status_code}"
            )

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to submit form: {str(e)}"
        )

# ============================================================================
# END OF NEW ENDPOINT
# ============================================================================


# ============================================================================
# External Integrations Endpoints
# ============================================================================

@app.get("/api/integrations/openai/usage")
def get_openai_usage(db: Session = Depends(get_db)):
    """Fetch usage data from OpenAI API."""
    api_key = get_config(db, "openai_api_key")
    if not api_key:
         raise HTTPException(status_code=400, detail="OpenAI API Key not set in settings")
    
    try:
        # Calculate start and end date for current month
        from datetime import datetime, timedelta
        now = datetime.now()
        start_date = now.replace(day=1).strftime("%Y-%m-%d")
        end_date = (now.replace(day=1) + timedelta(days=32)).replace(day=1).strftime("%Y-%m-%d")

        # Use the organization usage endpoint
        # https://api.openai.com/v1/organization/usage/completions
        url = f"https://api.openai.com/v1/organization/usage/completions?start_date={start_date}&end_date={end_date}"
        
        headers = {
            "Authorization": f"Bearer {api_key}"
        }
        
        response = requests.get(url, headers=headers)
        
        if response.status_code == 200:
            return response.json()
        elif response.status_code == 401:
             # Fallback for project keys / different scope
             models_resp = requests.get("https://api.openai.com/v1/models", headers=headers)
             if models_resp.status_code == 200:
                 return {
                     "message": "Key is valid, but Organization Usage API is restricted. Showing zero usage.",
                     "data": [],
                     "models_available": len(models_resp.json().get('data', []))
                 }
             else:
                 raise HTTPException(status_code=401, detail="Invalid OpenAI API Key")
        else:
            return {"error": response.text, "status_code": response.status_code}

    except Exception as e:
        logger.error(f"OpenAI API Error: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/integrations/n8n/executions")
def get_n8n_executions(db: Session = Depends(get_db)):
    """Fetch execution stats from n8n."""
    api_key = get_config(db, "n8n_api_key")
    base_url = get_config(db, "n8n_webhook_url", "").strip()
    
    if not api_key:
         raise HTTPException(status_code=400, detail="n8n API Key not set in settings")
         
    if not base_url:
        return {"error": "n8n Base URL not configured"}

    try:
        parsed = urlparse(base_url)
        api_base = f"{parsed.scheme}://{parsed.netloc}/api/v1"
    except:
        return {"error": "Invalid n8n URL"}

    try:
        url = f"{api_base}/executions?limit=50"
        
        headers = {}
        if api_key.startswith("ey"):
             headers["Authorization"] = f"Bearer {api_key}"
        else:
             headers["X-N8N-API-KEY"] = api_key
        
        response = requests.get(url, headers=headers)
        
        if response.status_code == 200:
            data = response.json()
            executions = data.get('data', [])
            success_count = sum(1 for e in executions if e.get('finished', False))
            error_count = len(executions) - success_count
            return {
                "total_fetched": len(executions),
                "success": success_count,
                "error": error_count,
                "recent_executions": executions[:5]
            }
        else:
             return {"error": f"n8n API Error: {response.text}", "status_code": response.status_code}

    except Exception as e:
        logger.error(f"n8n API Error: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.api_route("/{path:path}", methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS", "HEAD"])
async def proxy_request(request: Request, path: str):
    """
    Universal proxy endpoint that forwards any request to CasePeer API.

    This endpoint acts as a transparent proxy, forwarding all requests to the
    CasePeer API with automatic authentication handling.

    Args:
        request: FastAPI Request object
        path: The API path to forward to (everything after the domain)

    Returns:
        JSON response from CasePeer API

    Raises:
        HTTPException: On authentication or API errors
    """
    # Reserved paths that should NOT be proxied
    # "dashboard" is handled by the StaticFiles mount if path starts with dashboard/
    # but the catch-all might still see it if not careful.
    reserved_prefixes = ["dashboard", "api", "docs", "redoc", "openapi.json", "static"]
    
    # Check if the path starts with any reserved prefix
    is_reserved = False
    for reserved in reserved_prefixes:
        if path.startswith(reserved):
            is_reserved = True
            break
            
    # Health check for root path
    if not path or path == "":
        return {
            "status": "online",
            "service": "CasePeer API Proxy",
            "authenticated": ACCESS_TOKEN is not None,
            "dashboard_available": os.path.exists(dashboard_dist_path)
        }

    # If it's a reserved path and reached here, it means it wasn't caught by 
    # specific routes or the static mount.
    if is_reserved:
        # Special case: If path is exactly "dashboard", redirect to "dashboard/" for the static mount
        if path == "dashboard":
             from fastapi.responses import RedirectResponse
             return RedirectResponse(url="/dashboard/")
        raise HTTPException(status_code=404, detail=f"Path '{path}' is not a valid CasePeer endpoint.")

    # Construct endpoint path
    endpoint = f"/{path}" if not path.startswith("/") else path

    # Add query parameters if present
    if request.url.query:
        endpoint = f"{endpoint}?{request.url.query}"

    # Check for HTTP Method Override header (for ngrok PATCH workaround)
    # This allows sending POST requests that are converted to PATCH
    # Useful when ngrok blocks PATCH requests
    method = request.method
    method_override = request.headers.get("X-HTTP-Method-Override", "").upper()

    if method_override and method == "POST":
        logger.info(f"🔄 Method Override detected: POST → {method_override}")
        method = method_override
        logger.info(f"   Converting request method from POST to {method_override}")

    logger.info(f"Proxying {method} request to endpoint: {endpoint}")


    try:
        # Get request body for POST/PUT/PATCH requests
        body = None
        content_type = request.headers.get("content-type", "")

        if method in ["POST", "PUT", "PATCH"]:
            try:
                # Check if the request is JSON or form data
                if "application/json" in content_type:
                    body = await request.json()
                    logger.info(f"Request body (JSON): {body}")
                elif "application/x-www-form-urlencoded" in content_type or "multipart/form-data" in content_type:
                    # Handle form-encoded data
                    form_data = await request.form()
                    body = dict(form_data)
                    logger.info(f"Request body (Form): {body}")

                    # ============================================================
                    # AUTOMATIC GET-THEN-POST PATTERN FOR FORM SUBMISSIONS
                    # ============================================================
                    # If CSRF token is missing, do GET-then-POST automatically
                    if 'csrfmiddlewaretoken' not in body:
                        logger.info("🔄 CSRF token missing - initiating automatic GET-then-POST flow")
                        logger.info(f"   Step 1: GET {endpoint} to fetch form data")

                        # Step 1: GET the form to extract CSRF and existing fields
                        try:
                            get_response = await make_api_request(endpoint, method="GET")

                            if get_response.status_code == 200:
                                # Extract HTML content
                                html_content = None
                                try:
                                    data = get_response.json()
                                    if 'response' in data and isinstance(data['response'], str):
                                        html_content = data['response']
                                    else:
                                        html_content = get_response.text
                                except:
                                    html_content = get_response.text

                                if html_content:
                                    # Step 2: Extract CSRF token
                                    logger.info("   Step 2: Extract CSRF token from form")
                                    csrf_token = extract_csrf_from_html(html_content)

                                    if csrf_token:
                                        logger.info(f"   ✅ Extracted CSRF token: {csrf_token[:20]}...")

                                        # Step 3: Parse all existing form fields
                                        logger.info("   Step 3: Parse existing form fields")
                                        existing_form_data = parse_form_fields(html_content)

                                        if existing_form_data and len(existing_form_data) >= 5:
                                            logger.info(f"   ✅ Parsed {len(existing_form_data)} existing fields")

                                            # Step 4: Merge incoming data with existing form data
                                            logger.info("   Step 4: Merge incoming data with existing fields")
                                            # Existing fields are preserved, incoming fields override
                                            existing_form_data.update(body)
                                            existing_form_data['csrfmiddlewaretoken'] = csrf_token

                                            # Ensure submitButton is present
                                            if 'submitButton' not in existing_form_data:
                                                existing_form_data['submitButton'] = 'Submit'

                                            # Replace body with merged form data
                                            body = existing_form_data

                                            logger.info(f"   ✅ Form data merged: {len(body)} total fields")
                                            logger.info("   🚀 Proceeding with POST using complete form data")
                                        else:
                                            logger.warning(f"   ⚠️  Only parsed {len(existing_form_data) if existing_form_data else 0} fields")
                                            logger.warning("   Falling back to original body + global CSRF token")
                                            if CSRF_TOKEN:
                                                body['csrfmiddlewaretoken'] = CSRF_TOKEN
                                    else:
                                        logger.warning("   ⚠️  Could not extract CSRF token from form")
                                        logger.warning("   Falling back to global CSRF token")
                                        if CSRF_TOKEN:
                                            body['csrfmiddlewaretoken'] = CSRF_TOKEN
                                else:
                                    logger.warning("   ⚠️  Empty HTML content from GET request")
                                    if CSRF_TOKEN:
                                        body['csrfmiddlewaretoken'] = CSRF_TOKEN
                            else:
                                logger.warning(f"   ⚠️  GET request failed with status {get_response.status_code}")
                                if CSRF_TOKEN:
                                    body['csrfmiddlewaretoken'] = CSRF_TOKEN

                        except Exception as e:
                            logger.error(f"   ❌ GET-then-POST flow failed: {e}")
                            logger.warning("   Falling back to global CSRF token")
                            if CSRF_TOKEN:
                                body['csrfmiddlewaretoken'] = CSRF_TOKEN
                    else:
                        logger.info("✅ CSRF token already present in request body")

                else:
                    # Try JSON by default
                    body = await request.json()
                    logger.info(f"Request body: {body}")
            except:
                # No body or empty body
                logger.info("No request body")
                pass

        # Make API request
        response = await make_api_request(endpoint, method=method, data=body, content_type=content_type)

        # Try to return JSON response
        try:
            return response.json()
        except:
            # If response is not JSON, return text
            return {"response": response.text, "status_code": response.status_code}

    except HTTPException:
        # Re-raise HTTP exceptions from make_api_request
        raise
    except Exception as e:
        logger.error(f"Unexpected error: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail=f"Internal server error: {str(e)}"
        )


if __name__ == "__main__":
    import uvicorn

    logger.info("Starting FastAPI server...")
    uvicorn.run(app, host="0.0.0.0", port=8000, log_level="info")