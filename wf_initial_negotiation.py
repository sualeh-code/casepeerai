"""
Workflow: Initial Negotiation (Neg0sub)

Replicates the n8n Neg0sub workflow.
For a given case, sends initial settlement offers to all providers.

Flow:
1. Scrape treatment page → get providers, bills, liens
2. Calculate offers (MRI=$400, X-Ray=$50, others=2/3 of 33%)
3. Deduplicate providers by phone
4. Look up provider emails from contact directory
5. Generate offer letter documents via CasePeer
6. Send initial offer emails to each provider
7. Log negotiations to Turso
8. Add case notes
9. Trigger sub-workflows (thirdparty, get-mail-sub) if needed
"""

import asyncio
import json
import logging
import re
from datetime import datetime
from typing import Dict, Any, List

from casepeer_helpers import (
    casepeer_get, casepeer_get_raw, extract_html,
    get_treatment_providers, lookup_contact_directory,
    add_case_note, parse_dollar_amount, get_local_base,
)

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Beverly Law letterhead for emails
# ---------------------------------------------------------------------------

BEVERLY_LAW_HEADER = """Beverly Law<br>
4929 Wilshire Blvd, Suite 960<br>
Los Angeles, CA 90010<br><br>
Tel: 310-552-6959<br>
Fax: 323-421-9397<br><br>
<em>*Please note our new office address in your file*</em><br><br>"""


def _build_offer_email(provider_name: str, provider_address: str,
                       patient_name: str, patient_dob: str, incident_date: str,
                       offered_amount: str, total_bill: str,
                       gmail_email: str) -> str:
    """Build the initial offer email HTML body (matches n8n template)."""
    today = datetime.now().strftime("%B %d, %Y")
    return f"""{BEVERLY_LAW_HEADER}
{today}<br><br>
VIA EMAIL<br><br>
{provider_name}:<br>
{provider_address}<br><br>
RE: Our Client/Your Patient: {patient_name}<br><br>
Date of Birth: {patient_dob}<br>
Date of Injury: {incident_date}<br><br>
Dear Sir or Madam:<br><br>
Thank you for sending over the bills and reports for {patient_name} to our office. We are in the process of negotiating with the Insurance Company and at the current time would like to discuss settlement of the medical bills with your office. Based on the total medical bills and circumstances our client has allowed us to offer <strong>{offered_amount}</strong>. The total that you have billed {patient_name} for this case is: <strong>{total_bill}</strong>. Please confirm the outstanding balance for this patient.<br><br>
Please either fax back this letter with your initials of acceptance of the offer below or call the undersigned to discuss the settlement of this case a little further. Thank you for your partnership.<br><br>
X________________ Acceptance of offer.<br>
Authorized Representative of Provider.<br><br>
Regards,<br>
<strong>BEVERLY LAW</strong><br><br>
Please scan and EMAIL back this letter with your initials of acceptance of the offer below to email {gmail_email}. Please do not fax back this letter. Thank you for your partnership. Keep in mind we're still negotiating with other providers and insurance companies.<br><br>
X________________ Acceptance of offer.<br>
Authorized Representative of Provider.<br><br>
********Please Confirm Payment address here:__________________________________________________"""


# ---------------------------------------------------------------------------
# Main workflow
# ---------------------------------------------------------------------------

