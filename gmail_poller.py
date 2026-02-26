"""
Gmail Poller - Background task that replaces n8n entirely.

Polls Gmail via IMAP for new negotiation emails, processes them through
the negotiation agent, and sends replies via SMTP. Runs as a background
task inside the FastAPI app on Render.
"""

import imaplib
import smtplib
import email as email_lib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
import asyncio
import base64
import json
import logging
import re
import time
import requests as http_requests
from typing import Optional, Dict, Any, List
from datetime import datetime

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

POLL_INTERVAL_SECONDS = 60  # Check every 60 seconds (same as n8n)
IMAP_HOST = "imap.gmail.com"
IMAP_PORT = 993
SMTP_HOST = "smtp.gmail.com"
SMTP_PORT = 465  # SSL port (Render blocks 587/STARTTLS)

# Sender filter — only process emails FROM these addresses (comma-separated).
# These should be PROVIDER email addresses you're negotiating with.
# Set in Turso as "negotiation_sender_filter".
DEFAULT_SENDER_FILTER = ""


# ---------------------------------------------------------------------------
# State tracking
# ---------------------------------------------------------------------------

_poller_running = False
_poller_task: Optional[asyncio.Task] = None
_poller_stats = {
    "started_at": None,
    "last_poll": None,
    "emails_processed": 0,
    "emails_replied": 0,
    "errors": 0,
    "last_error": None,
    "status": "stopped",
}


def get_poller_stats() -> Dict[str, Any]:
    """Return current poller status and stats."""
    return {**_poller_stats, "running": _poller_running}


# ---------------------------------------------------------------------------
# Gmail credentials helper
# ---------------------------------------------------------------------------

def _get_gmail_creds() -> tuple:
    """Get Gmail credentials from Turso settings or env vars."""
    from turso_client import get_setting
    import os

    gmail_email = get_setting("gmail_email") or os.getenv("GMAIL_EMAIL", "")
    gmail_password = get_setting("gmail_app_password") or os.getenv("GMAIL_APP_PASSWORD", "")
    sender_filter = get_setting("negotiation_sender_filter") or os.getenv("NEGOTIATION_SENDER_FILTER", DEFAULT_SENDER_FILTER)

    return gmail_email, gmail_password, sender_filter


# ---------------------------------------------------------------------------
# IMAP: Fetch unread emails and full threads
# ---------------------------------------------------------------------------

def fetch_unread_threads(gmail_email: str, gmail_password: str, sender_filter: str) -> List[Dict]:
    """
    Connect to Gmail via IMAP, find unread emails matching the sender filter,
    fetch the full thread for each, mark as read, and return thread data.

    Returns a list of thread dicts, each containing messages in the thread.
    """
    threads = []

    try:
        mail = imaplib.IMAP4_SSL(IMAP_HOST, IMAP_PORT)
        mail.login(gmail_email, gmail_password)
        status, select_data = mail.select("inbox")
        total_in_inbox = select_data[0].decode() if select_data and select_data[0] else "?"
        logger.info(f"[Poller] Connected as {gmail_email} | INBOX has {total_in_inbox} total messages")

        # Quick check: how many UNSEEN in entire inbox?
        chk_status, chk_data = mail.search(None, "UNSEEN")
        total_unseen = len(chk_data[0].split()) if chk_status == "OK" and chk_data[0] else 0
        logger.info(f"[Poller] Total UNSEEN in inbox: {total_unseen}")

        # Search for unread emails from the sender(s) — supports comma-separated list
        email_ids = []
        if sender_filter:
            for sender in sender_filter.split(","):
                sender = sender.strip()
                if not sender:
                    continue
                status, message_ids = mail.search(None, f'FROM "{sender}" UNSEEN')
                if status == "OK" and message_ids[0]:
                    email_ids.extend(message_ids[0].split())
            # Deduplicate (in case an email matches multiple senders)
            email_ids = list(dict.fromkeys(email_ids))
        else:
            status, message_ids = mail.search(None, "UNSEEN")
            if status == "OK" and message_ids[0]:
                email_ids = message_ids[0].split()

        if not email_ids:
            if total_unseen > 0:
                # There are unread emails but none match the sender filter
                sample_froms = []
                try:
                    for uid in chk_data[0].split()[:5]:
                        s, d = mail.fetch(uid, "(BODY.PEEK[HEADER.FIELDS (FROM)])")
                        if s == "OK" and d[0]:
                            raw_from = d[0][1].decode("utf-8", errors="replace").strip()
                            sample_froms.append(raw_from.replace("From: ", "").strip())
                except Exception:
                    pass
                logger.warning(
                    f"[Poller] Filter '{sender_filter}' matched 0, but {total_unseen} total unread exist. "
                    f"Sample FROM headers: {sample_froms}"
                )
            else:
                logger.info(f"[Poller] IMAP reports 0 UNSEEN emails in INBOX for {gmail_email}")

            mail.close()
            mail.logout()
            return []
        logger.info(f"[Poller] Found {len(email_ids)} unread email(s)")

        seen_threads = {}  # threadId -> thread dict (deduplicate by conversation)
        for eid in email_ids:
            try:
                thread = _fetch_thread_for_email(mail, eid)
                if thread:
                    tid = thread["threadId"]
                    # Keep the version with the most messages (fullest thread)
                    if tid not in seen_threads or len(thread["messages"]) > len(seen_threads[tid]["messages"]):
                        seen_threads[tid] = thread

                    # Mark as read regardless (avoid re-processing)
                    mail.store(eid, "+FLAGS", "\\Seen")

            except Exception as e:
                logger.error(f"[Poller] Error processing email {eid}: {e}")

        threads = list(seen_threads.values())
        if len(threads) < len(email_ids):
            logger.info(f"[Poller] Deduplicated {len(email_ids)} emails into {len(threads)} unique thread(s)")

        mail.close()
        mail.logout()

    except Exception as e:
        logger.error(f"[Poller] IMAP connection failed: {e}", exc_info=True)

    return threads


