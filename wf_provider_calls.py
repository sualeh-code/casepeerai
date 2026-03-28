"""
Workflow: Provider Email Calls (Vapi Webhook-Based)

For each provider on a case, initiates Vapi AI phone calls to confirm/obtain
email addresses. Replaces polling-based wf_get_mail_sub.py with webhook-driven
approach.

Flow:
1. Get treatment providers for a case
2. Filter: skip excluded providers, skip already-handled
3. For each provider with a phone number:
   - Create provider_calls DB record
   - Initiate Vapi outbound call with dynamic firstMessage + metadata
   - Return immediately (webhook handles results asynchronously)
"""

import asyncio
import json
import logging
import os
import re
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

import requests as http_requests

from casepeer_helpers import (
    get_treatment_providers, lookup_contact_directory, add_case_note,
)
from turso_client import (
    get_setting, turso, normalize_phone,
    create_provider_call, update_provider_call,
)

logger = logging.getLogger(__name__)

EXCLUDED_PROVIDERS = ["medicare", "medicaid", "medi-cal"]

# Business hours: M-F 8am-5pm Pacific Time
BUSINESS_HOUR_START = 8   # 8:00 AM PT
BUSINESS_HOUR_END = 17    # 5:00 PM PT
PT_OFFSET = timedelta(hours=-7)  # PDT (UTC-7); PST would be -8

# Max call duration (5 minutes) to prevent cost overruns on hold
MAX_CALL_DURATION_SECONDS = 300


def _now_pt() -> datetime:
    """Get current time in approximate Pacific Time."""
    return datetime.utcnow() + PT_OFFSET


def is_business_hours() -> bool:
    """Check if current time is within business hours (M-F 8am-5pm PT)."""
    now = _now_pt()
    if now.weekday() >= 5:  # Saturday=5, Sunday=6
        return False
    return BUSINESS_HOUR_START <= now.hour < BUSINESS_HOUR_END


def next_business_window() -> str:
    """Return ISO datetime (UTC) of the next business hour window opening."""
    now_utc = datetime.utcnow()
    now = _now_pt()
    # Start from next possible opening
    target = now.replace(hour=BUSINESS_HOUR_START, minute=0, second=0, microsecond=0)
    if now.hour >= BUSINESS_HOUR_START:
        # Already past today's start, try tomorrow
        target += timedelta(days=1)
    # Skip weekends
    while target.weekday() >= 5:
        target += timedelta(days=1)
    # Convert back to UTC
    target_utc = target - PT_OFFSET
    return target_utc.strftime("%Y-%m-%dT%H:%M:%SZ")


