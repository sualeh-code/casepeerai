"""
Workflow: Initial Negotiation (Neg0sub)

Replicates the n8n Neg0sub workflow — the smarter way.

Flow:
1. Scrape treatment page → get providers, bills, liens
2. Deduplicate providers by phone
3. For each provider: generate balance confirmation PDF, email it
4. Log to Turso, add case note
5. Trigger sub-workflows if needed

NOTE: This is Step 1 (balance confirmation). We do NOT send an offer yet.
      The offer comes later after the provider confirms the outstanding balance.
"""

import asyncio
import io
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

# Providers to exclude from the negotiation process entirely
EXCLUDED_PROVIDERS = ["medicare", "medicaid", "medi-cal"]


# ---------------------------------------------------------------------------
# PDF generation — Balance Confirmation Letter
# ---------------------------------------------------------------------------

def _build_balance_confirmation_pdf(
    provider_name: str,
    provider_address: str,
    patient_name: str,
    patient_dob: str,
    incident_date: str,
    gmail_email: str,
) -> bytes:
    """Generate a Beverly Law balance confirmation letter as a PDF.

    The letter asks the provider to confirm the outstanding balance.
    No offer amount is included — that comes after confirmation.
    """
    from fpdf import FPDF

    today = datetime.now().strftime("%B %d, %Y")

    pdf = FPDF()
    pdf.add_page()
    pdf.set_auto_page_break(auto=True, margin=25)

    # --- Letterhead ---
    pdf.set_font("Helvetica", "B", 14)
    pdf.cell(0, 7, "Beverly Law", new_x="LMARGIN", new_y="NEXT")
    pdf.set_font("Helvetica", "", 10)
    pdf.cell(0, 5, "4929 Wilshire Blvd, Suite 960", new_x="LMARGIN", new_y="NEXT")
    pdf.cell(0, 5, "Los Angeles, CA 90010", new_x="LMARGIN", new_y="NEXT")
    pdf.ln(3)
    pdf.cell(0, 5, "Tel: 310-552-6959", new_x="LMARGIN", new_y="NEXT")
    pdf.cell(0, 5, "Fax: 323-421-9397", new_x="LMARGIN", new_y="NEXT")
    pdf.ln(3)
    pdf.set_font("Helvetica", "I", 9)
    pdf.cell(0, 5, "*Please note our new office address in your file*", new_x="LMARGIN", new_y="NEXT")
    pdf.ln(8)

    # --- Date and delivery method ---
    pdf.set_font("Helvetica", "", 11)
    pdf.cell(0, 6, today, new_x="LMARGIN", new_y="NEXT")
    pdf.ln(4)
    pdf.cell(0, 6, "VIA EMAIL", new_x="LMARGIN", new_y="NEXT")
    pdf.ln(4)

    # --- Recipient ---
    pdf.set_font("Helvetica", "B", 11)
    pdf.cell(0, 6, f"{provider_name}:", new_x="LMARGIN", new_y="NEXT")
    pdf.set_font("Helvetica", "", 11)
    if provider_address:
        for line in provider_address.split(","):
            line = line.strip()
            if line:
                pdf.cell(0, 6, line, new_x="LMARGIN", new_y="NEXT")
    pdf.ln(6)

    # --- RE line ---
    pdf.set_font("Helvetica", "B", 11)
    pdf.cell(0, 6, f"RE: Our Client/Your Patient: {patient_name}", new_x="LMARGIN", new_y="NEXT")
    pdf.ln(2)
    pdf.set_font("Helvetica", "", 11)
    if patient_dob and patient_dob != "N/A":
        pdf.cell(0, 6, f"Date of Birth: {patient_dob}", new_x="LMARGIN", new_y="NEXT")
    if incident_date and incident_date != "N/A":
        pdf.cell(0, 6, f"Date of Injury: {incident_date}", new_x="LMARGIN", new_y="NEXT")
    pdf.ln(6)

    # --- Body ---
    pdf.cell(0, 6, "Dear Sir or Madam:", new_x="LMARGIN", new_y="NEXT")
    pdf.ln(4)

    body = (
        f"Our office represents {patient_name} regarding injuries sustained on "
        f"{incident_date}. We are in the process of negotiating with the Insurance "
        f"Company and would like to confirm the outstanding balance for our client's "
        f"account with your office."
    )
    pdf.multi_cell(0, 6, body)
    pdf.ln(4)

    body2 = (
        "Please confirm the outstanding balance by completing the section below "
        "and returning this letter to our office via email. Thank you for your "
        "prompt attention to this matter."
    )
    pdf.multi_cell(0, 6, body2)
    pdf.ln(8)

    # --- Balance confirmation section (fillable) ---
    pdf.set_font("Helvetica", "B", 11)
    pdf.cell(0, 6, "OUTSTANDING BALANCE CONFIRMATION", new_x="LMARGIN", new_y="NEXT")
    pdf.ln(4)
    pdf.set_font("Helvetica", "", 11)

    pdf.cell(0, 8, "Total Amount Billed:  $ ___________________________", new_x="LMARGIN", new_y="NEXT")
    pdf.cell(0, 8, "Insurance Payments:   $ ___________________________", new_x="LMARGIN", new_y="NEXT")
    pdf.cell(0, 8, "Adjustments:          $ ___________________________", new_x="LMARGIN", new_y="NEXT")
    pdf.cell(0, 8, "Outstanding Balance:  $ ___________________________", new_x="LMARGIN", new_y="NEXT")
    pdf.ln(4)
    pdf.cell(0, 8, "Payment Address: ____________________________________________", new_x="LMARGIN", new_y="NEXT")
    pdf.cell(0, 8, "                 ____________________________________________", new_x="LMARGIN", new_y="NEXT")
    pdf.ln(4)
    pdf.cell(0, 8, "Authorized Signature: ________________________________________", new_x="LMARGIN", new_y="NEXT")
    pdf.cell(0, 8, "Print Name:           ________________________________________", new_x="LMARGIN", new_y="NEXT")
    pdf.cell(0, 8, "Date:                 ________________________________________", new_x="LMARGIN", new_y="NEXT")
    pdf.ln(8)

    # --- Closing ---
    pdf.cell(0, 6, "Regards,", new_x="LMARGIN", new_y="NEXT")
    pdf.set_font("Helvetica", "B", 11)
    pdf.cell(0, 6, "BEVERLY LAW", new_x="LMARGIN", new_y="NEXT")
    pdf.ln(4)
    pdf.set_font("Helvetica", "", 10)
    pdf.multi_cell(0, 5,
        f"Please scan and EMAIL this letter back to {gmail_email}. "
        "Please do not fax. Thank you for your partnership."
    )

    return pdf.output()


