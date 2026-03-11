"""
Workflow: Initial Negotiation (Neg0sub)

Replicates the n8n Neg0sub workflow — the smarter way.

Flow:
1. Scrape treatment page → get providers, bills, liens
2. Deduplicate providers by phone
3. For each provider: email balance confirmation request
4. Log to Turso, add case note
5. Trigger sub-workflows if needed

NOTE: This is Step 1 (balance confirmation). We do NOT send an offer yet.
      The offer comes later after the provider confirms the outstanding balance.
"""

import asyncio
import logging
import re
from typing import Dict, Any, List

from casepeer_helpers import (
    get_treatment_providers, lookup_contact_directory,
    add_case_note,
)

logger = logging.getLogger(__name__)

# Providers to exclude from the negotiation process entirely
EXCLUDED_PROVIDERS = ["medicare", "medicaid", "medi-cal"]


def _build_balance_confirmation_email(
    provider_name: str, patient_name: str, patient_dob: str,
    incident_date: str, bill_amount: float,
) -> str:
    """Build HTML email body asking provider to confirm outstanding balance."""
    bill_str = f"${bill_amount:,.2f}" if bill_amount > 0 else "the amount on file"
    dol_display = f" - DOL {incident_date}" if incident_date and incident_date != "N/A" else ""

    return (
        f"Dear {provider_name},<br><br>"
        f"Our office represents <strong>{patient_name}{dol_display}</strong>.<br><br>"
        f"We would like to confirm the outstanding balance for our client's account with your office.<br><br>"
        f"Our records show the total billed amount is <strong>{bill_str}</strong>. "
        f"Could you please confirm the current outstanding balance for this patient?<br><br>"
        f"Thank you for your prompt attention to this matter."
    )


# ---------------------------------------------------------------------------
# Main workflow
# ---------------------------------------------------------------------------

