"""
Workflow: CasePeer New Case Checker

Replicates the n8n CasePeer New Case Checker workflow.
Runs daily to detect new cases in CasePeer and trigger classification.

Flow:
1. Fetch "My Cases" page from CasePeer
2. Extract case IDs from HTML
3. Compare against known_cases table in Turso (replaces Google Sheets)
4. For new cases: store in Turso + trigger classification workflow
"""

import asyncio
import logging
import re
from typing import Dict, Any, List

from casepeer_helpers import casepeer_get, extract_html, extract_case_ids_from_html

logger = logging.getLogger(__name__)


async def run_case_checker() -> Dict[str, Any]:
    """
    Scan CasePeer for new cases and trigger classification for each.
    Returns summary of new cases found.
    """
    from turso_client import turso

    logger.info("[CaseChecker] Starting scan for new cases")

    # 1. Fetch "My Cases" page from CasePeer
    result = await asyncio.to_thread(casepeer_get, "report/R/my-cases/?page=1")
    html = extract_html(result)
    if not html:
        # Try the raw response if it's a string
        html = str(result) if result else ""

    if not html:
        return {"error": "Failed to fetch My Cases page", "new_cases": 0}

    # 2. Extract case IDs from HTML
    extracted_ids = extract_case_ids_from_html(html)

    if not extracted_ids:
        logger.info("[CaseChecker] No case IDs found on page")
        return {"new_cases": 0, "total_on_page": 0, "message": "No case IDs found"}

    logger.info(f"[CaseChecker] Found {len(extracted_ids)} case IDs on page")

    # 3. Compare against known_cases in Turso
    known_rows = turso.fetch_all("SELECT case_id FROM known_cases")
    known_ids = {str(r.get("case_id", "")) for r in known_rows}

    new_ids = [cid for cid in extracted_ids if cid not in known_ids]
    logger.info(f"[CaseChecker] {len(new_ids)} new case(s) detected (out of {len(extracted_ids)} total)")

    # 4. Store new cases in Turso and trigger classification
    new_cases = []
    for case_id in new_ids:
        try:
            # Try to get patient name from case page
            patient_name = await _get_patient_name(case_id)

            turso.execute(
                "INSERT OR IGNORE INTO known_cases (case_id, patient_name, status, classification_status) VALUES (?, ?, 'new', 'pending')",
                [case_id, patient_name]
            )
            new_cases.append({"case_id": case_id, "patient_name": patient_name})
            logger.info(f"[CaseChecker] New case: {case_id} ({patient_name})")

            # Trigger classification workflow in background
            try:
                from workflow_scheduler import trigger_workflow
                await trigger_workflow("classification", case_id, triggered_by="case_checker")
            except Exception as e:
                logger.warning(f"[CaseChecker] Failed to trigger classification for {case_id}: {e}")

        except Exception as e:
            logger.error(f"[CaseChecker] Failed to process case {case_id}: {e}")

    # Update last_checked for all known cases
    try:
        turso.execute("UPDATE known_cases SET last_checked = datetime('now') WHERE case_id IN (SELECT case_id FROM known_cases)")
    except Exception:
        pass

    result = {
        "total_on_page": len(extracted_ids),
        "known_cases": len(known_ids),
        "new_cases": len(new_cases),
        "new_case_details": new_cases,
    }
    logger.info(f"[CaseChecker] Complete: {result}")
    return result


async def _get_patient_name(case_id: str) -> str:
    """Try to get the patient name from the case page."""
    try:
        from bs4 import BeautifulSoup
        result = await asyncio.to_thread(casepeer_get, f"case/{case_id}/")
        html = extract_html(result)
        if html:
            soup = BeautifulSoup(html, "html.parser")
            title = soup.select_one("title")
            if title:
                match = re.match(r'(.*?)\s*-\s*Home', title.get_text())
                if match:
                    return match.group(1).strip()
    except Exception as e:
        logger.warning(f"[CaseChecker] Could not get patient name for {case_id}: {e}")
    return "Unknown"
