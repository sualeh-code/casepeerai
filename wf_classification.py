"""
Workflow: AI Document Classification

Classifies case documents using AI, renames them with standardized names,
and updates categories + filenames back in CasePeer.

Flow:
1. Fetch all documents for a case from CasePeer API
2. Download each document
3. Classify using AI (Gemini 2.5 Pro for PDFs, GPT-4o-mini for images)
   - AI returns: categoryID (4441-4477), file_name, extracted_text
4. PATCH /version-document/edit/{doc_id}/ with docname + custom_categories
5. Log results + update cases table
"""

import asyncio
import base64
import json
import logging
import re
from typing import Dict, Any, List, Optional

import requests as http_requests

from casepeer_helpers import casepeer_get, casepeer_patch, get_local_base

logger = logging.getLogger(__name__)

# CasePeer's actual category IDs (4441–4477)
CASEPEER_CATEGORIES = {
    4441: "Accounting",
    4442: "Attorney Designation",
    4443: "Case Notes",
    4444: "Client Correspondence",
    4445: "Client Portal",
    4446: "Contracts",
    4447: "Costs",
    4448: "Court Filings",
    4449: "Defendant Correspondence",
    4450: "Defendant Insurance",
    4451: "Depositions",
    4452: "Discovery",
    4453: "DMV",
    4454: "Evidence",
    4455: "Expert Witnesses",
    4456: "Health Insurance",
    4457: "Incident Report",
    4458: "Intake Documents",
    4459: "Invoices",
    4460: "Lien Negotiations",
    4461: "Loans",
    4462: "Lost Wages",
    4463: "Mediation",
    4464: "Medical Authorizations",
    4465: "Medical Payment",
    4466: "Medical Requests",
    4467: "Medical Treatment",
    4468: "Miscellaneous",
    4469: "Plaintiff Insurance",
    4470: "Pleadings",
    4471: "Property Damage",
    4472: "Research",
    4473: "Service Paperwork",
    4474: "Settlement",
    4475: "Subpoena",
    4476: "Trial Exhibits",
    4477: "Witness Statement",
}
CATEGORIES_JSON = json.dumps([{"id": k, "name": v} for k, v in CASEPEER_CATEGORIES.items()])

CLASSIFICATION_PROMPT = """You are an expert document classification AI specializing in legal and medical document categorization.

TASK: Analyze the provided document, extract ALL text content, and classify it into exactly ONE category from this list:
{categories}

CLASSIFICATION RULES (Priority Order):
1. Medical Treatment (4467) — medical bills, invoices, line items with charges, amounts due, CPT codes, "balance due", "total charges", "please remit payment"
2. Settlement (4474) — settlement agreements, release forms, policy limits letters
3. Property Damage (4471) — auto body estimates, vehicle repair bills
4. Medical Authorizations (4464) — HIPAA/consent forms signed by patient
5. Medical Requests (4466) — letters requesting medical records
6. Lien Negotiations (4460) — lien reduction letters, lien resolution agreements
7. Defendant Insurance (4450) — defendant/at-fault party insurance docs
8. Plaintiff Insurance (4469) — client's own insurance (PIP, med-pay, UIM)
9. Health Insurance (4456) — health insurance policy, Medicare/Medicaid
10. Incident Report (4457) — police reports, accident reports
11. Court Filings (4448) — complaints, motions, court-stamped docs
12. Lost Wages (4462) — employer wage verification, pay stubs for wage loss
13. Miscellaneous (4468) — anything that doesn't clearly fit

FILE NAMING FORMAT: LASTNAME, FIRSTNAME_PROVIDER_CONTEXT_$AMOUNT
- LASTNAME, FIRSTNAME — from patient name in doc (ALL CAPS, comma+space)
- PROVIDER — medical provider or source name (ALL CAPS, under 30 chars)
- CONTEXT (optional) — LIEN / CHECK / SETTLEMENT / AUTHORIZATION / RECORDS REQUEST / DEMAND / CORRESPONDENCE / ESTIMATE / EOB / CONTRACT / REPORT / POLICY LIMITS
- $AMOUNT (optional) — only if specific dollar amount in doc, format $X,XXX.00
- Omit context or amount if not applicable
Examples:
  KANONGATAA, LESIELI_APEX SURGERY CENTER_$23,150.00
  SMITH, JOHN_PRECISE IMAGING_LIEN_$4,400.00
  DOE, JANE_TRAVELERS_SETTLEMENT CHECK_$35,000.00
  GARCIA, MIGUEL_DIGNITY HEALTH_LIEN

Return ONLY valid JSON (no markdown fences):
{{
  "categoryID": "4467",
  "confidence": 0.99,
  "file_name": "LASTNAME, FIRSTNAME_PROVIDER_$AMOUNT",
  "extracted_text": "full text from document..."
}}
case_id for context: {case_id}
"""


