"""
Gmail Poller - Background task that replaces n8n entirely.

Polls Gmail via REST API for new negotiation emails, processes them through
the negotiation agent, and sends replies via Gmail API. Runs as a background
task inside the FastAPI app on Render.
"""

import smtplib
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
SMTP_HOST = "smtp.gmail.com"
SMTP_PORT = 465  # SSL port (Render blocks 587/STARTTLS)

# Sender filter — only process emails FROM these addresses (comma-separated).
# Set in Turso as "negotiation_sender_filter".
DEFAULT_SENDER_FILTER = ""

GMAIL_API_BASE = "https://gmail.googleapis.com/gmail/v1/users/me"


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
# Gmail OAuth2 helpers
# ---------------------------------------------------------------------------

GMAIL_OAUTH2_SCOPES = "https://www.googleapis.com/auth/gmail.modify"


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


def _get_api_access_token() -> Optional[str]:
    """Get a fresh Gmail API access token using the stored refresh token."""
    from turso_client import get_setting
    refresh_token = get_setting("gmail_oauth2_refresh_token", "")
    if not refresh_token:
        return None
    return _refresh_access_token(refresh_token)


# ---------------------------------------------------------------------------
# Gmail API: Fetch unread emails and full threads
# ---------------------------------------------------------------------------

def fetch_unread_threads(gmail_email: str, gmail_password: str, sender_filter: str) -> List[Dict]:
    """
    Fetch unread emails via Gmail REST API, matching the sender filter.
    Returns thread dicts with all messages, in the format the agent expects.
    """
    access_token = _get_api_access_token()
    if not access_token:
        logger.error("[Poller] No Gmail API access token — re-authorize OAuth2")
        return []

    headers = {"Authorization": f"Bearer {access_token}"}

    # Build Gmail search query
    if sender_filter:
        senders = [s.strip() for s in sender_filter.split(",") if s.strip()]
        from_query = " OR ".join(f"from:{s}" for s in senders)
        query = f"is:unread ({from_query})"
    else:
        query = "is:unread"

    logger.info(f"[Poller] Gmail API query: {query}")

    # 1. List matching messages
    try:
        resp = http_requests.get(
            f"{GMAIL_API_BASE}/messages",
            headers=headers,
            params={"q": query, "maxResults": 20},
            timeout=30,
        )
        if resp.status_code != 200:
            logger.error(f"[Poller] Gmail API list failed ({resp.status_code}): {resp.text[:200]}")
            return []

        data = resp.json()
        messages = data.get("messages", [])
        if not messages:
            logger.info("[Poller] Gmail API: 0 messages match query")
            return []

        logger.info(f"[Poller] Gmail API: {len(messages)} message(s) found")
    except Exception as e:
        logger.error(f"[Poller] Gmail API list error: {e}")
        return []

    # 2. Group by threadId and fetch full threads
    thread_ids = list(dict.fromkeys(m["threadId"] for m in messages))
    logger.info(f"[Poller] {len(thread_ids)} unique thread(s) to process")

    threads = []
    for tid in thread_ids:
        try:
            thread_data = _fetch_thread_via_api(tid, headers)
            if thread_data:
                # Analyze any PDF attachments with Gemini
                pdf_results = process_thread_attachments(thread_data)
                if pdf_results:
                    thread_data["_pdf_analyses"] = pdf_results
                    logger.info(f"[Poller] {len(pdf_results)} PDF(s) analyzed in thread {tid[:15]}")

                threads.append(thread_data)
                # Mark all messages in this thread as read
                _mark_thread_read(tid, headers)
        except Exception as e:
            logger.error(f"[Poller] Error fetching thread {tid}: {e}")

    return threads


def _fetch_thread_via_api(thread_id: str, headers: Dict) -> Optional[Dict]:
    """Fetch a full thread from Gmail API and convert to agent format."""
    resp = http_requests.get(
        f"{GMAIL_API_BASE}/threads/{thread_id}",
        headers=headers,
        params={"format": "full"},
        timeout=30,
    )
    if resp.status_code != 200:
        logger.warning(f"[Poller] Thread fetch failed for {thread_id}: {resp.status_code}")
        return None

    thread = resp.json()
    api_messages = thread.get("messages", [])
    if not api_messages:
        return None

    # Convert each Gmail API message to the format the agent expects
    parsed_messages = []
    for msg in api_messages:
        parsed = _parse_gmail_api_message(msg)
        if parsed:
            parsed_messages.append(parsed)

    if not parsed_messages:
        return None

    return {
        "threadId": thread_id,
        "messages": parsed_messages,
    }