def _fetch_thread_for_email(mail: imaplib.IMAP4_SSL, email_id: bytes) -> Optional[Dict]:
    """
    Fetch a single email and reconstruct its thread using References/In-Reply-To headers.
    Returns a dict mimicking the Gmail API thread format that the agent expects.
    """
    status, msg_data = mail.fetch(email_id, "(RFC822)")
    if status != "OK":
        return None

    raw_email = msg_data[0][1]
    msg = email_lib.message_from_bytes(raw_email)

    # Get thread identifiers
    message_id = msg.get("Message-ID", "")
    references = msg.get("References", "")
    in_reply_to = msg.get("In-Reply-To", "")
    subject = msg.get("Subject", "")

    # Build thread by searching for related messages
    thread_messages = []

    # Find all messages in this thread using subject matching
    # Gmail threads are grouped by subject, so search by subject
    clean_subject = re.sub(r'^(Re:|Fwd?:)\s*', '', subject, flags=re.IGNORECASE).strip()
    if clean_subject:
        # Search for all messages with this subject (read and unread)
        search_subject = clean_subject[:60]  # IMAP has limits
        # Escape quotes in subject for IMAP search
        search_subject = search_subject.replace('"', '\\"')
        try:
            status, thread_ids = mail.search(None, f'SUBJECT "{search_subject}"')
            if status == "OK" and thread_ids[0]:
                for tid in thread_ids[0].split():
                    parsed = _parse_email_to_thread_format(mail, tid)
                    if parsed:
                        thread_messages.append(parsed)
        except Exception as e:
            logger.warning(f"[Poller] Thread search failed for subject '{clean_subject[:30]}': {e}")

    # If thread search failed, at least include the original message
    if not thread_messages:
        parsed = _parse_raw_email(msg, email_id)
        if parsed:
            thread_messages.append(parsed)

    # Sort by date (oldest first, like Gmail API)
    thread_messages.sort(key=lambda m: m.get("internalDate", "0"))

    # Use subject as thread ID (since IMAP doesn't have Gmail thread IDs)
    thread_id = clean_subject or message_id

    return {
        "threadId": thread_id,
        "messages": thread_messages,
    }


def _parse_email_to_thread_format(mail: imaplib.IMAP4_SSL, email_id: bytes) -> Optional[Dict]:
    """Fetch and parse a single email into the format the agent expects."""
    try:
        status, msg_data = mail.fetch(email_id, "(RFC822)")
        if status != "OK":
            return None
        raw = msg_data[0][1]
        msg = email_lib.message_from_bytes(raw)
        return _parse_raw_email(msg, email_id)
    except Exception:
        return None