async def run_classification(case_id: str) -> Dict[str, Any]:
    """
    Classify all documents for a case, rename them, and push updates to CasePeer.
    """
    from turso_client import get_setting, turso
    import os

    logger.info(f"[Classification] Starting for case {case_id}")

    gemini_key = get_setting("gemini_api_key") or os.getenv("GEMINI_API_KEY", "")
    openai_key = get_setting("openai_api_key") or os.getenv("OPENAI_API_KEY", "")

    if not gemini_key and not openai_key:
        return {"error": "No AI API keys configured (need gemini_api_key or openai_api_key)", "case_id": case_id}

    # 1. Fetch all documents
    documents = await asyncio.to_thread(_fetch_case_documents, case_id)
    if not documents:
        return {"case_id": case_id, "classified": 0, "message": "No documents found"}

    logger.info(f"[Classification] Found {len(documents)} documents for case {case_id}")

    classified = []
    errors = []

    for doc in documents:
        doc_id = str(doc.get("id", ""))
        doc_name = doc.get("name", doc.get("docname", ""))
        doc_type = doc.get("file_type", "").lower()

        try:
            is_pdf = doc_type in ("pdf", "application/pdf") or doc_name.lower().endswith(".pdf")
            is_image = doc_type in ("jpg", "jpeg", "png", "image/jpeg", "image/png") or \
                       any(doc_name.lower().endswith(ext) for ext in [".jpg", ".jpeg", ".png"])

            ai_result = None

            if is_pdf and gemini_key:
                doc_bytes = await asyncio.to_thread(_download_document, case_id, doc_id)
                if doc_bytes:
                    ai_result = await asyncio.to_thread(
                        _classify_with_gemini, doc_bytes, doc_name, case_id, gemini_key
                    )
            elif is_image and openai_key:
                doc_bytes = await asyncio.to_thread(_download_document, case_id, doc_id)
                if doc_bytes:
                    ai_result = await asyncio.to_thread(
                        _classify_with_gpt4o, doc_bytes, doc_name, case_id, openai_key
                    )

            # Fall back to filename-based classification
            if not ai_result:
                category_id, category_name = _classify_by_name(doc_name)
                ai_result = {
                    "categoryID": str(category_id),
                    "file_name": doc_name,
                    "confidence": 0.5,
                    "extracted_text": "",
                }

            category_id = int(ai_result.get("categoryID", 4468))
            new_name = ai_result.get("file_name", doc_name) or doc_name
            confidence = float(ai_result.get("confidence", 0.8))

            # 4. Push rename + category update to CasePeer
            patch_result = await asyncio.to_thread(
                casepeer_patch,
                f"version-document/edit/{doc_id}/",
                {"docname": new_name, "custom_categories": category_id}
            )
            logger.info(f"[Classification] Updated {doc_id}: '{new_name}' → cat {category_id} | patch: {patch_result.get('status_code', '?')}")

            classified.append({
                "doc_id": doc_id,
                "original_name": doc_name,
                "new_name": new_name,
                "category_id": category_id,
                "category_name": CASEPEER_CATEGORIES.get(category_id, "Unknown"),
                "confidence": confidence,
            })

        except Exception as e:
            logger.error(f"[Classification] Error on {doc_name}: {e}")
            errors.append({"doc_id": doc_id, "name": doc_name, "error": str(e)})

    # 5. Log to Turso
    if classified:
        try:
            turso.execute(
                "INSERT INTO classifications (case_id, ocr_performed, number_of_documents, confidence) VALUES (?, ?, ?, ?)",
                [case_id, 1, len(classified),
                 sum(c["confidence"] for c in classified) / len(classified)]
            )
        except Exception as e:
            logger.warning(f"[Classification] Failed to log to Turso: {e}")

    try:
        turso.execute("UPDATE cases SET classification_status = 'completed' WHERE id = ?", [case_id])
    except Exception:
        pass

    # Auto-trigger provider/bill sync after classification
    try:
        from workflow_scheduler import trigger_workflow
        await trigger_workflow("sync_providers", case_id, triggered_by="classification_auto")
        logger.info(f"[Classification] Auto-triggered sync_providers for case {case_id}")
    except Exception as e:
        logger.warning(f"[Classification] Could not trigger sync_providers: {e}")

    result = {
        "case_id": case_id,
        "total_documents": len(documents),
        "classified": len(classified),
        "errors": len(errors),
        "classifications": classified,
        "error_details": errors[:10],
    }
    logger.info(f"[Classification] Complete: {len(classified)} classified, {len(errors)} errors")
    return result


# ---------------------------------------------------------------------------
# Document fetching
# ---------------------------------------------------------------------------

def _fetch_case_documents(case_id: str) -> List[Dict]:
    """Fetch all documents for a case from CasePeer API."""
    documents = []
    page = 1
    while True:
        result = casepeer_get(f"api/v1/case/case-documents/{case_id}/?page={page}")
        raw = result.get("response", "")
        try:
            data = json.loads(raw) if isinstance(raw, str) else raw
        except Exception:
            break

        if isinstance(data, list):
            if not data:
                break
            documents.extend(data)
            page += 1
            if len(data) < 20:
                break
        elif isinstance(data, dict):
            results = data.get("results", data.get("documents", []))
            if not results:
                break
            documents.extend(results)
            if not data.get("next"):
                break
            page += 1
        else:
            break

    return documents