def _parse_gmail_api_message(msg: Dict) -> Optional[Dict]:
    """Convert a Gmail API message object into the format the agent expects."""
    msg_id = msg.get("id", "")
    thread_id = msg.get("threadId", "")
    snippet = msg.get("snippet", "")
    internal_date = msg.get("internalDate", "")

    # Extract headers
    payload = msg.get("payload", {})
    headers_list = payload.get("headers", [])
    header_map = {}
    for h in headers_list:
        header_map[h["name"].lower()] = h["value"]

    from_addr = header_map.get("from", "")
    to_addr = header_map.get("to", "")
    subject = header_map.get("subject", "")
    date_str = header_map.get("date", "")
    # RFC Message-ID header (needed for In-Reply-To threading)
    rfc_message_id = header_map.get("message-id", "")
    rfc_references = header_map.get("references", "")

    # Extract body (try plain text first, then HTML)
    body_text = ""
    body_html = ""

    def _extract_body(part: Dict):
        nonlocal body_text, body_html
        mime = part.get("mimeType", "")
        body_data = part.get("body", {}).get("data", "")

        if body_data:
            try:
                decoded = base64.urlsafe_b64decode(body_data).decode("utf-8", errors="replace")
                if mime == "text/plain" and not body_text:
                    body_text = decoded
                elif mime == "text/html" and not body_html:
                    body_html = decoded
            except Exception:
                pass

        # Recurse into multipart
        for sub_part in part.get("parts", []):
            _extract_body(sub_part)

    _extract_body(payload)

    # Build snippet from body if needed
    if not snippet and (body_text or body_html):
        if body_text:
            snippet = body_text[:200]
        elif body_html:
            from bs4 import BeautifulSoup
            try:
                snippet = BeautifulSoup(body_html, "html.parser").get_text()[:200]
            except Exception:
                snippet = body_html[:200]

    # Detect PDF attachments
    pdf_attachments = []

    def _find_pdf_parts(part: Dict):
        mime = part.get("mimeType", "")
        filename = part.get("filename", "")
        att_id = part.get("body", {}).get("attachmentId", "")
        if att_id and (mime == "application/pdf" or filename.lower().endswith(".pdf")):
            pdf_attachments.append({
                "attachmentId": att_id,
                "filename": filename,
                "mimeType": mime,
            })
        for sub in part.get("parts", []):
            _find_pdf_parts(sub)

    _find_pdf_parts(payload)

    return {
        "id": msg_id,
        "threadId": thread_id,
        "From": from_addr,
        "To": to_addr,
        "Subject": subject,
        "Date": date_str,
        "Message-ID": rfc_message_id,
        "References": rfc_references,
        "snippet": snippet,
        "internalDate": internal_date,
        "payload": payload,
        "_decoded_body": body_text or body_html or snippet,
        "_pdf_attachments": pdf_attachments,
    }


def _mark_thread_read(thread_id: str, headers: Dict):
    """Mark all messages in a thread as read via Gmail API."""
    try:
        resp = http_requests.post(
            f"{GMAIL_API_BASE}/threads/{thread_id}/modify",
            headers={**headers, "Content-Type": "application/json"},
            json={"removeLabelIds": ["UNREAD"]},
            timeout=15,
        )
        if resp.status_code == 200:
            logger.info(f"[Poller] Marked thread {thread_id[:20]} as read")
        else:
            logger.warning(f"[Poller] Failed to mark thread read: {resp.status_code}")
    except Exception as e:
        logger.warning(f"[Poller] Error marking thread read: {e}")


# ---------------------------------------------------------------------------
# PDF attachment download + Gemini analysis
# ---------------------------------------------------------------------------

