"""
Workflow: Gmail Auto Follow-up Reminders

Replicates the n8n Gmail Auto Follow-up Reminders workflow.
Checks sent emails for providers that haven't responded in 2+ days
and sends follow-up reminder emails.

Flow:
1. Search Gmail sent folder for sent negotiation emails
2. For each thread, check if the provider has responded
3. If no response in 2+ days, compose and send a follow-up reminder
4. Log reminders in Turso
"""

import asyncio
import base64
import json
import logging
import re
from datetime import datetime, timedelta
from typing import Dict, Any, List, Optional

import requests as http_requests
from openai import OpenAI

logger = logging.getLogger(__name__)

# Days without response before sending a reminder
MIN_DAYS_FOR_REMINDER = 2


async def run_followup_reminders() -> Dict[str, Any]:
    """
    Check sent negotiation emails and send follow-ups for unresponsive providers.
    Returns summary of reminders sent.
    """
    from turso_client import get_setting, turso
    from gmail_poller import _get_api_access_token, send_reply, _get_gmail_creds

    logger.info("[FollowUp] Starting follow-up reminder check")

    access_token = _get_api_access_token()
    if not access_token:
        return {"error": "No Gmail API access token — re-authorize OAuth2"}

    headers = {"Authorization": f"Bearer {access_token}"}
    gmail_email, gmail_password, _ = _get_gmail_creds()

    # 1. Search Gmail sent folder for negotiation-related threads
    query = f"in:sent from:{gmail_email}"
    try:
        resp = http_requests.get(
            "https://gmail.googleapis.com/gmail/v1/users/me/messages",
            headers=headers,
            params={"q": query, "maxResults": 50},
            timeout=30,
        )
        if resp.status_code != 200:
            return {"error": f"Gmail API search failed: {resp.status_code}"}

        messages = resp.json().get("messages", [])
        if not messages:
            return {"reminders_sent": 0, "message": "No sent messages found"}

        logger.info(f"[FollowUp] Found {len(messages)} sent messages to check")
    except Exception as e:
        return {"error": f"Gmail API error: {e}"}

    # 2. Group by thread and analyze each
    thread_ids = list(dict.fromkeys(m["threadId"] for m in messages))
    logger.info(f"[FollowUp] {len(thread_ids)} unique threads to analyze")

    threads_needing_followup = []

    for tid in thread_ids[:30]:  # Cap at 30 threads to avoid overload
        thread_info = await asyncio.to_thread(_analyze_thread, tid, headers, gmail_email)
        if thread_info and thread_info.get("needs_followup"):
            threads_needing_followup.append(thread_info)

    logger.info(f"[FollowUp] {len(threads_needing_followup)} threads need follow-up")

    # 3. Send follow-up reminders
    reminders_sent = []
    for thread_info in threads_needing_followup:
        try:
            # Compose reminder
            reminder_text = _compose_reminder(
                patient_name=thread_info.get("patient_name", "our client"),
                provider_name=thread_info.get("provider_name", ""),
                days_since=thread_info.get("days_since_last", 0),
                reminder_number=thread_info.get("reminder_number", 1),
            )

            to_email = thread_info.get("provider_email", "")
            subject = thread_info.get("subject", "")
            rfc_msg_id = thread_info.get("last_message_id", "")
            thread_id = thread_info.get("thread_id", "")

            if not to_email:
                continue

            sent = await asyncio.to_thread(
                send_reply,
                gmail_email, gmail_password,
                to_email, subject, reminder_text,
                in_reply_to=rfc_msg_id,
                references=rfc_msg_id,
                thread_id=thread_id,
            )

            if sent:
                reminders_sent.append({
                    "provider_email": to_email,
                    "patient_name": thread_info.get("patient_name", ""),
                    "days_since": thread_info.get("days_since_last", 0),
                    "reminder_number": thread_info.get("reminder_number", 1),
                })

                # Log reminder to Turso
                case_id = thread_info.get("case_id", "")
                reminder_num = thread_info.get("reminder_number", 1)
                try:
                    turso.execute(
                        "INSERT INTO reminders (case_id, reminder_number, reminder_date, reminder_email_body) VALUES (?, ?, datetime('now'), ?)",
                        [case_id, reminder_num, reminder_text[:500]]
                    )
                except Exception as e:
                    logger.warning(f"[FollowUp] Failed to log reminder: {e}")

                logger.info(f"[FollowUp] Reminder #{reminder_num} sent to {to_email}")

        except Exception as e:
            logger.error(f"[FollowUp] Error sending reminder: {e}")

    result = {
        "threads_checked": len(thread_ids[:30]),
        "threads_needing_followup": len(threads_needing_followup),
        "reminders_sent": len(reminders_sent),
        "details": reminders_sent,
    }
    logger.info(f"[FollowUp] Complete: {result}")
    return result


