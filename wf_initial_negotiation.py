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

async def _build_balance_confirmation_pdf(
    provider_name: str,
    provider_address: str,
    patient_name: str,
    patient_dob: str,
    incident_date: str,
    gmail_email: str,
    bill_amount: float = 0.0,
) -> bytes:
    """Generate a Beverly Law balance confirmation letter as a styled PDF via Playwright."""
    today = datetime.now().strftime("%B %d, %Y")
    bill_str = f"${bill_amount:,.2f}" if bill_amount > 0 else "N/A"

    addr_lines = ""
    if provider_address:
        for line in provider_address.split(","):
            line = line.strip()
            if line:
                addr_lines += f"<div>{line}</div>"

    dob_line = f'<div style="margin-top:2px;">Date of Birth: {patient_dob}</div>' if patient_dob and patient_dob != "N/A" else ""
    dol_line = f'<div style="margin-top:2px;">Date of Injury: {incident_date}</div>' if incident_date and incident_date != "N/A" else ""

    html = f"""<!DOCTYPE html>
<html><head><style>
  body {{
    font-family: 'Georgia', 'Times New Roman', serif;
    font-size: 10.5pt;
    color: #1a1a1a;
    margin: 0;
    padding: 0;
    line-height: 1.35;
  }}
  .letterhead {{
    border-bottom: 2px solid #1a3c6e;
    padding-bottom: 8px;
    margin-bottom: 10px;
  }}
  .firm-name {{
    font-size: 18pt;
    font-weight: bold;
    color: #1a3c6e;
  }}
  .firm-details {{
    font-size: 8.5pt;
    color: #555;
    margin-top: 2px;
  }}
  .firm-note {{
    font-size: 7.5pt;
    font-style: italic;
    color: #888;
    margin-top: 3px;
  }}
  .meta-row {{
    margin-bottom: 6px;
    font-size: 10pt;
  }}
  .via {{ font-weight: bold; font-size: 8.5pt; color: #555; letter-spacing: 2px; margin-bottom: 4px; }}
  .recipient {{ font-weight: bold; margin-bottom: 8px; font-size: 10pt; }}
  .re-block {{
    background: #f4f6f9;
    border-left: 3px solid #1a3c6e;
    padding: 6px 12px;
    margin-bottom: 8px;
    font-size: 9.5pt;
  }}
  .re-block .re-title {{ font-weight: bold; color: #1a3c6e; }}
  .body-text {{ margin-bottom: 6px; text-align: justify; font-size: 10pt; }}
  .bill-highlight {{
    background: #fff8e1;
    border: 1px solid #f0c040;
    border-radius: 3px;
    padding: 6px 12px;
    margin: 8px 0;
    font-size: 10pt;
  }}
  .bill-highlight strong {{ color: #b8860b; font-size: 12pt; }}
  .confirmation-box {{
    border: 2px solid #1a3c6e;
    border-radius: 5px;
    padding: 10px 14px;
    margin: 10px 0;
  }}
  .confirmation-box h3 {{
    color: #1a3c6e;
    margin: 0 0 8px 0;
    font-size: 10pt;
    text-transform: uppercase;
    letter-spacing: 1px;
    border-bottom: 1px solid #ccc;
    padding-bottom: 4px;
  }}
  .form-row {{
    display: flex;
    align-items: baseline;
    margin-bottom: 10px;
  }}
  .form-label {{
    width: 145px;
    font-size: 9.5pt;
    color: #333;
    flex-shrink: 0;
  }}
  .form-line {{
    flex: 1;
    border-bottom: 1px solid #999;
    min-height: 14px;
    margin-left: 6px;
  }}
  .form-prefix {{
    font-size: 9.5pt;
    margin-left: 6px;
    margin-right: 3px;
  }}
  .sig-section {{ margin-top: 10px; padding-top: 6px; border-top: 1px solid #ddd; }}
  .closing {{ margin-top: 12px; font-size: 10pt; }}
  .closing .firm {{ font-weight: bold; color: #1a3c6e; font-size: 11pt; }}
  .email-note {{
    margin-top: 10px;
    padding: 6px 10px;
    background: #e8f5e9;
    border-radius: 3px;
    font-size: 8.5pt;
    color: #2e7d32;
  }}
</style></head><body>

<div class="letterhead">
  <div class="firm-name">Beverly Law</div>
  <div class="firm-details">
    4929 Wilshire Blvd, Suite 960, Los Angeles, CA 90010<br>
    Tel: 310-552-6959 &nbsp;|&nbsp; Fax: 323-421-9397
  </div>
  <div class="firm-note">*Please note our new office address in your file*</div>
</div>

<div class="date-line">{today}</div>
<div class="via">VIA EMAIL</div>

<div class="recipient">
  {provider_name}
  {addr_lines}
</div>

<div class="re-block">
  <div class="re-title">RE: Our Client / Your Patient: {patient_name}</div>
  {dob_line}
  {dol_line}
</div>

<div class="body-text">Dear Sir or Madam:</div>

<div class="body-text">
  Our office represents <strong>{patient_name}</strong> regarding injuries sustained on
  <strong>{incident_date}</strong>. We are in the process of negotiating with the Insurance
  Company and would like to confirm the outstanding balance for our client's account with your office.
</div>

<div class="bill-highlight">
  The total that you have billed {patient_name} for this case is: <strong>{bill_str}</strong>.
  Please confirm the outstanding balance for this patient.
</div>

<div class="body-text">
  Please confirm the outstanding balance by completing the section below and returning
  this letter to our office via email. Thank you for your prompt attention to this matter.
</div>

<div class="confirmation-box">
  <h3>Outstanding Balance Confirmation</h3>

  <div class="form-row">
    <span class="form-label">Total Amount Billed:</span>
    <span class="form-prefix">$</span>
    <span class="form-line"></span>
  </div>
  <div class="form-row">
    <span class="form-label">Insurance Payments:</span>
    <span class="form-prefix">$</span>
    <span class="form-line"></span>
  </div>
  <div class="form-row">
    <span class="form-label">Adjustments:</span>
    <span class="form-prefix">$</span>
    <span class="form-line"></span>
  </div>
  <div class="form-row">
    <span class="form-label">Outstanding Balance:</span>
    <span class="form-prefix">$</span>
    <span class="form-line"></span>
  </div>

  <div class="form-row" style="margin-top:22px;">
    <span class="form-label">Payment Address:</span>
    <span class="form-line"></span>
  </div>
  <div class="form-row">
    <span class="form-label"></span>
    <span class="form-line"></span>
  </div>

  <div class="sig-section">
    <div class="form-row">
      <span class="form-label">Authorized Signature:</span>
      <span class="form-line"></span>
    </div>
    <div class="form-row">
      <span class="form-label">Print Name:</span>
      <span class="form-line"></span>
    </div>
    <div class="form-row">
      <span class="form-label">Date:</span>
      <span class="form-line"></span>
    </div>
  </div>
</div>

<div class="closing">
  Regards,<br>
  <span class="firm">BEVERLY LAW</span>
</div>

<div class="email-note">
  Please scan and EMAIL this letter back to <strong>{gmail_email}</strong>.
  Please do not fax. Thank you for your partnership.
</div>

</body></html>"""

    from playwright.async_api import async_playwright
    async with async_playwright() as p:
        browser = await p.chromium.launch()
        page = await browser.new_page()
        await page.set_content(html, wait_until="networkidle")
        pdf_bytes = await page.pdf(
            format="Letter",
            print_background=True,
            margin={"top": "40px", "bottom": "30px", "left": "50px", "right": "50px"},
        )
        await browser.close()
    return pdf_bytes


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
        pdf_bytes = await _build_balance_confirmation_pdf(
            provider_name=name,
            provider_address=provider_address,
            patient_name=patient_name,
            patient_dob=patient_dob,
            incident_date=incident_date,
            gmail_email=gmail_email,
            bill_amount=bill,
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