def _download_attachment(message_id: str, attachment_id: str, headers: Dict) -> Optional[bytes]:
    """Download a Gmail attachment and return raw bytes."""
    try:
        resp = http_requests.get(
            f"{GMAIL_API_BASE}/messages/{message_id}/attachments/{attachment_id}",
            headers=headers,
            timeout=30,
        )
        if resp.status_code != 200:
            logger.warning(f"[Poller] Attachment download failed: {resp.status_code}")
            return None
        data = resp.json().get("data", "")
        if not data:
            return None
        return base64.urlsafe_b64decode(data)
    except Exception as e:
        logger.error(f"[Poller] Attachment download error: {e}")
        return None


def analyze_pdf_with_gemini(pdf_bytes: bytes, filename: str = "attachment.pdf") -> Optional[Dict]:
    """
    Send a PDF to Gemini 2.5 Pro to extract settlement amounts.
    Returns {"originalBill": float, "offeredAmount": float, "totalBill": float} or None.
    """
    from turso_client import get_setting
    import os

    api_key = get_setting("gemini_api_key") or os.getenv("GEMINI_API_KEY", "")
    if not api_key:
        logger.warning("[Gemini] No API key configured — skipping PDF analysis")
        return None

    pdf_b64 = base64.standard_b64encode(pdf_bytes).decode("ascii")

    prompt = (
        "Extract exactly three dollar amounts from this legal settlement letter and return "
        "ONLY a valid JSON object with no markdown, no explanation, no extra text.\n\n"
        "Rules:\n"
        '- "originalBill" = the amount billed to the specific patient (labeled as the amount billed to [patient name])\n'
        '- "offeredAmount" = the settlement offer amount made to the provider\n'
        '- "totalBill" = the "Total Medical Bills" amount\n\n'
        "CRITICAL:\n"
        '- Strip any "$" or "$$" symbols before parsing numbers\n'
        "- Preserve decimal points exactly as written (e.g. 41,722.80 → 41722.80, NOT 41722080)\n"
        "- Remove commas from numbers (e.g. 41,722.80 → 41722.80)\n"
        "- Return numbers as JSON numbers, not strings\n\n"
        'Output format (and nothing else):\n'
        '{"originalBill": 0.00, "offeredAmount": 0.00, "totalBill": 0.00}'
    )

    try:
        resp = http_requests.post(
            f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-pro:generateContent?key={api_key}",
            headers={"Content-Type": "application/json"},
            json={
                "contents": [{
                    "parts": [
                        {"inline_data": {"mime_type": "application/pdf", "data": pdf_b64}},
                        {"text": prompt}
                    ]
                }]
            },
            timeout=60,
        )

        if resp.status_code != 200:
            logger.error(f"[Gemini] API error ({resp.status_code}): {resp.text[:300]}")
            return None

        result = resp.json()
        text = result.get("candidates", [{}])[0].get("content", {}).get("parts", [{}])[0].get("text", "")
        if not text:
            logger.warning("[Gemini] Empty response from model")
            return None

        # Clean markdown fences if present
        cleaned = re.sub(r'```json\s*|```\s*', '', text).strip()
        parsed = json.loads(cleaned)
        logger.info(f"[Gemini] PDF analysis result: {parsed}")
        return parsed

    except json.JSONDecodeError as e:
        logger.error(f"[Gemini] Failed to parse response as JSON: {e} — raw: {text[:200]}")
        return None
    except Exception as e:
        logger.error(f"[Gemini] PDF analysis error: {e}")
        return None


def process_thread_attachments(thread_data: Dict) -> List[Dict]:
    """
    Download and analyze all PDF attachments in a thread via Gemini.
    Returns list of analysis results with source message info.
    """
    access_token = _get_api_access_token()
    if not access_token:
        return []

    headers = {"Authorization": f"Bearer {access_token}"}
    results = []

    for msg in thread_data.get("messages", []):
        pdf_atts = msg.get("_pdf_attachments", [])
        if not pdf_atts:
            continue

        msg_id = msg.get("id", "")
        from_addr = msg.get("From", "")

        for att in pdf_atts:
            att_id = att.get("attachmentId", "")
            filename = att.get("filename", "attachment.pdf")
            logger.info(f"[Poller] Downloading PDF '{filename}' from message {msg_id[:15]}")

            pdf_bytes = _download_attachment(msg_id, att_id, headers)
            if not pdf_bytes:
                continue

            logger.info(f"[Poller] Analyzing PDF '{filename}' ({len(pdf_bytes)} bytes) with Gemini")
            analysis = analyze_pdf_with_gemini(pdf_bytes, filename)

            results.append({
                "filename": filename,
                "from": from_addr,
                "message_id": msg_id,
                "size_bytes": len(pdf_bytes),
                "analysis": analysis,  # may be None if Gemini fails
                "_pdf_bytes": pdf_bytes,  # keep raw bytes for upload to CasePeer
            })

    return results


