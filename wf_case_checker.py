"""
Workflow: CasePeer New Case Checker

Runs daily to detect new cases in CasePeer and trigger classification.

Flow:
1. Fetch cases from CasePeer API (/api/v1/case/my/)
2. Compare against cases table in Turso
3. For new cases: store in Turso + trigger classification workflow
"""

import asyncio
import json
import logging
from typing import Dict, Any, List

from casepeer_helpers import casepeer_get

logger = logging.getLogger(__name__)


def _fetch_all_my_cases() -> List[Dict[str, Any]]:
    """Fetch all cases from the CasePeer API, handling pagination."""
    all_cases = []
    url = "api/v1/case/my/"

    while url:
        result = casepeer_get(url)
        raw = result.get("response", "")
        try:
            data = json.loads(raw)
        except (json.JSONDecodeError, TypeError):
            logger.error(f"[CaseChecker] Failed to parse API response: {raw[:200]}")
            break

        all_cases.extend(data.get("results", []))
        # Handle pagination — 'next' is a full URL or null
        next_url = data.get("next")
        if next_url:
            # Extract relative path from full URL
            if "casepeer.com/" in next_url:
                url = next_url.split("casepeer.com/", 1)[1]
            else:
                url = next_url
        else:
            url = None

    return all_cases


async def run_case_checker() -> Dict[str, Any]:
    """
    Scan CasePeer for new cases and trigger classification for each.
    Returns summary of new cases found.
    """
    from turso_client import turso

    logger.info("[CaseChecker] Starting scan for new cases")

    # 1. Fetch cases from CasePeer API
    cases = await asyncio.to_thread(_fetch_all_my_cases)

    if not cases:
        logger.info("[CaseChecker] No cases returned from API")
        return {"new_cases": 0, "total_from_api": 0, "message": "No cases returned from API"}

    # Filter out test/internal cases (primary_contact = "Saleh Ai")
    EXCLUDED_CONTACTS = {"saleh ai"}
    real_cases = [c for c in cases if c.get("primary_contact", "").strip().lower() not in EXCLUDED_CONTACTS]
    logger.info(f"[CaseChecker] {len(cases)} total from API, {len(real_cases)} after excluding test contacts")

    if not real_cases:
        return {"new_cases": 0, "total_from_api": len(cases), "filtered": len(cases) - len(real_cases), "message": "All cases excluded by contact filter"}

    # Build lookups from API data
    case_info = {
        str(c["id"]): {
            "name": c.get("_casename", "Unknown"),
            "status": c.get("casestatus", ""),
            "casetype": c.get("casetype", ""),
            "primary_contact": c.get("primary_contact", ""),
            "doi": c.get("doi", ""),
        }
        for c in real_cases
    }
    extracted_ids = list(case_info.keys())

    logger.info(f"[CaseChecker] Found {len(extracted_ids)} real case IDs")

    # 3. Compare against cases in Turso
    known_rows = turso.fetch_all("SELECT id FROM cases")
    known_ids = {str(r.get("id", "")) for r in known_rows}

    new_ids = [cid for cid in extracted_ids if cid not in known_ids]
    logger.info(f"[CaseChecker] {len(new_ids)} new case(s) detected (out of {len(extracted_ids)} total)")

    # 4. Store new cases in Turso and trigger classification
    new_cases = []
    for case_id in new_ids:
        try:
            info = case_info.get(case_id, {})
            patient_name = info.get("name", "Unknown")
            case_status = info.get("status", "")
            case_type = info.get("casetype", "")
            primary_contact = info.get("primary_contact", "")
            doi = info.get("doi", "")

            turso.execute(
                "INSERT OR IGNORE INTO cases (id, patient_name, status, classification_status, casetype, casestatus, primary_contact, doi) VALUES (?, ?, 'new', 'pending', ?, ?, ?, ?)",
                [case_id, patient_name, case_type, case_status, primary_contact, doi]
            )
            new_cases.append({"case_id": case_id, "patient_name": patient_name, "casestatus": case_status, "casetype": case_type, "primary_contact": primary_contact})
            logger.info(f"[CaseChecker] New case: {case_id} ({patient_name}) - {case_status}")

            # Auto-trigger provider email calls for the new case
            try:
                from turso_client import get_setting
                auto_call = (get_setting("auto_provider_calls_enabled", "true") or "").lower() == "true"
                if auto_call:
                    from workflow_scheduler import trigger_workflow
                    await trigger_workflow("provider_calls", case_id, triggered_by="case_checker_auto")
                    logger.info(f"[CaseChecker] Auto-triggered provider calls for case {case_id}")
            except Exception as call_err:
                logger.warning(f"[CaseChecker] Failed to auto-trigger provider calls for {case_id}: {call_err}")

        except Exception as e:
            logger.error(f"[CaseChecker] Failed to process case {case_id}: {e}")

    # Update last_checked for all known cases
    try:
        turso.execute("UPDATE cases SET last_checked = datetime('now')")
    except Exception:
        pass

    result = {
        "total_from_api": len(cases),
        "filtered_out": len(cases) - len(real_cases),
        "real_cases": len(extracted_ids),
        "already_known": len(known_ids),
        "new_cases": len(new_cases),
        "new_case_details": new_cases,
    }
    logger.info(f"[CaseChecker] Complete: {result}")
    return result


