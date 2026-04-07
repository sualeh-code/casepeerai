"""
Workflow: Sync Providers and Bills

After classification, this workflow:
1. Fetches all health liens (providers + bills) from CasePeer's treatment page
2. For any provider with a missing/zero original_cost, extracts the bill amount
   from the classified document text and updates CasePeer
3. Returns a summary of providers found and any bill updates made

This replaces the manual step of entering bill amounts in CasePeer.
"""

import asyncio
import json
import logging
import re
from typing import Dict, Any, List, Optional

from casepeer_helpers import casepeer_get, get_treatment_providers

logger = logging.getLogger(__name__)


async def run_sync_providers(case_id: str) -> Dict[str, Any]:
    """
    Sync provider bills for a case. Reads from CasePeer health liens,
    fills in any zero/missing bill amounts from classified doc extracted text.
    """
    logger.info(f"[SyncProviders] Starting for case {case_id}")

    # 1. Get current providers from CasePeer
    treatment = await asyncio.to_thread(get_treatment_providers, case_id)
    if "error" in treatment:
        return {"error": treatment["error"], "case_id": case_id}

    providers = treatment.get("providers", [])
    if not providers:
        return {"case_id": case_id, "providers": 0, "message": "No providers found on treatment page"}

    logger.info(f"[SyncProviders] Found {len(providers)} providers for case {case_id}")

    # 2. Find providers with missing/zero bills
    providers_missing_bill = [p for p in providers if not p.get("bill_amount") or p["bill_amount"] <= 0]
    logger.info(f"[SyncProviders] {len(providers_missing_bill)} providers have no bill amount")

    # 3. Try to fill missing bills from classified document extracted text in Turso
    updates_made = []
    if providers_missing_bill:
        from turso_client import turso
        # Get extracted text from recent classifications for this case
        rows = turso.fetch_all(
            "SELECT * FROM classifications WHERE case_id = ? ORDER BY id DESC LIMIT 50",
            [case_id]
        )
        # Also pull from conversation_history which may have extracted text
        extracted_texts = _get_extracted_texts(case_id)

        for provider in providers_missing_bill:
            provider_name = provider.get("provider_name", "")
            bill = _find_bill_in_texts(provider_name, extracted_texts)
            if bill and bill > 0:
                logger.info(f"[SyncProviders] Found bill ${bill} for '{provider_name}' from doc text")
                try:
                    from negotiation_agent import _update_lien_original_cost
                    success = await asyncio.to_thread(
                        _update_lien_original_cost, case_id, provider_name, str(bill)
                    )
                    if success:
                        updates_made.append({"provider": provider_name, "bill_set": bill})
                        logger.info(f"[SyncProviders] Updated original_cost=${bill} for '{provider_name}'")
                except Exception as e:
                    logger.warning(f"[SyncProviders] Failed to update bill for '{provider_name}': {e}")

    result = {
        "case_id": case_id,
        "total_providers": len(providers),
        "providers_missing_bill": len(providers_missing_bill),
        "bill_updates_made": len(updates_made),
        "updates": updates_made,
        "providers": [
            {
                "name": p["provider_name"],
                "bill": p["bill_amount"],
                "offered": p["offered_amount"],
                "email": p.get("email", ""),
                "phone": p.get("phone", ""),
                "lien_id": p.get("lien_id", ""),
            }
            for p in providers
        ],
    }
    logger.info(f"[SyncProviders] Complete: {result['total_providers']} providers, {result['bill_updates_made']} bills updated")
    return result


def _get_extracted_texts(case_id: str) -> List[str]:
    """Pull any extracted document text stored from classification."""
    texts = []
    try:
        from turso_client import turso
        # conversation_history may contain extracted text from AI classification
        rows = turso.fetch_all(
            "SELECT messages_json FROM conversation_history WHERE case_id = ?",
            [case_id]
        )
        for row in rows:
            raw = row.get("messages_json", "")
            try:
                msgs = json.loads(raw) if isinstance(raw, str) else raw
                for m in (msgs if isinstance(msgs, list) else []):
                    content = m.get("content", "")
                    if isinstance(content, str) and len(content) > 50:
                        texts.append(content)
            except Exception:
                pass
    except Exception as e:
        logger.debug(f"[SyncProviders] Could not fetch extracted texts: {e}")
    return texts


def _find_bill_in_texts(provider_name: str, texts: List[str]) -> Optional[float]:
    """
    Search extracted document texts for a bill amount associated with the provider name.
    Returns the dollar amount if found, else None.
    """
    if not provider_name or not texts:
        return None

    # Normalize provider name for matching
    name_parts = [w.lower() for w in re.split(r'\W+', provider_name) if len(w) >= 4]
    if not name_parts:
        return None

    for text in texts:
        text_lower = text.lower()
        # Check if this text mentions the provider
        if not any(part in text_lower for part in name_parts):
            continue

        # Look for dollar amounts near provider name
        # Find all dollar amounts in the text
        amounts = re.findall(r'\$[\d,]+(?:\.\d{2})?', text)
        for amt_str in amounts:
            try:
                amt = float(re.sub(r'[^0-9.]', '', amt_str))
                if amt > 0:
                    return amt
            except Exception:
                pass

    return None
