"""
Persistent Playwright Browser Manager — keeps a single headless Chromium open
to maintain CasePeer session alive and enable instant cookie sync.

Instead of launching/closing a browser for every login (~45s with OTP),
the browser stays open permanently. Keepalive pings use authentic browser
navigation, and cookie re-sync to requests.Session is instant.
"""

import asyncio
import json
import logging
import threading
import time
from typing import Optional, Dict, Any

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Global state
# ---------------------------------------------------------------------------

_pw = None            # Playwright instance (async)
_browser = None       # Browser instance
_context = None       # BrowserContext with cookies
_page = None          # Main page (used for keepalive navigation)
_lock = threading.Lock()
_last_sync: float = 0.0          # Timestamp of last cookie sync
_last_keepalive: float = 0.0     # Timestamp of last keepalive ping
_launched = False                 # Whether browser was launched via this module


# ---------------------------------------------------------------------------
# Lifecycle
# ---------------------------------------------------------------------------

async def launch_persistent_browser() -> bool:
    """Launch a persistent headless Chromium browser.
    Called once from caseapi.lifespan() after initial login succeeds.
    """
    global _pw, _browser, _context, _page, _launched

    if _browser and _launched:
        logger.info("[BrowserMgr] Browser already running")
        return True

    try:
        from playwright.async_api import async_playwright

        _pw = await async_playwright().start()
        _browser = await _pw.chromium.launch(headless=True)
        _context = await _browser.new_context(
            user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 '
                        '(KHTML, like Gecko) Chrome/141.0.0.0 Safari/537.36'
        )
        _page = await _context.new_page()
        _launched = True
        logger.info("[BrowserMgr] Persistent browser launched")
        return True
    except Exception as e:
        logger.error(f"[BrowserMgr] Failed to launch persistent browser: {e}")
        return False


def adopt_browser_sync(browser, context, page):
    """Adopt a browser that was already launched by playwright_login() (sync API).

    Since playwright_login() uses sync_playwright, we store the sync objects
    and extract cookies from the context. The sync browser will be closed and
    replaced with an async browser on first keepalive.
    """
    global _context, _browser, _page, _launched, _last_sync

    with _lock:
        # Extract cookies from the sync context before anything else
        try:
            cookies = context.cookies()
            _sync_cookies_from_list(cookies)
            _last_sync = time.time()
            logger.info(f"[BrowserMgr] Adopted {len(cookies)} cookies from sync browser")
        except Exception as e:
            logger.warning(f"[BrowserMgr] Cookie extraction from sync browser failed: {e}")


async def close_browser():
    """Gracefully close the persistent browser (called on app shutdown)."""
    global _browser, _context, _page, _pw, _launched

    try:
        if _page:
            await _page.close()
        if _context:
            await _context.close()
        if _browser:
            await _browser.close()
        if _pw:
            await _pw.stop()
    except Exception as e:
        logger.warning(f"[BrowserMgr] Error closing browser: {e}")
    finally:
        _page = None
        _context = None
        _browser = None
        _pw = None
        _launched = False
        logger.info("[BrowserMgr] Browser closed")


# ---------------------------------------------------------------------------
# Cookie sync
# ---------------------------------------------------------------------------