def _parse_raw_email(msg: email_lib.message.Message, email_id: bytes = b"0") -> Dict:
    """Convert a parsed email.message.Message into the dict format the agent expects."""
    from_addr = msg.get("From", "")
    to_addr = msg.get("To", "")
    subject = msg.get("Subject", "")
    date_str = msg.get("Date", "")
    message_id = msg.get("Message-ID", str(email_id))

    # Extract body
    body_text = ""
    body_html = ""

    if msg.is_multipart():
        for part in msg.walk():
            ct = part.get_content_type()
            if ct == "text/plain" and not body_text:
                payload = part.get_payload(decode=True)
                if payload:
                    body_text = payload.decode("utf-8", errors="replace")
            elif ct == "text/html" and not body_html:
                payload = part.get_payload(decode=True)
                if payload:
                    body_html = payload.decode("utf-8", errors="replace")
    else:
        payload = msg.get_payload(decode=True)
        if payload:
            body_text = payload.decode("utf-8", errors="replace")

    # Use snippet (first 200 chars of plain text)
    snippet = (body_text or body_html or "")[:200].replace("\n", " ").strip()

    # Parse date to timestamp
    internal_date = "0"
    try:
        parsed_date = email_lib.utils.parsedate_to_datetime(date_str)
        internal_date = str(int(parsed_date.timestamp() * 1000))
    except Exception:
        pass

    return {
        "id": message_id,
        "threadId": re.sub(r'^(Re:|Fwd?:)\s*', '', subject, flags=re.IGNORECASE).strip(),
        "From": from_addr,
        "To": to_addr,
        "Subject": subject,
        "snippet": snippet,
        "internalDate": internal_date,
        "payload": {
            "headers": [
                {"name": "From", "value": from_addr},
                {"name": "To", "value": to_addr},
                {"name": "Subject", "value": subject},
                {"name": "Date", "value": date_str},
            ],
            "body": {},
            "parts": []
        },
        # Store decoded body directly for the agent's parser
        "_decoded_body": body_text or body_html or snippet,
    }


# ---------------------------------------------------------------------------
# Gmail OAuth2 helpers (for sending via Gmail REST API over HTTPS)
# ---------------------------------------------------------------------------

GMAIL_OAUTH2_SCOPES = "https://www.googleapis.com/auth/gmail.send"


def _get_oauth2_creds() -> tuple:
    """Get Gmail OAuth2 client credentials from Turso settings or env vars."""
    from turso_client import get_setting
    import os
    client_id = get_setting("gmail_oauth2_client_id") or os.getenv("GMAIL_OAUTH2_CLIENT_ID", "")
    client_secret = get_setting("gmail_oauth2_client_secret") or os.getenv("GMAIL_OAUTH2_CLIENT_SECRET", "")
    return client_id, client_secret


def get_gmail_oauth2_auth_url(redirect_uri: str) -> str:
    """Build the Google OAuth2 authorization URL for the user to visit."""
    client_id, _ = _get_oauth2_creds()
    params = {
        "client_id": client_id,
        "redirect_uri": redirect_uri,
        "response_type": "code",
        "scope": GMAIL_OAUTH2_SCOPES,
        "access_type": "offline",
        "prompt": "consent",
    }
    qs = "&".join(f"{k}={http_requests.utils.quote(str(v))}" for k, v in params.items())
    return f"https://accounts.google.com/o/oauth2/v2/auth?{qs}"


def exchange_oauth2_code(code: str, redirect_uri: str) -> Dict:
    """Exchange authorization code for access_token + refresh_token."""
    client_id, client_secret = _get_oauth2_creds()
    resp = http_requests.post("https://oauth2.googleapis.com/token", data={
        "code": code,
        "client_id": client_id,
        "client_secret": client_secret,
        "redirect_uri": redirect_uri,
        "grant_type": "authorization_code",
    })
    return resp.json()


def _refresh_access_token(refresh_token: str) -> Optional[str]:
    """Use refresh_token to get a fresh access_token."""
    client_id, client_secret = _get_oauth2_creds()
    try:
        resp = http_requests.post("https://oauth2.googleapis.com/token", data={
            "client_id": client_id,
            "client_secret": client_secret,
            "refresh_token": refresh_token,
            "grant_type": "refresh_token",
        })
        data = resp.json()
        if "access_token" in data:
            return data["access_token"]
        logger.error(f"[Gmail API] Token refresh failed: {data}")
        return None
    except Exception as e:
        logger.error(f"[Gmail API] Token refresh error: {e}")
        return None


