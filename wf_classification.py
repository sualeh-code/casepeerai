"""
Workflow: AI Document Classification

Replicates the n8n New Classification workflow.
Classifies case documents using AI (Gemini for PDFs, GPT-4o for images).

Flow:
1. Fetch all documents for a case from CasePeer API
2. Download each document
3. Classify using AI (Gemini 2.5 Pro for PDFs, GPT-4o for images)
4. Update document categories in CasePeer
5. Log classification results
"""

import asyncio
import base64
import json
import logging
import re
from typing import Dict, Any, List, Optional

import requests as http_requests

from casepeer_helpers import casepeer_get, get_local_base

logger = logging.getLogger(__name__)

# 37 classification categories from the n8n workflow
CLASSIFICATION_CATEGORIES = [
    "Medical Records", "Medical Bills", "Imaging (MRI/CT/X-Ray)",
    "Lab Results", "Pharmacy Records", "Surgical Report",
    "Physical Therapy Notes", "Chiropractic Records", "Mental Health Records",
    "Dental Records", "Insurance Correspondence", "Police Report",
    "Accident Report", "Photos (Accident/Injuries)", "Property Damage Records",
    "Demand Letter", "Settlement Documents", "Lien Documents",
    "Attorney Correspondence", "Client Correspondence", "Court Documents",
    "Pleadings", "Discovery Documents", "Deposition Transcripts",
    "Expert Reports", "Employment Records", "Lost Wages Documentation",
    "Social Security Records", "Prior Medical Records", "Birth Certificate",
    "Death Certificate", "Power of Attorney", "Signed Retainer/Agreement",
    "ID/Identification", "Check/Payment", "Other Legal Documents",
    "Miscellaneous/Unclassified",
]


async def run_classification(case_id: str) -> Dict[str, Any]:
    """
    Classify all documents for a case using AI.
    Returns summary of classifications made.
    """
    from turso_client import get_setting, turso
    import os

    logger.info(f"[Classification] Starting for case {case_id}")

    gemini_key = get_setting("gemini_api_key") or os.getenv("GEMINI_API_KEY", "")
    openai_key = get_setting("openai_api_key") or os.getenv("OPENAI_API_KEY", "")

    if not gemini_key and not openai_key:
        return {"error": "No AI API keys configured (need gemini_api_key or openai_api_key)", "case_id": case_id}

    # 1. Fetch all documents for the case
    documents = await asyncio.to_thread(_fetch_case_documents, case_id)
    if not documents:
        return {"case_id": case_id, "classified": 0, "message": "No documents found"}

    logger.info(f"[Classification] Found {len(documents)} documents for case {case_id}")

    # 2. Classify each document
    classified = []
    errors = []

    for doc in documents:
        doc_id = doc.get("id", "")
        doc_name = doc.get("name", doc.get("docname", ""))
        doc_type = doc.get("file_type", "").lower()

        # Skip already classified documents
        if doc.get("category") and doc["category"] != "Miscellaneous/Unclassified":
            continue

        try:
            # 1. Try filename-based classification first (fast, no download needed)
            category = _classify_by_name(doc_name)

            # 2. Only download + AI classify if filename couldn't determine category
            if category == "Miscellaneous/Unclassified":
                is_pdf = doc_type in ("pdf", "application/pdf") or doc_name.lower().endswith(".pdf")
                is_image = doc_type in ("jpg", "jpeg", "png", "image/jpeg", "image/png") or \
                           any(doc_name.lower().endswith(ext) for ext in [".jpg", ".jpeg", ".png"])

                if (is_pdf and gemini_key) or (is_image and openai_key):
                    doc_bytes = await asyncio.to_thread(_download_document, case_id, doc_id)
                    if doc_bytes:
                        if is_pdf and gemini_key:
                            ai_category = await asyncio.to_thread(
                                _classify_with_gemini, doc_bytes, doc_name, gemini_key
                            )
                        elif is_image and openai_key:
                            ai_category = await asyncio.to_thread(
                                _classify_with_gpt4o, doc_bytes, doc_name, openai_key
                            )
                        else:
                            ai_category = None
                        if ai_category and ai_category != "Miscellaneous/Unclassified":
                            category = ai_category

            if category:
                classified.append({
                    "doc_id": doc_id,
                    "name": doc_name,
                    "category": category,
                    "confidence": 0.8 if category != "Miscellaneous/Unclassified" else 0.3,
                })
                logger.info(f"[Classification] {doc_name} → {category}")

        except Exception as e:
            logger.error(f"[Classification] Error classifying {doc_name}: {e}")
            errors.append({"doc_id": doc_id, "name": doc_name, "error": str(e)})

    # 3. Log classification results to Turso
    if classified:
        try:
            turso.execute(
                "INSERT INTO classifications (case_id, ocr_performed, number_of_documents, confidence) VALUES (?, ?, ?, ?)",
                [case_id, 1 if gemini_key or openai_key else 0, len(classified),
                 sum(c["confidence"] for c in classified) / len(classified)]
            )
        except Exception as e:
            logger.warning(f"[Classification] Failed to log to Turso: {e}")

    # 4. Update known_cases classification status
    try:
        turso.execute(
            "UPDATE known_cases SET classification_status = 'completed' WHERE case_id = ?",
            [case_id]
        )
    except Exception:
        pass

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
        if isinstance(result, dict) and "error" in result:
            break
        if isinstance(result, list):
            if not result:
                break
            documents.extend(result)
            page += 1
            if len(result) < 20:  # Assume page size is ~20
                break
        elif isinstance(result, dict):
            results = result.get("results", result.get("documents", []))
            if not results:
                break
            documents.extend(results)
            if not result.get("next"):
                break
            page += 1
        else:
            break

    return documents