def _sync_cookies_from_list(cookies: list) -> bool:
    """Push a list of cookie dicts into the global requests.Session + globals."""
    global _last_sync
    try:
        from caseapi import session, CSRF_TOKEN, ACCESS_TOKEN, REFRESH_TOKEN
        import caseapi

        synced = 0
        for c in cookies:
            name = c.get("name", "")
            value = c.get("value", "")
            if not name:
                continue
            session.cookies.set(
                name, value,
                domain=c.get("domain", ""),
                path=c.get("path", "/")
            )
            synced += 1

            if name == "csrftoken":
                caseapi.CSRF_TOKEN = value
            elif name == "ACCESS_TOKEN":
                caseapi.ACCESS_TOKEN = value
            elif name == "REFRESH_TOKEN":
                caseapi.REFRESH_TOKEN = value

        if synced:
            # Re-apply headers with updated tokens
            from turso_client import get_setting
            base_url = get_setting("casepeer_base_url", "https://my.casepeer.com")
            caseapi.apply_session_headers(base_url)
            _last_sync = time.time()

            # Also save to Turso as backup
            try:
                from turso_client import save_session
                session_data = {
                    "access_token": caseapi.ACCESS_TOKEN,
                    "refresh_token": caseapi.REFRESH_TOKEN,
                    "csrf_token": caseapi.CSRF_TOKEN,
                    "cookies": [
                        {"name": c.get("name"), "value": c.get("value"),
                         "domain": c.get("domain", ""), "path": c.get("path", "/")}
                        for c in cookies if c.get("name")
                    ],
                    "updated_at": time.time()
                }
                save_session("default", json.dumps(session_data))
            except Exception as e:
                logger.debug(f"[BrowserMgr] Turso session save failed (non-critical): {e}")

        return synced > 0
    except Exception as e:
        logger.error(f"[BrowserMgr] Cookie sync failed: {e}")
        return False


def sync_cookies_to_session() -> bool:
    """Extract cookies from the persistent browser context and sync to requests.Session.
    Returns True if cookies were synced successfully.
    """
    global _last_sync

    with _lock:
        if not _context:
            return False

        try:
            # For async context, we need to get cookies from the async context
            # This function may be called from sync code, so we handle both cases
            import asyncio
            try:
                loop = asyncio.get_running_loop()
                # We're in an async context — can't await here from sync caller
                # Schedule it and return False (caller should use async version)
                return False
            except RuntimeError:
                # No running loop — create one to extract cookies
                loop = asyncio.new_event_loop()
                try:
                    cookies = loop.run_until_complete(_context.cookies())
                    return _sync_cookies_from_list(cookies)
                finally:
                    loop.close()
        except Exception as e:
            logger.error(f"[BrowserMgr] sync_cookies_to_session failed: {e}")
            return False


async def async_sync_cookies() -> bool:
    """Async version of cookie sync — use from async code."""
    global _last_sync

    if not _context:
        return False

    try:
        cookies = await _context.cookies()
        return _sync_cookies_from_list(cookies)
    except Exception as e:
        logger.error(f"[BrowserMgr] async cookie sync failed: {e}")
        return False


# ---------------------------------------------------------------------------
# Keepalive
# ---------------------------------------------------------------------------

async def keepalive_via_browser() -> bool:
    """Navigate the persistent browser to CasePeer dashboard for keepalive.
    Syncs cookies to requests.Session after navigation.
    Returns True on success.
    """
    global _last_keepalive

    if not _page or not _launched:
        return False

    try:
        from turso_client import get_setting
        base_url = get_setting("casepeer_base_url", "https://my.casepeer.com")
        url = f"{base_url}/law/dashboard/"

        await _page.goto(url, wait_until="domcontentloaded", timeout=30000)
        content = await _page.content()

        # Check if we got redirected to login
        if "/login/" in _page.url or ("login" in content[:500].lower() and "password" in content[:500].lower()):
            logger.warning("[BrowserMgr] Browser keepalive: session expired (login redirect)")
            return False

        # Sync fresh cookies
        synced = await async_sync_cookies()
        _last_keepalive = time.time()
        logger.debug(f"[BrowserMgr] Keepalive OK, cookies synced: {synced}")
        return True
    except Exception as e:
        logger.warning(f"[BrowserMgr] Keepalive navigation failed: {e}")
        return False


# ---------------------------------------------------------------------------
# Fast re-auth (reuse existing browser)
# ---------------------------------------------------------------------------