# ---------------------------------------------------------------------------
# Main workflow entry point
# ---------------------------------------------------------------------------
async def run_provider_calls(case_id: str) -> Dict[str, Any]:
    """
    Initiate provider email confirmation calls for a case.
    Does NOT wait for completion — webhook handles results.
    """
    logger.info(f"[ProviderCalls] Starting for case {case_id}")

    vapi_api_key = get_setting("vapi_api_key") or os.getenv("VAPI_API_KEY", "")
    vapi_assistant_id = get_setting("vapi_assistant_id") or os.getenv("VAPI_ASSISTANT_ID", "")
    vapi_phone_id = get_setting("vapi_phone_id") or os.getenv("VAPI_PHONE_ID", "")

    if not vapi_api_key:
        return {"error": "Vapi API key not configured", "case_id": case_id}
    if not vapi_assistant_id:
        return {"error": "Vapi assistant ID not configured", "case_id": case_id}
    if not vapi_phone_id:
        return {"error": "Vapi phone ID not configured", "case_id": case_id}

    # 1. Get providers
    treatment_data = await asyncio.to_thread(get_treatment_providers, case_id)
    if "error" in treatment_data:
        return {"error": treatment_data["error"], "case_id": case_id}

    providers = treatment_data.get("providers", [])
    patient_name = treatment_data.get("patient_name", "Unknown")
    patient_dob = treatment_data.get("patient_dob", "")
    incident_date = treatment_data.get("incident_date", "")

    if not providers:
        return {"case_id": case_id, "calls_initiated": 0, "message": "No providers found"}

    # 2. Check for existing pending calls (avoid duplicates)
    existing = turso.fetch_all(
        """SELECT provider_name, provider_phone, email_status
           FROM provider_calls
           WHERE case_id = ? AND email_status IN ('pending', 'confirmed', 'new_email')""",
        [case_id]
    )
    already_handled = set()
    for r in existing:
        key = (r["provider_name"], r.get("provider_phone") or "")
        already_handled.add(key)

    # 3. Check business hours — schedule if outside window
    outside_hours = not is_business_hours()
    next_window = next_business_window() if outside_hours else ""
    if outside_hours:
        logger.info(f"[ProviderCalls] Outside business hours, scheduling for {next_window}")

    # 4. Initiate calls
    calls_initiated = []
    calls_skipped = []

    for p in providers:
        name = p["provider_name"]
        phone = p.get("phone", "")
        email = p.get("email", "")

        # Skip excluded providers
        if any(excl in name.lower() for excl in EXCLUDED_PROVIDERS):
            calls_skipped.append({"provider": name, "reason": "excluded_provider"})
            continue

        # Skip already handled
        norm_phone = normalize_phone(phone) if phone else ""
        if (name, norm_phone) in already_handled:
            calls_skipped.append({"provider": name, "reason": "already_handled"})
            continue

        # Try contact directory if no phone
        if not phone:
            contacts = await asyncio.to_thread(lookup_contact_directory, name)
            for c in contacts:
                if c.get("phone"):
                    phone = c["phone"]
                    break

        if not phone:
            calls_skipped.append({"provider": name, "reason": "no_phone"})
            continue

        # Create DB record (scheduled if outside business hours)
        call_db_id = create_provider_call(
            case_id=case_id,
            provider_name=name,
            provider_phone=phone,
            existing_email=email or None,
            call_type="outbound_confirm",
            scheduled_at=next_window if outside_hours else None,
        )

        if not call_db_id:
            calls_skipped.append({"provider": name, "reason": "db_error"})
            continue

        # If outside business hours, just schedule — don't dial
        if outside_hours:
            calls_initiated.append({
                "provider": name, "phone": phone,
                "scheduled_at": next_window, "db_id": call_db_id,
            })
            logger.info(f"[ProviderCalls] Call scheduled for {name} at {next_window}")
            continue

        # Initiate Vapi call
        try:
            vapi_call_id = await asyncio.to_thread(
                _initiate_vapi_call,
                vapi_api_key, vapi_assistant_id, vapi_phone_id,
                case_id, name, patient_name, phone, email, call_db_id,
                patient_dob, incident_date,
            )
            if vapi_call_id:
                update_provider_call(call_db_id, vapi_call_id=vapi_call_id, status="ringing")
                calls_initiated.append({
                    "provider": name, "phone": phone,
                    "vapi_call_id": vapi_call_id, "db_id": call_db_id,
                })
                logger.info(f"[ProviderCalls] Call initiated for {name}: {vapi_call_id}")
            else:
                update_provider_call(call_db_id, status="failed", end_reason="api_error")
                calls_skipped.append({"provider": name, "reason": "vapi_api_error"})
        except Exception as e:
            logger.error(f"[ProviderCalls] Failed to call {name}: {e}")
            update_provider_call(call_db_id, status="failed", end_reason=str(e)[:200])
            calls_skipped.append({"provider": name, "reason": str(e)[:100]})

    # Add case note
    if calls_initiated:
        note = f"Vapi calls initiated for {len(calls_initiated)} provider(s): "
        note += ", ".join(c["provider"] for c in calls_initiated)
        await asyncio.to_thread(add_case_note, case_id, note)

    result = {
        "case_id": case_id,
        "patient_name": patient_name,
        "calls_initiated": len(calls_initiated),
        "calls_skipped": len(calls_skipped),
        "initiated": calls_initiated,
        "skipped": calls_skipped,
    }
    logger.info(f"[ProviderCalls] Complete: {len(calls_initiated)} initiated, {len(calls_skipped)} skipped")
    return result