def _download_document(case_id: str, doc_id: str) -> Optional[bytes]:
    """Download a document from CasePeer."""
    import requests as req
    base = get_local_base()
    try:
        resp = req.get(
            f"{base}/api/v1/case/case-documents/{case_id}/{doc_id}/download/",
            timeout=60,
        )
        if resp.status_code == 200:
            return resp.content
        logger.warning(f"[Classification] Document download failed: {resp.status_code}")
        return None
    except Exception as e:
        logger.error(f"[Classification] Document download error: {e}")
        return None


# ---------------------------------------------------------------------------
# AI classification
# ---------------------------------------------------------------------------

def _classify_with_gemini(doc_bytes: bytes, filename: str, api_key: str) -> str:
    """Classify a PDF document using Gemini 2.5 Pro."""
    doc_b64 = base64.standard_b64encode(doc_bytes).decode("ascii")
    categories_str = ", ".join(f'"{c}"' for c in CLASSIFICATION_CATEGORIES)

    prompt = (
        f"Classify this document into exactly ONE of these categories: [{categories_str}]\n\n"
        f"Document filename: {filename}\n\n"
        "Return ONLY the category name, nothing else. No quotes, no explanation."
    )

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
                }]
            },
            timeout=60,
        )

        if resp.status_code != 200:
            logger.error(f"[Gemini] Classification failed: {resp.status_code}")
            return _classify_by_name(filename)

        result = resp.json()
        text = result.get("candidates", [{}])[0].get("content", {}).get("parts", [{}])[0].get("text", "").strip()

        # Match against known categories
        for cat in CLASSIFICATION_CATEGORIES:
            if cat.lower() in text.lower():
                return cat

        return text if text else "Miscellaneous/Unclassified"

    except Exception as e:
        logger.error(f"[Gemini] Classification error: {e}")
        return _classify_by_name(filename)


def _classify_with_gpt4o(doc_bytes: bytes, filename: str, api_key: str) -> str:
    """Classify an image document using GPT-4o."""
    from openai import OpenAI
    doc_b64 = base64.standard_b64encode(doc_bytes).decode("ascii")
    mime = "image/jpeg" if filename.lower().endswith((".jpg", ".jpeg")) else "image/png"
    categories_str = ", ".join(f'"{c}"' for c in CLASSIFICATION_CATEGORIES)

    try:
        client = OpenAI(api_key=api_key)
        response = client.chat.completions.create(
            model="gpt-4o",
            messages=[{
                "role": "user",
                "content": [
                    {"type": "text", "text": f"Classify this document image into exactly ONE category: [{categories_str}]. Return ONLY the category name."},
                    {"type": "image_url", "image_url": {"url": f"data:{mime};base64,{doc_b64}"}}
                ]
            }],
            max_tokens=50,
            temperature=0,
        )
        text = response.choices[0].message.content.strip()

        for cat in CLASSIFICATION_CATEGORIES:
            if cat.lower() in text.lower():
                return cat

        return text if text else "Miscellaneous/Unclassified"

    except Exception as e:
        logger.error(f"[GPT-4o] Classification error: {e}")
        return _classify_by_name(filename)


