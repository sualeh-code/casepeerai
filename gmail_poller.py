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
import json
import logging
import re
import time
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

# Sender filter — only process emails forwarded through this address
# Set to None to process ALL unread emails (not recommended)
DEFAULT_SENDER_FILTER = "NatalyaValencia@beverlylaw.org,eyfectdesigns@gmail.com"


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
        mail.select("inbox")

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
            mail.close()
            mail.logout()
            return []
        logger.info(f"[Poller] Found {len(email_ids)} unread email(s)")

        for eid in email_ids:
            try:
                thread = _fetch_thread_for_email(mail, eid)
                if thread:
                    threads.append(thread)

                    # Mark as read
                    mail.store(eid, "+FLAGS", "\\Seen")

            except Exception as e:
                logger.error(f"[Poller] Error processing email {eid}: {e}")

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
# SMTP: Send reply emails
# ---------------------------------------------------------------------------

def send_reply(gmail_email: str, gmail_password: str,
               to_address: str, subject: str, html_body: str,
               in_reply_to: str = "", references: str = "") -> bool:
    """
    Send an HTML email reply via SMTP.

    Args:
        gmail_email: Sender email address
        gmail_password: Gmail app password
        to_address: Recipient email
        subject: Email subject (will be prefixed with "Re:" if not already)
        html_body: HTML content of the reply
        in_reply_to: Message-ID of the email being replied to (for threading)
        references: References header for threading

    Returns:
        True if sent successfully
    """
    try:
        # Build the email
        msg = MIMEMultipart("alternative")
        msg["From"] = gmail_email
        msg["To"] = to_address
        msg["Subject"] = subject if subject.lower().startswith("re:") else f"Re: {subject}"

        # Threading headers
        if in_reply_to:
            msg["In-Reply-To"] = in_reply_to
        if references:
            msg["References"] = references

        # Convert </br> to <br> for proper HTML
        clean_html = html_body.replace("</br>", "<br>")

        # Wrap in basic HTML structure
        full_html = f"""<html><body style="font-family: Arial, sans-serif; font-size: 14px;">
{clean_html}
</body></html>"""

        msg.attach(MIMEText(full_html, "html"))

        # Send via SMTP over SSL (port 465)
        with smtplib.SMTP_SSL(SMTP_HOST, SMTP_PORT) as server:
            server.login(gmail_email, gmail_password)
            server.send_message(msg)

        logger.info(f"[Poller] Reply sent to {to_address} | Subject: {msg['Subject']}")
        return True

    except Exception as e:
        logger.error(f"[Poller] SMTP send failed: {e}", exc_info=True)
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