async def fast_reauth() -> bool:
    """Re-authenticate within the persistent browser (no browser launch overhead).
    If 'Remember Me' was checked, CasePeer may skip OTP entirely.
    Returns True on success.
    """
    if not _page or not _launched:
        return False

    try:
        from turso_client import get_setting
        base_url = get_setting("casepeer_base_url", "https://my.casepeer.com")
        username = get_setting("casepeer_username", "SalehAI")
        password = get_setting("casepeer_password", "B$hSkWCr9n4gJ6U")

        logger.info("[BrowserMgr] Attempting fast re-auth in persistent browser...")

        # Navigate to login
        await _page.goto(base_url, wait_until="networkidle", timeout=30000)

        # Check if already logged in (no login page)
        if "/login/" not in _page.url:
            content = await _page.content()
            if not ("login" in content[:500].lower() and "password" in content[:500].lower()):
                logger.info("[BrowserMgr] Already logged in — syncing cookies")
                await async_sync_cookies()
                return True

        # Fill credentials
        await _page.fill('input[name="username"], input[type="text"]', username)
        await _page.fill('input[name="password"], input[type="password"]', password)
        await _page.click('button[type="submit"], input[type="submit"]')
        await _page.wait_for_load_state("networkidle", timeout=30000)

        # Check if OTP is needed
        otp_selectors = [
            'input[name="otp_token"]',
            'input[id="id_otp_token"]',
            'input[placeholder="Authentication Code"]',
        ]
        needs_otp = False
        for sel in otp_selectors:
            try:
                if await _page.locator(sel).count() > 0:
                    needs_otp = True
                    break
            except Exception:
                continue

        if needs_otp:
            logger.info("[BrowserMgr] OTP required for fast reauth — fetching from Gmail")
            from caseapi import fetch_otp_from_gmail
            otp_retry_count = int(get_setting("otp_retry_count", "10"))
            otp_retry_delay = int(get_setting("otp_retry_delay", "5"))
            otp_code = await asyncio.to_thread(fetch_otp_from_gmail, otp_retry_count, otp_retry_delay)

            if not otp_code:
                logger.error("[BrowserMgr] Failed to get OTP for fast reauth")
                return False

            # Check "Remember Me" if available
            try:
                rm_sel = 'input[name="remember_me"], input[id="id_remember_me"]'
                if await _page.locator(rm_sel).count() > 0:
                    await _page.click(rm_sel)
            except Exception:
                pass

            # Fill OTP
            for sel in otp_selectors:
                try:
                    if await _page.locator(sel).count() > 0:
                        await _page.fill(sel, otp_code)
                        break
                except Exception:
                    continue

            await _page.click('button[type="submit"], input[type="submit"]')
            await _page.wait_for_load_state("networkidle", timeout=30000)

        # Verify login succeeded
        content = await _page.content()
        if "/login/" in _page.url or ("login" in content[:500].lower() and "password" in content[:500].lower()):
            logger.error("[BrowserMgr] Fast reauth failed — still on login page")
            return False

        # Sync cookies
        synced = await async_sync_cookies()
        logger.info(f"[BrowserMgr] Fast reauth succeeded, cookies synced: {synced}")
        return True

    except Exception as e:
        logger.error(f"[BrowserMgr] Fast reauth failed: {e}")
        return False


# ---------------------------------------------------------------------------
# Status / Health check
# ---------------------------------------------------------------------------

def get_browser_status() -> Dict[str, Any]:
    """Return current browser status for monitoring."""
    return {
        "launched": _launched,
        "browser_alive": _browser is not None and _browser.is_connected() if _browser else False,
        "has_context": _context is not None,
        "has_page": _page is not None,
        "last_cookie_sync": _last_sync,
        "last_keepalive": _last_keepalive,
        "seconds_since_sync": round(time.time() - _last_sync, 1) if _last_sync else None,
        "seconds_since_keepalive": round(time.time() - _last_keepalive, 1) if _last_keepalive else None,
    }


def is_browser_alive() -> bool:
    """Quick check if the browser is still usable."""
    try:
        return _launched and _browser is not None and _browser.is_connected()
    except Exception:
        return False