def _send_via_gmail_api(gmail_email: str, to_address: str, subject: str,
                        html_body: str, in_reply_to: str = "",
                        references: str = "") -> bool:
    """Send email via Gmail REST API over HTTPS (works on Render free tier)."""
    from turso_client import get_setting
    refresh_token = get_setting("gmail_oauth2_refresh_token", "")
    if not refresh_token:
        logger.warning("[Gmail API] No refresh token configured, skipping API send")
        return False

    access_token = _refresh_access_token(refresh_token)
    if not access_token:
        return False

    # Build MIME message
    msg = MIMEMultipart("alternative")
    msg["From"] = gmail_email
    msg["To"] = to_address
    msg["Subject"] = subject if subject.lower().startswith("re:") else f"Re: {subject}"
    if in_reply_to:
        msg["In-Reply-To"] = in_reply_to
    if references:
        msg["References"] = references

    clean_html = html_body.replace("</br>", "<br>")

    # Append Gmail signature if configured
    signature = get_setting("gmail_signature", "")
    if signature:
        clean_html += f"\n<br><br>{signature}"

    full_html = f'<html><body style="font-family: Arial, sans-serif; font-size: 14px;">\n{clean_html}\n</body></html>'
    msg.attach(MIMEText(full_html, "html"))

    # Base64url-encode the MIME message
    raw_message = base64.urlsafe_b64encode(msg.as_bytes()).decode("ascii")

    # Send via Gmail API
    resp = http_requests.post(
        "https://gmail.googleapis.com/gmail/v1/users/me/messages/send",
        headers={"Authorization": f"Bearer {access_token}", "Content-Type": "application/json"},
        json={"raw": raw_message},
    )

    if resp.status_code == 200:
        logger.info(f"[Gmail API] Reply sent to {to_address} | Subject: {msg['Subject']}")
        return True
    else:
        logger.error(f"[Gmail API] Send failed ({resp.status_code}): {resp.text[:300]}")
        return False


# ---------------------------------------------------------------------------
# Send reply emails (Gmail API first, SMTP fallback)
# ---------------------------------------------------------------------------

def send_reply(gmail_email: str, gmail_password: str,
               to_address: str, subject: str, html_body: str,
               in_reply_to: str = "", references: str = "") -> bool:
    """
    Send an HTML email reply. Tries Gmail REST API first (works on Render
    free tier where SMTP ports are blocked), falls back to SMTP.
    """
    # Try Gmail API first (HTTPS, no port restrictions)
    if _send_via_gmail_api(gmail_email, to_address, subject, html_body, in_reply_to, references):
        return True

    # Fallback: try SMTP (works on paid Render or local dev)
    logger.info("[Poller] Gmail API unavailable, trying SMTP fallback...")
    try:
        msg = MIMEMultipart("alternative")
        msg["From"] = gmail_email
        msg["To"] = to_address
        msg["Subject"] = subject if subject.lower().startswith("re:") else f"Re: {subject}"
        if in_reply_to:
            msg["In-Reply-To"] = in_reply_to
        if references:
            msg["References"] = references

        clean_html = html_body.replace("</br>", "<br>")

        # Append Gmail signature if configured
        from turso_client import get_setting as _get_sig
        sig = _get_sig("gmail_signature", "")
        if sig:
            clean_html += f"\n<br><br>{sig}"

        full_html = f'<html><body style="font-family: Arial, sans-serif; font-size: 14px;">\n{clean_html}\n</body></html>'
        msg.attach(MIMEText(full_html, "html"))

        with smtplib.SMTP_SSL(SMTP_HOST, SMTP_PORT) as server:
            server.login(gmail_email, gmail_password)
            server.send_message(msg)

        logger.info(f"[Poller] Reply sent via SMTP to {to_address} | Subject: {msg['Subject']}")
        return True
    except Exception as e:
        logger.error(f"[Poller] SMTP fallback also failed: {e}", exc_info=True)
        return False


# ---------------------------------------------------------------------------
# Main polling loop
# ---------------------------------------------------------------------------