def _download_document(case_id: str, doc_id: str) -> Optional[bytes]:
    """Download a document from CasePeer."""
    from casepeer_helpers import casepeer_get_raw
    try:
        resp = casepeer_get_raw(f"api/v1/case/case-documents/{case_id}/{doc_id}/download/", timeout=60)
        if resp.status_code == 200:
            return resp.content
        logger.warning(f"[Classification] Download failed for {doc_id}: {resp.status_code}")
        return None
    except Exception as e:
        logger.error(f"[Classification] Download error for {doc_id}: {e}")
        return None


# ---------------------------------------------------------------------------
# AI classification
# ---------------------------------------------------------------------------

def _parse_ai_response(text: str) -> Optional[Dict]:
    """Parse AI JSON response, stripping markdown fences if present."""
    text = re.sub(r"```(?:json)?|```", "", text).strip()
    try:
        return json.loads(text)
    except Exception:
        # Try to extract JSON object
        match = re.search(r'\{.*\}', text, re.DOTALL)
        if match:
            try:
                return json.loads(match.group())
            except Exception:
                pass
    return None


def _classify_with_gemini(doc_bytes: bytes, filename: str, case_id: str, api_key: str) -> Optional[Dict]:
    """Classify a PDF using Gemini 2.5 Pro. Returns full AI result dict."""
    doc_b64 = base64.standard_b64encode(doc_bytes).decode("ascii")
    prompt = CLASSIFICATION_PROMPT.format(categories=CATEGORIES_JSON, case_id=case_id)

    try:
        resp = http_requests.post(
            f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-pro:generateContent?key={api_key}",
            headers={"Content-Type": "application/json"},
            json={
                "contents": [{
                    "parts": [
                        {"inline_data": {"mime_type": "application/pdf", "data": doc_b64}},
                        {"text": prompt}
                    ]
                }],
                "generationConfig": {"maxOutputTokens": 4096}
            },
            timeout=120,
        )
        if resp.status_code != 200:
            logger.error(f"[Gemini] {resp.status_code}: {resp.text[:200]}")
            return None

        raw = resp.json()
        text = raw.get("candidates", [{}])[0].get("content", {}).get("parts", [{}])[0].get("text", "")
        return _parse_ai_response(text)

    except Exception as e:
        logger.error(f"[Gemini] Error: {e}")
        return None


def _classify_with_gpt4o(doc_bytes: bytes, filename: str, case_id: str, api_key: str) -> Optional[Dict]:
    """Classify an image using GPT-4o-mini. Returns full AI result dict."""
    from openai import OpenAI
    doc_b64 = base64.standard_b64encode(doc_bytes).decode("ascii")
    mime = "image/jpeg" if filename.lower().endswith((".jpg", ".jpeg")) else "image/png"
    prompt = CLASSIFICATION_PROMPT.format(categories=CATEGORIES_JSON, case_id=case_id)

    try:
        client = OpenAI(api_key=api_key)
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[{
                "role": "user",
                "content": [
                    {"type": "text", "text": prompt},
                    {"type": "image_url", "image_url": {"url": f"data:{mime};base64,{doc_b64}"}}
                ]
            }],
            max_tokens=1024,
            temperature=0,
        )
        text = response.choices[0].message.content.strip()
        return _parse_ai_response(text)

    except Exception as e:
        logger.error(f"[GPT-4o] Error: {e}")
        return None


def _classify_by_name(filename: str):
    """Fallback: classify by filename keywords. Returns (category_id, category_name)."""
    name_lower = filename.lower()
    keyword_map = [
        ("bill", 4467), ("invoice", 4459), ("ub04", 4467), ("hicfa", 4467), ("hcfa", 4467),
        ("cms 1500", 4467), ("charges", 4467), ("statement of account", 4467),
        ("mri", 4467), ("xray", 4467), ("x-ray", 4467), ("ct scan", 4467), ("imaging", 4467),
        ("lien", 4460), ("settlement", 4474), ("release", 4474),
        ("demand", 4449), ("police report", 4457), ("accident report", 4457),
        ("retainer", 4446), ("agreement", 4446), ("intake", 4458),
        ("insurance", 4469), ("eob", 4456), ("authorization", 4464),
        ("medical record", 4467), ("records request", 4466),
        ("court", 4448), ("pleading", 4470), ("discovery", 4452), ("deposition", 4451),
        ("lost wage", 4462), ("wage", 4462), ("property damage", 4471),
        ("check", 4465), ("payment", 4465),
    ]
    for keyword, cat_id in keyword_map:
        if keyword in name_lower:
            return cat_id, CASEPEER_CATEGORIES.get(cat_id, "Unknown")
    return 4468, "Miscellaneous"