# ---------------------------------------------------------------------------
# Send reply emails (Gmail API first, SMTP fallback)
# ---------------------------------------------------------------------------

def _send_via_gmail_api(gmail_email: str, to_address: str, subject: str,
                        html_body: str, in_reply_to: str = "",
                        references: str = "", thread_id: str = "") -> bool:
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

    # Always append the firm signature
    clean_html += "<br><br>Sincerely,<br>Lien Negotiations Department<br>Beverly Law"

    # Append additional Gmail signature if configured (e.g. contact info, logo)
    signature = get_setting("gmail_signature", "")
    if signature:
        clean_html += f"\n<br><br>{signature}"

    full_html = f'<html><body style="font-family: Arial, sans-serif; font-size: 14px;">\n{clean_html}\n</body></html>'
    msg.attach(MIMEText(full_html, "html"))

    # Base64url-encode the MIME message
    raw_message = base64.urlsafe_b64encode(msg.as_bytes()).decode("ascii")

    # Send via Gmail API (include threadId to keep reply in same thread)
    send_payload = {"raw": raw_message}
    if thread_id:
        send_payload["threadId"] = thread_id

    resp = http_requests.post(
        "https://gmail.googleapis.com/gmail/v1/users/me/messages/send",
        headers={"Authorization": f"Bearer {access_token}", "Content-Type": "application/json"},
        json=send_payload,
    )

    if resp.status_code == 200:
        logger.info(f"[Gmail API] Reply sent to {to_address} | Subject: {msg['Subject']}")
        return True
    else:
        logger.error(f"[Gmail API] Send failed ({resp.status_code}): {resp.text[:300]}")
        return False


def send_reply(gmail_email: str, gmail_password: str,
               to_address: str, subject: str, html_body: str,
               in_reply_to: str = "", references: str = "",
               thread_id: str = "") -> bool:
    """
    Send an HTML email reply. Tries Gmail REST API first (works on Render
    free tier where SMTP ports are blocked), falls back to SMTP.
    """
    # Try Gmail API first (HTTPS, no port restrictions)
    if _send_via_gmail_api(gmail_email, to_address, subject, html_body, in_reply_to, references, thread_id):
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

        # Always append the firm signature
        clean_html += "<br><br>Sincerely,<br>Lien Negotiations Department<br>Beverly Law"

        # Append additional Gmail signature if configured (e.g. contact info, logo)
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

            if not gmail_email:
                logger.error("[Poller] Gmail email not configured")
                _poller_stats["status"] = "error: no credentials"
                await asyncio.sleep(POLL_INTERVAL_SECONDS)
                continue

            logger.info(f"[Poller] Polling for: {sender_filter or '(all unread)'}")

            # Fetch unread threads via Gmail API (runs in thread to avoid blocking)
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
                        # Use RFC Message-ID header for threading (NOT Gmail API id)
                        rfc_msg_id = last_msg.get("Message-ID", "")
                        rfc_references = last_msg.get("References", "")
                        # Build References chain: existing refs + this message's ID
                        if rfc_msg_id:
                            refs = f"{rfc_references} {rfc_msg_id}".strip() if rfc_references else rfc_msg_id
                        else:
                            refs = rfc_references
                        thread_id = thread_data.get("threadId", "")

                        if to_address:
                            logger.info(f"[Poller] Sending reply to: {to_address} | Subject: {subject} | Thread: {thread_id[:15]}")
                            sent = await asyncio.to_thread(
                                send_reply,
                                gmail_email, gmail_password,
                                to_address, subject, reply_message,
                                in_reply_to=rfc_msg_id,
                                references=refs,
                                thread_id=thread_id,
                            )
                            if sent:
                                _poller_stats["emails_replied"] += 1
                            else:
                                logger.error(f"[Poller] Failed to send reply to {to_address}")
                        else:
                            logger.warning("[Poller] No reply-to address found, skipping send")

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