# ---------------------------------------------------------------------------
# Single call initiation (also used by retry/scheduled calls)
# ---------------------------------------------------------------------------
async def make_provider_call(case_id: str, provider_name: str,
                             provider_phone: str, existing_email: str = None,
                             call_type: str = "outbound_followup",
                             attempt_number: int = 1) -> Optional[str]:
    """Initiate a single Vapi call for a provider. Returns vapi_call_id or None.
    Respects business hours — schedules for next window if outside M-F 8am-5pm PT.
    """
    # Business hours gate
    if not is_business_hours():
        nw = next_business_window()
        logger.info(f"[ProviderCalls] Outside business hours, scheduling {provider_name} for {nw}")
        call_db_id = create_provider_call(
            case_id=case_id,
            provider_name=provider_name,
            provider_phone=provider_phone,
            existing_email=existing_email,
            call_type=call_type,
            attempt_number=attempt_number,
            scheduled_at=nw,
        )
        return None  # Not dialed now

    vapi_api_key = get_setting("vapi_api_key", "")
    vapi_assistant_id = get_setting("vapi_assistant_id", "")
    vapi_phone_id = get_setting("vapi_phone_id", "")

    if not all([vapi_api_key, vapi_assistant_id, vapi_phone_id]):
        logger.error("[ProviderCalls] Vapi settings not configured for make_provider_call")
        return None

    # Get patient context
    treatment_data = await asyncio.to_thread(get_treatment_providers, case_id)
    patient_name = treatment_data.get("patient_name", "our client")
    patient_dob = treatment_data.get("patient_dob", "")
    incident_date = treatment_data.get("incident_date", "")

    call_db_id = create_provider_call(
        case_id=case_id,
        provider_name=provider_name,
        provider_phone=provider_phone,
        existing_email=existing_email,
        call_type=call_type,
        attempt_number=attempt_number,
    )

    if not call_db_id:
        return None

    vapi_call_id = await asyncio.to_thread(
        _initiate_vapi_call,
        vapi_api_key, vapi_assistant_id, vapi_phone_id,
        case_id, provider_name, patient_name,
        provider_phone, existing_email or "", call_db_id,
        patient_dob, incident_date,
    )

    if vapi_call_id:
        update_provider_call(call_db_id, vapi_call_id=vapi_call_id, status="ringing")
    else:
        update_provider_call(call_db_id, status="failed", end_reason="api_error")

    return vapi_call_id


def _initiate_vapi_call(api_key: str, assistant_id: str, phone_id: str,
                        case_id: str, provider_name: str, patient_name: str,
                        phone: str, existing_email: str,
                        provider_call_db_id: int,
                        patient_dob: str = "", incident_date: str = "") -> Optional[str]:
    """
    Initiate a Vapi outbound call. Returns vapi_call_id or None.
    Does NOT wait for completion — webhook handles the rest.
    """
    phone_clean = normalize_phone(phone)
    if not phone_clean:
        return None

    # Debug override: dial a test number instead of the real provider
    override_phone = get_setting("debug_override_phone", "")
    if override_phone:
        dial_number = normalize_phone(override_phone)
        logger.info(f"[ProviderCalls] DEBUG override: dialing {dial_number} instead of {phone_clean}")
    else:
        dial_number = phone_clean

    # Dynamic first message based on email status
    # Recording consent disclosure (California two-party consent)
    recording_disclosure = "This call may be recorded for quality assurance. "

    if existing_email:
        first_message = (
            f"Hi, this is Alferd calling from Beverly Law Firm regarding our client {patient_name}. "
            f"{recording_disclosure}"
            f"I'm reaching out to the billing department at {provider_name}. "
            f"We have {existing_email} on file as your email address for correspondence. "
            f"Can you confirm this is the best email to send correspondence regarding our client's account?"
        )
    else:
        first_message = (
            f"Hi, this is Alferd calling from Beverly Law Firm regarding our client {patient_name}. "
            f"{recording_disclosure}"
            f"I'm reaching out to the billing department at {provider_name}. "
            f"Could you please provide us with the best email address to send "
            f"correspondence regarding our client's account?"
        )

    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }

    payload = {
        "assistantId": assistant_id,
        "phoneNumberId": phone_id,
        "customer": {"number": dial_number},
        "maxDurationSeconds": MAX_CALL_DURATION_SECONDS,
        "assistantOverrides": {
            "firstMessage": first_message,
            "voicemailDetection": {
                "enabled": True,
                "provider": "twilio",
                "voicemailDetectionTypes": ["machine_end_beep", "machine_end_silence"],
                "machineDetectionTimeout": 8,
            },
            "metadata": {
                "provider_call_id": str(provider_call_db_id),
                "case_id": case_id,
                "provider_name": provider_name,
                "provider_phone": phone_clean,
                "existing_email": existing_email or "",
                "patient_name": patient_name,
                "patient_dob": patient_dob,
                "incident_date": incident_date,
            },
        },
    }

    try:
        resp = http_requests.post(
            "https://api.vapi.ai/call/phone",
            headers=headers,
            json=payload,
            timeout=30,
        )
        if resp.status_code in (200, 201):
            call_data = resp.json()
            return call_data.get("id", "")
        else:
            logger.error(f"[ProviderCalls] Vapi API error: {resp.status_code} - {resp.text[:200]}")
            return None
    except Exception as e:
        logger.error(f"[ProviderCalls] Vapi call request failed: {e}")
        return None


