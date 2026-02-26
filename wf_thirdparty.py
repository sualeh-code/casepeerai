"""
Workflow: Third-Party (Defendant) Settlement Processing

Replicates the n8n Thirdpartysubf workflow.
Handles the full defendant insurance settlement flow:

Flow:
1. Get defendant insurance data from case
2. Create third-party demand
3. Create offer
4. Accept offer
5. Record deposit
6. Take fees
7. Edit settlement fees (17%)
"""

import asyncio
import json
import logging
import re
from datetime import datetime
from typing import Dict, Any, Optional

from casepeer_helpers import (
    casepeer_get, casepeer_post, casepeer_post_form,
    extract_html, extract_id_from_url, get_defendant_data,
    add_case_note, get_local_base,
)

logger = logging.getLogger(__name__)


async def run_thirdparty_processing(case_id: str) -> Dict[str, Any]:
    """
    Run the full third-party (defendant) settlement flow for a case.
    """
    logger.info(f"[ThirdParty] Starting for case {case_id}")

    # Step 1: Get defendant insurance data
    defendant_data = await asyncio.to_thread(get_defendant_data, case_id)
    if "error" in defendant_data:
        return {"error": defendant_data["error"], "case_id": case_id}

    insurance_id = defendant_data.get("insurance_id", "")
    deposited_amount = defendant_data.get("deposited_amount", 0)
    full_name = defendant_data.get("full_name", "")

    if not insurance_id:
        return {"error": "No insurance ID found on defendant page", "case_id": case_id}

    if deposited_amount <= 0:
        return {"error": "No deposited amount found", "case_id": case_id}

    logger.info(f"[ThirdParty] Case {case_id}: defendant={full_name}, insurance_id={insurance_id}, deposited=${deposited_amount:,.2f}")

    today = datetime.now().strftime("%Y-%m-%d")

    # Step 2: Create third-party demand
    demand_result = await asyncio.to_thread(
        _post_form, case_id,
        f"case/{case_id}/settlement/third-party-demand/",
        {
            "defendant_insurance": insurance_id,
            "datesent": today,
            "amount": str(deposited_amount),
            "submitButton": "Submit",
        }
    )
    logger.info(f"[ThirdParty] Demand created for case {case_id}")

    # Step 3: Get negotiation page and extract offer ID
    offer_id = await asyncio.to_thread(_get_offer_id, case_id)
    if not offer_id:
        return {"error": "Could not extract offer ID from negotiations page", "case_id": case_id, "step": "get_offer_id"}

    logger.info(f"[ThirdParty] Offer ID: {offer_id}")

    # Step 4: Create offer
    await asyncio.to_thread(
        _post_form, case_id,
        f"case/{case_id}/settlement/offer/{offer_id}/",
        {
            "offer_date": today,
            "offer": str(deposited_amount),
            "description": f"${deposited_amount:,.2f}",
            "submitButton": "Submit",
        }
    )
    logger.info(f"[ThirdParty] Offer created: ${deposited_amount:,.2f}")

    # Step 5: Get accept offer ID (different from offer ID)
    accept_offer_id = await asyncio.to_thread(_get_accept_offer_id, case_id)
    if not accept_offer_id:
        return {"error": "Could not extract accept offer ID", "case_id": case_id, "step": "get_accept_id"}

    logger.info(f"[ThirdParty] Accept offer ID: {accept_offer_id}")

    # Step 6: Accept offer
    await asyncio.to_thread(
        _post_form, case_id,
        f"case/{case_id}/settlement/offer/accept/{accept_offer_id}/",
        {
            "case_stage": "litigation",
            "accepteddate": "",
            "offerstatus": "2",
            "acceptednote": "",
            "submitButton": "Submit",
        }
    )
    logger.info(f"[ThirdParty] Offer accepted")

    # Step 7: Record deposit
    await asyncio.to_thread(
        _post_form, case_id,
        f"case/{case_id}/settlement/settlement-deposit/{accept_offer_id}/",
        {
            "check_number": "",
            "memo": "",
            "submitButton": "Submit",
        }
    )
    logger.info(f"[ThirdParty] Deposit recorded")

    # Step 8: Take fees (initial)
    await asyncio.to_thread(
        _post_form, case_id,
        f"case/{case_id}/settlement/fee-check/{accept_offer_id}/{offer_id}/",
        {
            "check_number": "",
            "memo": "",
            "take_dollar_amount": "False",
            "fee_percentage": "4",
            "dollar_amount": "",
            "submitButton": "Submit",
        }
    )
    logger.info(f"[ThirdParty] Initial fees taken")

    # Step 9: Edit settlement fees (17%)
    fee_percentage = 17
    await asyncio.to_thread(
        _post_form, case_id,
        f"{case_id}/settlement/edit-settlement-fees/{accept_offer_id}/",
        {
            "take_dollar_amount": "false",
            "fee_percentage": str(fee_percentage),
            "dollar_amount": "",
            "submitButton": "Submit",
        }
    )
    logger.info(f"[ThirdParty] Settlement fees set to {fee_percentage}%")

    # Step 10: Add case note
    percentage33 = deposited_amount * 0.33
    await asyncio.to_thread(
        add_case_note, case_id,
        f"Third-party settlement processed: Deposited ${deposited_amount:,.2f}, 33% = ${percentage33:,.2f}, Fees = {fee_percentage}%"
    )

    # Step 11: Update case in Turso
    from turso_client import turso
    try:
        turso.execute(
            "INSERT OR REPLACE INTO cases (id, patient_name, status, fees_taken) VALUES (?, ?, 'Disbursement', ?)",
            [case_id, full_name, round(deposited_amount * fee_percentage / 100, 2)]
        )
    except Exception as e:
        logger.warning(f"[ThirdParty] Failed to update case in Turso: {e}")

    result = {
        "case_id": case_id,
        "defendant_name": full_name,
        "insurance_id": insurance_id,
        "deposited_amount": deposited_amount,
        "percentage_33": round(percentage33, 2),
        "fee_percentage": fee_percentage,
        "fees_taken": round(deposited_amount * fee_percentage / 100, 2),
        "status": "completed",
    }
    logger.info(f"[ThirdParty] Complete: {result}")
    return result


