"""
Workflow: Get Mail Sub (Vapi Phone Calls)

Replicates the n8n Get Mail Sub workflow.
Uses Vapi AI phone calls to retrieve provider email addresses
when they can't be found in the contact directory.

Flow:
1. Get treatment providers for a case
2. Filter providers missing email addresses
3. For each, initiate a Vapi AI phone call to request email
4. Wait for call completion and extract email from transcript
5. Update provider contact info in CasePeer
"""

import asyncio
import json
import logging
import re
import time
from typing import Dict, Any, List, Optional

import requests as http_requests

from casepeer_helpers import (
    get_treatment_providers, lookup_contact_directory,
    add_case_note,
)

logger = logging.getLogger(__name__)


async def run_get_mail_sub(case_id: str) -> Dict[str, Any]:
    """
    For providers missing email addresses, make Vapi AI phone calls
    to retrieve their email.
    """
    from turso_client import get_setting
    import os

    logger.info(f"[GetMailSub] Starting for case {case_id}")

    vapi_api_key = get_setting("vapi_api_key") or os.getenv("VAPI_API_KEY", "")
    vapi_assistant_id = get_setting("vapi_assistant_id") or os.getenv("VAPI_ASSISTANT_ID", "")
    vapi_phone_id = get_setting("vapi_phone_id") or os.getenv("VAPI_PHONE_ID", "")

    if not vapi_api_key:
        return {"error": "Vapi API key not configured (set vapi_api_key in settings)", "case_id": case_id}

    # 1. Get providers for the case
    treatment_data = await asyncio.to_thread(get_treatment_providers, case_id)
    if "error" in treatment_data:
        return {"error": treatment_data["error"], "case_id": case_id}

    providers = treatment_data.get("providers", [])
    patient_name = treatment_data.get("patient_name", "Unknown")

    # 2. Filter providers missing email
    providers_needing_email = []
    for p in providers:
        if p.get("email"):
            continue
        # Try contact directory first
        contacts = await asyncio.to_thread(lookup_contact_directory, p["provider_name"])
        found_email = False
        for c in contacts:
            if c.get("email"):
                found_email = True
                p["email"] = c["email"]
                break
        if not found_email and p.get("phone"):
            providers_needing_email.append(p)

    if not providers_needing_email:
        return {
            "case_id": case_id,
            "calls_made": 0,
            "message": "All providers already have email addresses",
        }

    logger.info(f"[GetMailSub] {len(providers_needing_email)} providers need email lookup via phone")

    # 3. Make Vapi calls for each provider
    calls_made = []
    calls_failed = []

    for provider in providers_needing_email:
        phone = provider.get("phone", "")
        name = provider["provider_name"]

        if not phone:
            calls_failed.append({"provider": name, "reason": "no phone number"})
            continue

        try:
            result = await asyncio.to_thread(
                _make_vapi_call,
                vapi_api_key, vapi_assistant_id, vapi_phone_id,
                phone, name, patient_name,
            )

            if result and result.get("email"):
                calls_made.append({
                    "provider": name,
                    "phone": phone,
                    "email_found": result["email"],
                    "call_id": result.get("call_id", ""),
                })
                logger.info(f"[GetMailSub] Found email for {name}: {result['email']}")
            else:
                calls_failed.append({
                    "provider": name,
                    "phone": phone,
                    "reason": result.get("error", "no email in transcript"),
                })

        except Exception as e:
            logger.error(f"[GetMailSub] Vapi call failed for {name}: {e}")
            calls_failed.append({"provider": name, "reason": str(e)})

    # 4. Add case note
    if calls_made:
        note = f"Vapi phone calls: Found emails for {len(calls_made)} provider(s). "
        for c in calls_made:
            note += f"{c['provider']}: {c['email_found']}. "
        await asyncio.to_thread(add_case_note, case_id, note)

    result = {
        "case_id": case_id,
        "calls_made": len(calls_made),
        "calls_failed": len(calls_failed),
        "emails_found": calls_made,
        "failures": calls_failed,
    }
    logger.info(f"[GetMailSub] Complete: {result}")
    return result


def _make_vapi_call(api_key: str, assistant_id: str, phone_id: str,
                    phone_number: str, provider_name: str,
                    patient_name: str) -> Optional[Dict]:
    """
    Initiate a Vapi AI phone call and wait for completion.
    Returns {"email": "...", "call_id": "..."} or {"error": "..."}.
    """
    if not assistant_id or not phone_id:
        return {"error": "Vapi assistant_id or phone_id not configured"}

    # Clean phone number (ensure it has country code)
    phone_clean = re.sub(r'[^0-9+]', '', phone_number)
    if not phone_clean.startswith("+"):
        phone_clean = f"+1{phone_clean}"  # Default to US

    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }

    # Create the call
    try:
        resp = http_requests.post(
            "https://api.vapi.ai/call/phone",
            headers=headers,
            json={
                "assistantId": assistant_id,
                "phoneNumberId": phone_id,
                "customer": {"number": phone_clean},
                "assistantOverrides": {
                    "firstMessage": (
                        f"Hi, this is Beverly Law calling regarding our client {patient_name}. "
                        f"I'm reaching out to the billing department at {provider_name}. "
                        f"Could you please provide us with the best email address to send "
                        f"correspondence regarding {patient_name}'s account?"
                    ),
                },
            },
            timeout=30,
        )

        if resp.status_code not in (200, 201):
            return {"error": f"Vapi API error: {resp.status_code} - {resp.text[:200]}"}

        call_data = resp.json()
        call_id = call_data.get("id", "")

        if not call_id:
            return {"error": "No call ID returned from Vapi"}

        # Wait for call to complete (poll every 10 seconds, max 3 minutes)
        for _ in range(18):
            time.sleep(10)
            status_resp = http_requests.get(
                f"https://api.vapi.ai/call/{call_id}",
                headers=headers,
                timeout=15,
            )
            if status_resp.status_code != 200:
                continue

            call_status = status_resp.json()
            if call_status.get("status") in ("ended", "completed"):
                # Extract email from transcript
                transcript = call_status.get("transcript", "")
                email = _extract_email_from_transcript(transcript)
                return {"email": email, "call_id": call_id}

        return {"error": "Call timed out after 3 minutes", "call_id": call_id}

    except Exception as e:
        return {"error": str(e)}


def _extract_email_from_transcript(transcript: str) -> str:
    """Extract an email address from a phone call transcript."""
    if not transcript:
        return ""
    # Look for email patterns
    email_match = re.search(r'[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}', transcript)
    return email_match.group(0) if email_match else ""