# ---------------------------------------------------------------------------
# Email extraction from transcript
# ---------------------------------------------------------------------------
def extract_email_from_transcript(transcript: str) -> str:
    """
    Extract email from transcript. Handles:
    - Standard email regex (billing@clinic.com)
    - Spoken format ("X at Y dot com")
    - Letter-by-letter / NATO phonetic spelling ("B as in boy, I, L, L...")
    """
    if not transcript:
        return ""

    # 1. Direct regex match
    match = re.search(r'[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}', transcript)
    if match:
        return match.group(0).lower()

    # 2. Spoken format: "X at Y dot com"
    spoken = re.search(
        r'([a-zA-Z0-9._-]+(?:\s+(?:dot|period)\s+[a-zA-Z0-9._-]+)*)'
        r'\s+at\s+'
        r'([a-zA-Z0-9._-]+(?:\s+(?:dot|period)\s+[a-zA-Z0-9._-]+)*)'
        r'\s+(?:dot|period)\s+(com|org|net|edu|gov|io|co)',
        transcript, re.IGNORECASE
    )
    if spoken:
        local_part = spoken.group(1).replace(" dot ", ".").replace(" period ", ".")
        domain_part = spoken.group(2).replace(" dot ", ".").replace(" period ", ".")
        tld = spoken.group(3)
        return f"{local_part}@{domain_part}.{tld}".lower().replace(" ", "")

    # 3. Letter-by-letter / NATO phonetic spelling
    #    Handles: "B as in boy, I, L, L" or "alpha bravo charlie at..."
    email = _extract_spelled_email(transcript)
    if email:
        return email

    return ""


# NATO phonetic alphabet → letter mapping
_NATO_MAP = {
    "alpha": "a", "bravo": "b", "charlie": "c", "delta": "d", "echo": "e",
    "foxtrot": "f", "golf": "g", "hotel": "h", "india": "i", "juliet": "j",
    "kilo": "k", "lima": "l", "mike": "m", "november": "n", "oscar": "o",
    "papa": "p", "quebec": "q", "romeo": "r", "sierra": "s", "tango": "t",
    "uniform": "u", "victor": "v", "whiskey": "w", "x-ray": "x", "xray": "x",
    "yankee": "y", "zulu": "z",
}

# Common "as in" words → letter
_AS_IN_MAP = {
    "apple": "a", "adam": "a", "able": "a",
    "boy": "b", "baker": "b", "bob": "b", "bravo": "b",
    "cat": "c", "charlie": "c", "candy": "c", "carol": "c",
    "dog": "d", "david": "d", "delta": "d", "dan": "d",
    "edward": "e", "echo": "e", "egg": "e",
    "frank": "f", "fox": "f", "foxtrot": "f",
    "george": "g", "golf": "g",
    "henry": "h", "hotel": "h", "harry": "h",
    "ida": "i", "india": "i", "ice": "i",
    "john": "j", "jack": "j", "juliet": "j",
    "king": "k", "kilo": "k",
    "larry": "l", "lima": "l", "lincoln": "l",
    "mary": "m", "mike": "m", "michael": "m",
    "nancy": "n", "november": "n", "nora": "n",
    "ocean": "o", "oscar": "o", "oliver": "o",
    "paul": "p", "peter": "p", "papa": "p",
    "queen": "q", "quebec": "q",
    "robert": "r", "romeo": "r", "roger": "r",
    "sam": "s", "sierra": "s", "sugar": "s", "steven": "s",
    "tom": "t", "tango": "t", "thomas": "t", "tiger": "t",
    "uncle": "u", "uniform": "u",
    "victor": "v", "victoria": "v",
    "william": "w", "whiskey": "w",
    "yellow": "y", "yankee": "y",
    "zebra": "z", "zulu": "z",
}


def _extract_spelled_email(transcript: str) -> str:
    """
    Try to extract email from letter-by-letter or NATO phonetic spelling.
    Patterns like: "B as in boy, I, L, L, I, N, G at provider dot com"
    """
    t = transcript.lower()

    # Look for "at" separator between local and domain parts
    at_match = re.search(r'\bat\b', t)
    if not at_match:
        return ""

    before_at = t[:at_match.start()]
    after_at = t[at_match.end():]

    # Check if "dot com/org/net/..." exists after "at"
    domain_match = re.search(
        r'(.+?)\s+(?:dot|period|\.)\s+(com|org|net|edu|gov|io|co)\b',
        after_at, re.IGNORECASE,
    )
    if not domain_match:
        return ""

    domain_raw = domain_match.group(1).strip()
    tld = domain_match.group(2)

    # Only proceed if the before-at portion looks like spelled letters
    # (contains "as in", comma-separated single letters, or NATO words)
    has_spelling = bool(re.search(r'\bas\s+in\b', before_at)) or \
                   bool(re.search(r'\b[a-z]\s*,\s*[a-z]\b', before_at)) or \
                   any(word in before_at.split() for word in _NATO_MAP)

    if not has_spelling:
        return ""

    local = _decode_spelled_segment(before_at)
    domain = _decode_spelled_segment(domain_raw)

    if local and domain:
        email = f"{local}@{domain}.{tld}".lower()
        # Basic sanity check
        if re.match(r'^[a-z0-9._+-]+@[a-z0-9.-]+\.[a-z]{2,}$', email):
            return email
    return ""