async def _poll_loop():
    """Background loop that checks Gmail and processes emails."""
    global _poller_running, _poller_stats

    _poller_stats["started_at"] = datetime.now().isoformat()
    _poller_stats["status"] = "running"

    logger.info(f"[Poller] Started. Checking every {POLL_INTERVAL_SECONDS}s")

    while _poller_running:
        try:
            _poller_stats["last_poll"] = datetime.now().isoformat()
            _poller_stats["status"] = "polling"

            gmail_email, gmail_password, sender_filter = _get_gmail_creds()

            if not gmail_email or not gmail_password:
                logger.error("[Poller] Gmail credentials not configured")
                _poller_stats["status"] = "error: no credentials"
                await asyncio.sleep(POLL_INTERVAL_SECONDS)
                continue

            logger.info(f"[Poller] Polling for: {sender_filter}")

            # Fetch unread threads (runs in thread to avoid blocking)
            threads = await asyncio.to_thread(
                fetch_unread_threads, gmail_email, gmail_password, sender_filter
            )

            if not threads:
                logger.info("[Poller] No unread emails found")
                _poller_stats["status"] = "idle"
                await asyncio.sleep(POLL_INTERVAL_SECONDS)
                continue

            # Process each thread through the agent
            for thread_data in threads:
                try:
                    _poller_stats["status"] = "processing"
                    logger.info(f"[Poller] Processing thread: {thread_data.get('threadId', 'unknown')[:50]}")

                    # Run the negotiation agent
                    from negotiation_agent import process_negotiation_email
                    result = await process_negotiation_email(thread_data)

                    _poller_stats["emails_processed"] += 1

                    intent = result.get("intent", "unclear")
                    reply_message = result.get("reply_message")

                    logger.info(f"[Poller] Agent result: intent={intent}, reply={'yes' if reply_message else 'no'}")

                    # Send reply if the agent generated one
                    if reply_message and intent not in ("no_action", "escalate"):
                        # Determine reply-to address
                        messages = thread_data.get("messages", [])
                        last_msg = messages[-1] if messages else {}
                        to_address = last_msg.get("From", "")

                        logger.info(f"[Poller] Raw From field: '{to_address}'")

                        # Extract just the email from "Name <email@domain.com>"
                        email_match = re.search(r'<(.+?)>', to_address)
                        if email_match:
                            to_address = email_match.group(1)

                        subject = last_msg.get("Subject", "Lien Negotiation")
                        message_id = last_msg.get("id", "")

                        if to_address:
                            logger.info(f"[Poller] Sending reply to: {to_address} | Subject: {subject}")
                            sent = await asyncio.to_thread(
                                send_reply,
                                gmail_email, gmail_password,
                                to_address, subject, reply_message,
                                in_reply_to=message_id
                            )
                            if sent:
                                _poller_stats["emails_replied"] += 1
                            else:
                                logger.error(f"[Poller] Failed to send reply to {to_address}")
                        else:
                            logger.warning(f"[Poller] No reply-to address found, skipping send")

                    # Log escalations
                    if intent == "escalate":
                        logger.warning(f"[Poller] ESCALATION needed: {result.get('reasoning', 'Unknown reason')}")

                except Exception as e:
                    _poller_stats["errors"] += 1
                    _poller_stats["last_error"] = f"{datetime.now().isoformat()}: {str(e)[:200]}"
                    logger.error(f"[Poller] Error processing thread: {e}", exc_info=True)

            _poller_stats["status"] = "idle"

        except Exception as e:
            _poller_stats["errors"] += 1
            _poller_stats["last_error"] = f"{datetime.now().isoformat()}: {str(e)[:200]}"
            _poller_stats["status"] = f"error: {str(e)[:100]}"
            logger.error(f"[Poller] Poll cycle error: {e}", exc_info=True)

        try:
            await asyncio.sleep(POLL_INTERVAL_SECONDS)
        except asyncio.CancelledError:
            logger.info("[Poller] Sleep cancelled, shutting down")
            break

    _poller_stats["status"] = "stopped"
    logger.info("[Poller] Stopped")


# ---------------------------------------------------------------------------
# Start / Stop controls
# ---------------------------------------------------------------------------

async def start_poller():
    """Start the background email polling task."""
    global _poller_running, _poller_task

    if _poller_running:
        logger.info("[Poller] Already running")
        return {"status": "already_running"}

    _poller_running = True
    _poller_task = asyncio.create_task(_poll_loop())
    logger.info("[Poller] Starting background task")
    return {"status": "started"}


async def stop_poller():
    """Stop the background email polling task."""
    global _poller_running, _poller_task

    if not _poller_running:
        return {"status": "already_stopped"}

    _poller_running = False
    if _poller_task:
        _poller_task.cancel()
        _poller_task = None

    _poller_stats["status"] = "stopped"
    logger.info("[Poller] Stop requested")
    return {"status": "stopped"}