def _analyze_thread(thread_id: str, headers: Dict, our_email: str) -> Optional[Dict]:
    """Analyze a Gmail thread to check if follow-up is needed."""
    try:
        resp = http_requests.get(
            f"https://gmail.googleapis.com/gmail/v1/users/me/threads/{thread_id}",
            headers=headers,
            params={"format": "metadata", "metadataHeaders": ["From", "To", "Subject", "Date", "Message-ID"]},
            timeout=30,
        )
        if resp.status_code != 200:
            return None

        thread = resp.json()
        messages = thread.get("messages", [])
        if len(messages) < 1:
            return None

        # Parse message metadata
        parsed = []
        for msg in messages:
            h_map = {}
            for h in msg.get("payload", {}).get("headers", []):
                h_map[h["name"].lower()] = h["value"]

            from_addr = h_map.get("from", "")
            is_us = our_email.lower() in from_addr.lower()
            parsed.append({
                "from": from_addr,
                "to": h_map.get("to", ""),
                "subject": h_map.get("subject", ""),
                "date": h_map.get("date", ""),
                "message_id": h_map.get("message-id", ""),
                "is_us": is_us,
                "internal_date": msg.get("internalDate", "0"),
            })

        if not parsed:
            return None

        last_msg = parsed[-1]
        first_msg = parsed[0]

        # Only follow up if the last message is FROM US (provider hasn't responded)
        if not last_msg["is_us"]:
            return None  # Provider already responded

        # Check how many days since the last message
        try:
            last_date_ms = int(last_msg.get("internal_date", "0") or "0")
            last_date = datetime.fromtimestamp(last_date_ms / 1000)
            days_since = (datetime.now() - last_date).days
        except Exception:
            days_since = 0

        if days_since < MIN_DAYS_FOR_REMINDER:
            return None  # Too soon

        # Extract provider email (recipient of our first message)
        provider_email = ""
        for p in parsed:
            if p["is_us"]:
                # Extract the To address
                to = p.get("to", "")
                email_match = re.search(r'<(.+?)>', to)
                provider_email = email_match.group(1) if email_match else to.strip()
                break

        # Count previous reminders in this thread (our messages after the first)
        our_messages = [p for p in parsed if p["is_us"]]
        reminder_number = len(our_messages)  # Already sent this many

        # Try to extract patient name from subject
        patient_name = ""
        subject = first_msg.get("subject", "")
        name_match = re.search(r'(?:Patient|Client)[:\s]+(.+?)(?:\s*-|\s*$)', subject, re.IGNORECASE)
        if name_match:
            patient_name = name_match.group(1).strip()

        return {
            "thread_id": thread_id,
            "subject": subject,
            "provider_email": provider_email,
            "patient_name": patient_name,
            "days_since_last": days_since,
            "reminder_number": reminder_number,
            "last_message_id": last_msg.get("message_id", ""),
            "needs_followup": True,
            "case_id": "",  # Will be looked up later if needed
        }

    except Exception as e:
        logger.error(f"[FollowUp] Error analyzing thread {thread_id}: {e}")
        return None


def _compose_reminder(patient_name: str, provider_name: str,
                      days_since: int, reminder_number: int) -> str:
    """Compose a follow-up reminder email."""
    ordinal = {1: "first", 2: "second", 3: "third"}.get(reminder_number, f"{reminder_number}th")

    return f"""Dear Sir or Madam,<br><br>
This is a follow-up regarding our previous correspondence concerning our client, <strong>{patient_name}</strong>. It has been {days_since} days since our last communication, and we have not yet received a response.<br><br>
We kindly request that you review our previous offer and respond at your earliest convenience. If you have any questions or need additional information, please do not hesitate to reach out.<br><br>
We look forward to resolving this matter promptly.<br><br>
Sincerely,<br>
Lien Negotiations Department<br>
Beverly Law"""