def _decode_spelled_segment(text: str) -> str:
    """Decode a spelled-out segment into actual characters."""
    result = []
    # Split on commas, spaces, "and"
    tokens = re.split(r'[,\s]+', text.strip())
    i = 0
    while i < len(tokens):
        token = tokens[i].lower().strip(".,;:")
        if not token:
            i += 1
            continue

        # "as in X" pattern → take the first letter of X
        if token == "as" and i + 2 < len(tokens) and tokens[i + 1].lower() == "in":
            word = tokens[i + 2].lower().strip(".,;:")
            letter = _AS_IN_MAP.get(word, word[0] if word else "")
            result.append(letter)
            i += 3
            continue

        # Single letter
        if len(token) == 1 and token.isalpha():
            result.append(token)
            i += 1
            continue

        # NATO phonetic word
        if token in _NATO_MAP:
            result.append(_NATO_MAP[token])
            i += 1
            continue

        # "dot" or "period" → literal "."
        if token in ("dot", "period"):
            result.append(".")
            i += 1
            continue

        # "dash" or "hyphen" → literal "-"
        if token in ("dash", "hyphen"):
            result.append("-")
            i += 1
            continue

        # "underscore" → "_"
        if token == "underscore":
            result.append("_")
            i += 1
            continue

        # Number
        if token.isdigit():
            result.append(token)
            i += 1
            continue

        # Skip filler words
        if token in ("and", "then", "the", "letter", "like", "for", "number"):
            i += 1
            continue

        # Unknown — treat as literal if short
        if len(token) <= 3:
            result.append(token)
        i += 1

    return "".join(result)


# ---------------------------------------------------------------------------
# Callback time parsing
# ---------------------------------------------------------------------------
def parse_callback_time(time_str: str) -> str:
    """
    Parse natural language callback time into ISO datetime string.
    Examples: "3pm", "3:00 PM", "tomorrow morning", "in 2 hours"
    Uses Pacific Time (law firm timezone).
    """
    now = datetime.utcnow()
    # Approximate PT offset (UTC-7 for PDT, UTC-8 for PST)
    pt_offset = timedelta(hours=-7)
    now_pt = now + pt_offset

    time_lower = time_str.lower().strip()

    # "in X hours"
    match = re.search(r'in\s+(\d+)\s+hours?', time_lower)
    if match:
        hours = int(match.group(1))
        target = now + timedelta(hours=hours)
        return target.strftime("%Y-%m-%dT%H:%M:%SZ")

    # "tomorrow morning/afternoon"
    if "tomorrow" in time_lower:
        target_pt = now_pt + timedelta(days=1)
        if "afternoon" in time_lower:
            target_pt = target_pt.replace(hour=14, minute=0, second=0, microsecond=0)
        else:
            target_pt = target_pt.replace(hour=10, minute=0, second=0, microsecond=0)
        # Convert back to UTC
        target_utc = target_pt - pt_offset
        return target_utc.strftime("%Y-%m-%dT%H:%M:%SZ")

    # "3pm", "3:00 PM", "15:00"
    time_match = re.search(r'(\d{1,2})(?::(\d{2}))?\s*(am|pm)?', time_lower)
    if time_match:
        hour = int(time_match.group(1))
        minute = int(time_match.group(2) or 0)
        ampm = time_match.group(3)
        if ampm == "pm" and hour < 12:
            hour += 12
        elif ampm == "am" and hour == 12:
            hour = 0
        target_pt = now_pt.replace(hour=hour, minute=minute, second=0, microsecond=0)
        if target_pt <= now_pt:
            target_pt += timedelta(days=1)
        # Skip weekends
        while target_pt.weekday() >= 5:
            target_pt += timedelta(days=1)
        target_utc = target_pt - pt_offset
        return target_utc.strftime("%Y-%m-%dT%H:%M:%SZ")

    # Fallback: 2 hours from now
    target = now + timedelta(hours=2)
    return target.strftime("%Y-%m-%dT%H:%M:%SZ")