async def run_initial_negotiation(case_id: str) -> Dict[str, Any]:
    """
    Run the initial negotiation workflow for a case.
    Returns summary of offers sent.
    """
    from turso_client import get_setting
    from gmail_poller import send_reply

    logger.info(f"[InitialNeg] Starting for case {case_id}")

    # 1. Get treatment providers with offer calculations
    treatment_data = await asyncio.to_thread(get_treatment_providers, case_id)
    if "error" in treatment_data:
        return {"error": treatment_data["error"], "case_id": case_id}

    patient_name = treatment_data.get("patient_name", "Unknown")
    patient_dob = treatment_data.get("patient_dob", "N/A")
    incident_date = treatment_data.get("incident_date", "N/A")
    providers = treatment_data.get("providers", [])
    offer_letter_id = treatment_data.get("offer_letter_template_id", "")

    if not providers:
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

    # 3. Generate offer letter documents via CasePeer (if template found)
    if offer_letter_id:
        lien_ids = [p["lien_id"] for p in unique_providers if p.get("lien_id")]
        if lien_ids:
            ids_str = ",".join(lien_ids)
            try:
                doc_url = f"autoletters/CaseGenerateLetter/{ids_str}/{offer_letter_id}/{case_id}"
                await asyncio.to_thread(casepeer_get_raw, doc_url)
                logger.info(f"[InitialNeg] Generated offer letters for {len(lien_ids)} providers")
            except Exception as e:
                logger.warning(f"[InitialNeg] Failed to generate letter documents: {e}")

    # 4. Look up provider emails from contact directory and send offers
    gmail_email, gmail_password, _ = _get_gmail_creds()
    recipient_override = get_setting("neg0sub_recipient_override", "")

    offers_sent = []
    offers_skipped = []

    for provider in unique_providers:
        name = provider["provider_name"]
        bill = provider["bill_amount"]
        offered = provider["offered_amount"]

        # Skip zero or very small bills
        if bill < 1.0:
            offers_skipped.append({"provider": name, "reason": "bill < $1"})
            continue

        # Look up email from contact directory
        provider_email = provider.get("email", "")
        provider_address = ""
        if not provider_email:
            contacts = await asyncio.to_thread(lookup_contact_directory, name)
            if contacts:
                for c in contacts:
                    if c.get("email"):
                        provider_email = c["email"]
                        provider_address = c.get("address", c.get("full_text", ""))
                        break

        # Use override email for testing
        send_to = recipient_override if recipient_override else provider_email

        if not send_to:
            offers_skipped.append({"provider": name, "reason": "no email found"})
            logger.warning(f"[InitialNeg] No email for {name}, skipping")
            continue

        # Build and send email
        offered_str = f"${offered:,.2f}"
        bill_str = f"${bill:,.2f}"

        html_body = _build_offer_email(
            provider_name=name,
            provider_address=provider_address,
            patient_name=patient_name,
            patient_dob=patient_dob,
            incident_date=incident_date,
            offered_amount=offered_str,
            total_bill=bill_str,
            gmail_email=gmail_email,
        )

        try:
            sent = await asyncio.to_thread(
                send_reply,
                gmail_email, gmail_password,
                send_to, "Bill Negotiation", html_body,
            )
            if sent:
                offers_sent.append({
                    "provider": name,
                    "email": send_to,
                    "bill": bill,
                    "offered": offered,
                    "reason": provider["offer_reason"],
                })
                logger.info(f"[InitialNeg] Sent offer to {send_to}: ${offered:,.2f} for {name}")
            else:
                offers_skipped.append({"provider": name, "reason": "send failed"})
        except Exception as e:
            logger.error(f"[InitialNeg] Failed to send to {send_to}: {e}")
            offers_skipped.append({"provider": name, "reason": str(e)})

    # 5. Log negotiations to Turso
    from turso_client import turso
    for offer in offers_sent:
        try:
            turso.execute(
                'INSERT INTO negotiations (case_id, negotiation_type, "to", email_body, date, actual_bill, offered_bill, sent_by_us, result) VALUES (?, ?, ?, ?, datetime(\'now\'), ?, ?, 1, ?)',
                [case_id, "Offer", offer["email"],
                 f"Initial offer sent: ${offer['offered']:,.2f} for {offer['provider']}",
                 offer["bill"], offer["offered"], "Pending"]
            )
        except Exception as e:
            logger.error(f"[InitialNeg] Failed to log negotiation: {e}")

    # 6. Add case note
    note = f"Initial negotiations sent to {len(offers_sent)} provider(s). "
    if offers_skipped:
        note += f"{len(offers_skipped)} skipped (no email or low bill)."
    await asyncio.to_thread(add_case_note, case_id, note)

    result = {
        "case_id": case_id,
        "patient_name": patient_name,
        "offers_sent": len(offers_sent),
        "offers_skipped": len(offers_skipped),
        "details": offers_sent,
        "skipped": offers_skipped,
    }

    # 7. Trigger sub-workflows (thirdparty + get-mail-sub) in background
    try:
        from workflow_scheduler import trigger_workflow
        await trigger_workflow("thirdparty", case_id, triggered_by="initial_negotiation")
        await trigger_workflow("get_mail_sub", case_id, triggered_by="initial_negotiation")
    except Exception as e:
        logger.warning(f"[InitialNeg] Failed to trigger sub-workflows: {e}")

    logger.info(f"[InitialNeg] Done for case {case_id}: {len(offers_sent)} sent, {len(offers_skipped)} skipped")
    return result


def _get_gmail_creds():
    """Get Gmail credentials."""
    from gmail_poller import _get_gmail_creds as gc
    return gc()