# ---------------------------------------------------------------------------
# Helper functions
# ---------------------------------------------------------------------------

def _post_form(case_id: str, endpoint: str, data: Dict) -> bool:
    """POST form data to CasePeer endpoint with CSRF injection."""
    import requests as req

    base = get_local_base()
    try:
        # First GET the page to extract CSRF token
        get_resp = req.get(f"{base}/{endpoint.lstrip('/')}", timeout=90)
        from bs4 import BeautifulSoup
        soup = BeautifulSoup(get_resp.text, "html.parser")

        csrf_input = soup.select_one("input[name='csrfmiddlewaretoken']")
        if csrf_input:
            data["csrfmiddlewaretoken"] = csrf_input.get("value", "")

        resp = req.post(
            f"{base}/{endpoint.lstrip('/')}",
            data=data,
            timeout=90,
        )
        return resp.status_code in (200, 302)
    except Exception as e:
        logger.error(f"[ThirdParty] POST {endpoint} failed: {e}")
        return False


def _get_offer_id(case_id: str) -> Optional[str]:
    """Get the offer ID from the negotiations page."""
    result = casepeer_get(f"case/{case_id}/settlement/negotiations/")
    html = extract_html(result)
    if not html:
        return None
    match = re.search(r'/settlement/offer/(\d+)/', html)
    return match.group(1) if match else None


def _get_accept_offer_id(case_id: str) -> Optional[str]:
    """Get the accept offer ID from the negotiations page."""
    result = casepeer_get(f"case/{case_id}/settlement/negotiations/")
    html = extract_html(result)
    if not html:
        return None
    match = re.search(r'/settlement/offer/accept/(\d+)/', html)
    return match.group(1) if match else None