async def run_initial_negotiation(case_id: str) -> Dict[str, Any]:
    """
    Run the initial negotiation workflow for a case.
    Sends balance confirmation email to each provider (no offer yet).
    """
    from turso_client import get_setting
    from gmail_poller import _send_via_gmail_api

    logger.info(f"[InitialNeg] Starting for case {case_id}")

    # 1. Get treatment providers
    treatment_data = await asyncio.to_thread(get_treatment_providers, case_id)
    logger.info(f"[InitialNeg] Treatment data: patient={treatment_data.get('patient_name')}, providers={len(treatment_data.get('providers', []))}")
    if "error" in treatment_data:
        logger.error(f"[InitialNeg] Failed to get treatment data: {treatment_data['error']}")
        return {"error": treatment_data["error"], "case_id": case_id}

    patient_name = treatment_data.get("patient_name", "Unknown")
    patient_dob = treatment_data.get("patient_dob", "N/A")
    incident_date = treatment_data.get("incident_date", "N/A")
    providers = treatment_data.get("providers", [])

    if not providers:
        logger.warning(f"[InitialNeg] No providers found for case {case_id}")
        return {"case_id": case_id, "status": "no_providers", "message": "No providers found on treatment page"}

    logger.info(f"[InitialNeg] Case {case_id}: {len(providers)} providers found, patient={patient_name}")

    # 2. Deduplicate providers by phone
    seen_phones = set()
    unique_providers = []
    for p in providers:
        phone = (p.get("phone") or "").strip()
        if phone and phone in seen_phones:
            logger.info(f"[InitialNeg] Skipping duplicate (same phone): {p['provider_name']}")
            continue
        if phone:
            seen_phones.add(phone)
        unique_providers.append(p)

    logger.info(f"[InitialNeg] After dedup: {len(unique_providers)} unique providers")

    # 2b. Exclude Medicare/Medicaid/Medi-cal providers
    before_exclude = len(unique_providers)
    unique_providers = [
        p for p in unique_providers
        if not any(exc in p["provider_name"].lower() for exc in EXCLUDED_PROVIDERS)
    ]
    excluded_count = before_exclude - len(unique_providers)
    if excluded_count:
        logger.info(f"[InitialNeg] Excluded {excluded_count} Medicare/Medicaid/Medi-cal provider(s)")

    # 3. Look up provider emails and send balance confirmation emails
    gmail_email, gmail_password, _ = _get_gmail_creds()
    recipient_override = get_setting("neg0sub_recipient_override", "")

    sent_list = []
    skipped_list = []

    for provider in unique_providers:
        name = provider["provider_name"]
        bill = provider["bill_amount"]

        # Skip providers with no bill on file
        if bill < 1.0:
            skipped_list.append({"provider": name, "reason": "no bill on file"})
            continue

        # Resolve email
        provider_email = provider.get("email", "")
        provider_address = provider.get("address", "")
        if not provider_email:
            contacts = await asyncio.to_thread(lookup_contact_directory, name)
            if contacts:
                for c in contacts:
                    if c.get("email"):
                        provider_email = c["email"]
                        provider_address = c.get("address", c.get("full_text", ""))
                        break

        send_to = recipient_override if recipient_override else provider_email
        if not send_to:
            skipped_list.append({"provider": name, "reason": "no email found"})
            logger.warning(f"[InitialNeg] No email for {name}, skipping")
            continue

        # Build email body
        email_html = _build_balance_confirmation_email(
            provider_name=name,
            patient_name=patient_name,
            patient_dob=patient_dob,
            incident_date=incident_date,
            bill_amount=bill,
        )

        # Build subject with client name and DOL
        dol_part = f" - DOL {incident_date}" if incident_date and incident_date != "N/A" else ""
        email_subject = f"Balance Confirmation - {patient_name}{dol_part}"

        # BCC the case email so thread shows in CasePeer
        bcc_addr = f"{case_id}@bcc.casepeer.com"

        # Send with retry (up to 3 attempts, 5s delay)
        sent = False
        last_error = None
        for attempt in range(1, 4):
            try:
                sent = await asyncio.to_thread(
                    _send_via_gmail_api,
                    gmail_email, send_to,
                    email_subject,
                    email_html,
                    bcc=bcc_addr,
                )
                if sent:
                    break
                last_error = "send returned False"
            except Exception as e:
                last_error = str(e)
                logger.warning(f"[InitialNeg] Attempt {attempt}/3 failed for {send_to}: {e}")
            if attempt < 3:
                await asyncio.sleep(5)

        if sent:
            sent_list.append({
                "provider": name,
                "email": provider_email or send_to,
                "bill": bill,
            })
            logger.info(f"[InitialNeg] Sent balance confirmation to {send_to} for {name}")
        else:
            skipped_list.append({"provider": name, "reason": f"send failed: {last_error}"})
            logger.error(f"[InitialNeg] Failed to send to {send_to}: {last_error}")

    # 4. Log to Turso + save conversation history for agent continuity
    from turso_client import turso
    import json
    for item in sent_list:
        try:
            turso.execute(
                'INSERT INTO negotiations (case_id, negotiation_type, "to", email_body, date, actual_bill, offered_bill, sent_by_us, result) VALUES (?, ?, ?, ?, datetime(\'now\'), ?, ?, 1, ?)',
                [case_id, "Balance Confirmation", item["email"],
                 f"[{item['provider']}] Balance confirmation email sent",
                 item["bill"], 0.0, "Awaiting Confirmation"]
            )
        except Exception as e:
            logger.error(f"[InitialNeg] Failed to log: {e}")

        # Save initial outbound email to conversation_history so the agent
        # has context when the provider replies (keyed by case_id + provider_email)
        try:
            provider_email = item["email"]
            conv_key = f"{case_id}|{provider_email.lower()}"
            initial_messages = [
                {"role": "system", "content": "Balance confirmation email was sent to this provider."},
                {"role": "assistant", "content": json.dumps({
                    "intent": "initial_outreach",
                    "reply_message": f"Balance confirmation request sent to {item['provider']}",
                    "provider_name": item["provider"],
                    "patient_name": patient_name,
                    "actual_bill": item["bill"],
                    "reasoning": f"Initial balance confirmation email sent. Bill on file: ${item['bill']:,.2f}",
                })}
            ]
            turso.execute(
                "INSERT OR REPLACE INTO conversation_history (id, case_id, sender_email, thread_subject, messages_json, tools_used, last_intent, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?, datetime('now'))",
                [conv_key, case_id, provider_email.lower(), "", json.dumps(initial_messages), "[]", "initial_outreach"]
            )
            logger.info(f"[InitialNeg] Saved conversation history for case {case_id} | {provider_email}")
        except Exception as e:
            logger.error(f"[InitialNeg] Failed to save conversation history: {e}")

    # 5. Add case note
    note = f"Balance confirmation requests sent to {len(sent_list)} provider(s). "
    if skipped_list:
        note += f"{len(skipped_list)} skipped."
    await asyncio.to_thread(add_case_note, case_id, note)

    result = {
        "case_id": case_id,
        "patient_name": patient_name,
        "confirmations_sent": len(sent_list),
        "skipped": len(skipped_list),
        "details": sent_list,
        "skipped_details": skipped_list,
    }

    # 6. Sub-workflows disabled for now (thirdparty, get_mail_sub)
    # try:
    #     from workflow_scheduler import trigger_workflow
    #     await trigger_workflow("thirdparty", case_id, triggered_by="initial_negotiation")
    #     await trigger_workflow("get_mail_sub", case_id, triggered_by="initial_negotiation")
    # except Exception as e:
    #     logger.warning(f"[InitialNeg] Failed to trigger sub-workflows: {e}")

    logger.info(f"[InitialNeg] Done for case {case_id}: {len(sent_list)} sent, {len(skipped_list)} skipped")
    return result


def _get_gmail_creds():
    """Get Gmail credentials."""
    from gmail_poller import _get_gmail_creds as gc
    return gc()