def _build_cover_email(provider_name: str, patient_name: str) -> str:
    """Short cover email body to accompany the PDF attachment."""
    return (
        f"Dear {provider_name},<br><br>"
        f"Please find attached a balance confirmation request regarding our client "
        f"<strong>{patient_name}</strong>.<br><br>"
        f"Kindly complete the attached form and return it to us via email at your "
        f"earliest convenience.<br><br>"
        f"Thank you for your prompt attention to this matter."
    )


# ---------------------------------------------------------------------------
# Main workflow
# ---------------------------------------------------------------------------

async def run_initial_negotiation(case_id: str) -> Dict[str, Any]:
    """
    Run the initial negotiation workflow for a case.
    Sends balance confirmation PDF to each provider (no offer yet).
    """
    from turso_client import get_setting
    from gmail_poller import send_email_with_attachment

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

    # 3. Look up provider emails and send balance confirmation PDFs
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

        # Generate PDF
        pdf_bytes = _build_balance_confirmation_pdf(
            provider_name=name,
            provider_address=provider_address,
            patient_name=patient_name,
            patient_dob=patient_dob,
            incident_date=incident_date,
            gmail_email=gmail_email,
        )

        # Build cover email
        cover_html = _build_cover_email(name, patient_name)

        # Safe filename
        safe_name = re.sub(r'[^a-zA-Z0-9 ]', '', name).strip().replace(' ', '_')
        filename = f"Balance_Confirmation_{safe_name}.pdf"

        # Send with retry (up to 3 attempts, 5s delay)
        sent = False
        last_error = None
        for attempt in range(1, 4):
            try:
                sent = await asyncio.to_thread(
                    send_email_with_attachment,
                    gmail_email, send_to,
                    "Balance Confirmation Request",
                    cover_html, pdf_bytes, filename,
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
                "email": send_to,
                "bill": bill,
            })
            logger.info(f"[InitialNeg] Sent balance confirmation to {send_to} for {name}")
        else:
            skipped_list.append({"provider": name, "reason": f"send failed: {last_error}"})
            logger.error(f"[InitialNeg] Failed to send to {send_to}: {last_error}")

    # 4. Log to Turso
    from turso_client import turso
    for item in sent_list:
        try:
            turso.execute(
                'INSERT INTO negotiations (case_id, negotiation_type, "to", email_body, date, actual_bill, offered_bill, sent_by_us, result) VALUES (?, ?, ?, ?, datetime(\'now\'), ?, ?, 1, ?)',
                [case_id, "Balance Confirmation", item["email"],
                 f"Balance confirmation PDF sent to {item['provider']}",
                 item["bill"], 0.0, "Awaiting Confirmation"]
            )
        except Exception as e:
            logger.error(f"[InitialNeg] Failed to log: {e}")

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

    # 6. Trigger sub-workflows in background
    try:
        from workflow_scheduler import trigger_workflow
        await trigger_workflow("thirdparty", case_id, triggered_by="initial_negotiation")
        await trigger_workflow("get_mail_sub", case_id, triggered_by="initial_negotiation")
    except Exception as e:
        logger.warning(f"[InitialNeg] Failed to trigger sub-workflows: {e}")

    logger.info(f"[InitialNeg] Done for case {case_id}: {len(sent_list)} sent, {len(skipped_list)} skipped")
    return result


def _get_gmail_creds():
    """Get Gmail credentials."""
    from gmail_poller import _get_gmail_creds as gc
    return gc()