def _classify_by_name(filename: str) -> str:
    """Classify based on filename keywords. Checked in priority order."""
    name_lower = filename.lower()

    # Priority-ordered list (first match wins)
    keyword_map = [
        # Medical Bills
        ("bill", "Medical Bills"),
        ("invoice", "Medical Bills"),
        ("ub04", "Medical Bills"),
        ("ub-04", "Medical Bills"),
        ("hicfa", "Medical Bills"),
        ("hcfa", "Medical Bills"),
        ("cms 1500", "Medical Bills"),
        ("cms-1500", "Medical Bills"),
        ("charges", "Medical Bills"),
        ("statement of account", "Medical Bills"),

        # Imaging
        ("mri", "Imaging (MRI/CT/X-Ray)"),
        ("xray", "Imaging (MRI/CT/X-Ray)"),
        ("x-ray", "Imaging (MRI/CT/X-Ray)"),
        ("x ray", "Imaging (MRI/CT/X-Ray)"),
        ("ct scan", "Imaging (MRI/CT/X-Ray)"),
        ("diagnostic imaging", "Imaging (MRI/CT/X-Ray)"),
        ("radiology", "Imaging (MRI/CT/X-Ray)"),
        ("imaging record", "Imaging (MRI/CT/X-Ray)"),

        # Surgical
        ("operative report", "Surgical Report"),
        ("operative", "Surgical Report"),
        ("surgical", "Surgical Report"),
        ("surgery", "Surgical Report"),
        ("procedure", "Surgical Report"),
        ("op report", "Surgical Report"),

        # Physical Therapy
        ("physical therapy", "Physical Therapy Notes"),
        ("select pt", "Physical Therapy Notes"),
        ("plan of care", "Physical Therapy Notes"),
        ("pt note", "Physical Therapy Notes"),
        ("pt -", "Physical Therapy Notes"),
        ("eval note", "Physical Therapy Notes"),
        ("initial eval", "Physical Therapy Notes"),

        # Lien Documents
        ("lien", "Lien Documents"),
        ("lien letter", "Lien Documents"),
        ("intake_lien", "Lien Documents"),

        # Settlement / Release
        ("full and final", "Settlement Documents"),
        ("settlement", "Settlement Documents"),
        ("release", "Settlement Documents"),
        ("signed release", "Settlement Documents"),

        # Attorney Correspondence
        ("rep letter", "Attorney Correspondence"),
        ("representation letter", "Attorney Correspondence"),
        ("attorney letter", "Attorney Correspondence"),
        ("plaintiff adjuster", "Attorney Correspondence"),
        ("defendant adjuster", "Attorney Correspondence"),
        ("adjuster", "Attorney Correspondence"),

        # Insurance
        ("eor", "Insurance Correspondence"),
        ("explanation of review", "Insurance Correspondence"),
        ("eob", "Insurance Correspondence"),
        ("explanation of benefit", "Insurance Correspondence"),
        ("insurance", "Insurance Correspondence"),
        ("certificate of no record", "Insurance Correspondence"),

        # Medical Records
        ("medical record", "Medical Records"),
        ("records affidavit", "Medical Records"),
        ("medical review", "Medical Records"),
        ("npv", "Medical Records"),
        ("patient record", "Medical Records"),
        ("clinical note", "Medical Records"),
        ("treatment record", "Medical Records"),
        ("fu.", "Medical Records"),
        ("follow up", "Medical Records"),
        ("initial.", "Medical Records"),

        # Chiropractic
        ("chiro", "Chiropractic Records"),

        # Lab
        ("lab", "Lab Results"),
        ("pathology", "Lab Results"),

        # Pharmacy
        ("pharmacy", "Pharmacy Records"),
        ("prescription", "Pharmacy Records"),
        ("rx", "Pharmacy Records"),

        # Mental Health
        ("mental health", "Mental Health Records"),
        ("psych", "Mental Health Records"),
        ("counseling", "Mental Health Records"),

        # Police / Accident
        ("police report", "Police Report"),
        ("police", "Police Report"),
        ("accident report", "Accident Report"),
        ("accident", "Accident Report"),
        ("crash report", "Accident Report"),

        # Photos
        ("photo", "Photos (Accident/Injuries)"),
        ("injury photo", "Photos (Accident/Injuries)"),

        # Demand
        ("demand", "Demand Letter"),
        ("demand letter", "Demand Letter"),

        # Retainer / Agreement
        ("retainer", "Signed Retainer/Agreement"),
        ("agreement", "Signed Retainer/Agreement"),
        ("please sign", "Signed Retainer/Agreement"),

        # Legal Documents
        ("affidavit", "Other Legal Documents"),
        ("w-9", "Other Legal Documents"),
        ("w9", "Other Legal Documents"),
        ("order form", "Other Legal Documents"),
        ("power of attorney", "Power of Attorney"),
        ("poa", "Power of Attorney"),

        # ID
        ("id card", "ID/Identification"),
        ("driver", "ID/Identification"),
        ("identification", "ID/Identification"),

        # Check/Payment
        ("check", "Check/Payment"),
        ("payment", "Check/Payment"),
        ("deposit", "Check/Payment"),

        # Dental
        ("dental", "Dental Records"),

        # Court / Discovery
        ("court", "Court Documents"),
        ("pleading", "Pleadings"),
        ("discovery", "Discovery Documents"),
        ("deposition", "Deposition Transcripts"),
        ("expert report", "Expert Reports"),

        # Employment / Wages
        ("employment", "Employment Records"),
        ("lost wage", "Lost Wages Documentation"),
        ("wage", "Lost Wages Documentation"),

        # Property Damage
        ("property damage", "Property Damage Records"),
    ]

    for keyword, category in keyword_map:
        if keyword in name_lower:
            return category
    return "Miscellaneous/Unclassified"
