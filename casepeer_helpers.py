"""
Shared CasePeer HTTP helpers — used by negotiation_agent.py and all workflow modules.

Provides authenticated GET/POST to CasePeer through the local proxy,
plus common HTML parsing utilities.
"""

import json
import logging
import os
import re
from typing import Dict, Any, Optional, List

import requests as req
from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Base URL helper
# ---------------------------------------------------------------------------

def get_local_base() -> str:
    """Get the local proxy URL, respecting Render's PORT env var."""
    port = os.getenv("PORT", "8000")
    return f"http://localhost:{port}"


# ---------------------------------------------------------------------------
# CasePeer proxy requests
# ---------------------------------------------------------------------------

def casepeer_get(endpoint: str, timeout: int = 90) -> Dict[str, Any]:
    """Make a GET request through the CasePeer proxy (internal)."""
    base = get_local_base()
    try:
        resp = req.get(f"{base}/{endpoint.lstrip('/')}", timeout=timeout)
        resp.raise_for_status()
        return resp.json()
    except Exception as e:
        logger.error(f"CasePeer GET {endpoint} failed: {e}")
        return {"error": str(e)}


def casepeer_post(endpoint: str, data: Dict = None,
                  content_type: str = "application/json",
                  timeout: int = 90) -> Dict[str, Any]:
    """Make a POST request through the CasePeer proxy (internal)."""
    base = get_local_base()
    try:
        if content_type == "application/x-www-form-urlencoded":
            resp = req.post(f"{base}/{endpoint.lstrip('/')}", data=data, timeout=timeout)
        elif content_type == "multipart/form-data":
            resp = req.post(f"{base}/{endpoint.lstrip('/')}", data=data, timeout=timeout)
        else:
            resp = req.post(f"{base}/{endpoint.lstrip('/')}", json=data, timeout=timeout)
        resp.raise_for_status()
        return resp.json()
    except Exception as e:
        logger.error(f"CasePeer POST {endpoint} failed: {e}")
        return {"error": str(e)}


def casepeer_post_form(endpoint: str, form_body: str, timeout: int = 90) -> req.Response:
    """POST url-encoded form data (raw string) and return the response object."""
    base = get_local_base()
    return req.post(
        f"{base}/{endpoint.lstrip('/')}",
        data=form_body,
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        timeout=timeout,
    )


def casepeer_get_raw(endpoint: str, timeout: int = 90) -> req.Response:
    """GET and return the raw response object (for binary downloads etc.)."""
    base = get_local_base()
    return req.get(f"{base}/{endpoint.lstrip('/')}", timeout=timeout)


# ---------------------------------------------------------------------------
# HTML extraction helpers
# ---------------------------------------------------------------------------

def extract_html(result: Dict) -> str:
    """Extract HTML string from a proxy response dict."""
    if isinstance(result, dict):
        return result.get("response", "")
    return ""


def _decode_unicode_escapes(s: str) -> str:
    """Decode all \\uXXXX sequences (e.g. \\u0022 → \", \\u003C → <)."""
    return re.sub(r'\\u([0-9a-fA-F]{4})', lambda m: chr(int(m.group(1), 16)), s)


def extract_script_json(html: str, var_name: str) -> Any:
    """
    Extract a JSON value assigned to a window variable in embedded <script> tags.
    Handles: JSON.parse('...'), JSON.parse("..."), and direct assignment.
    Decodes all \\uXXXX unicode escapes before JSON parsing.
    """
    soup = BeautifulSoup(html, "html.parser")
    for script in soup.select("script"):
        text = script.string or ""
        if var_name not in text:
            continue

        # Try JSON.parse('...') format (single quotes)
        pattern = rf"window\.{var_name}\s*=\s*JSON\.parse\(\s*'(.*?)'\s*\)"
        match = re.search(pattern, text, re.DOTALL)
        if match:
            try:
                return json.loads(_decode_unicode_escapes(match.group(1)))
            except json.JSONDecodeError:
                pass

        # Try JSON.parse("...") format (double quotes with unicode escapes)
        pattern_dq = rf'window\.{var_name}\s*=\s*JSON\.parse\(\s*"(.*?)"\s*\)'
        match_dq = re.search(pattern_dq, text, re.DOTALL)
        if match_dq:
            try:
                return json.loads(_decode_unicode_escapes(match_dq.group(1)))
            except json.JSONDecodeError:
                pass

        # Try JSON.parse(String.raw`...`) or JSON.parse(`...`) (template literals)
        pattern_tl = rf"window\.{var_name}\s*=\s*JSON\.parse\(\s*(?:String\.raw)?`(.*?)`\s*\)"
        match_tl = re.search(pattern_tl, text, re.DOTALL)
        if match_tl:
            try:
                return json.loads(_decode_unicode_escapes(match_tl.group(1)))
            except json.JSONDecodeError:
                pass

        # Try direct assignment: window.VAR = [...]; or window.VAR = {...};
        pattern2 = rf"window\.{var_name}\s*=\s*(\[.*?\]|\{{.*?\}});?"
        match2 = re.search(pattern2, text, re.DOTALL)
        if match2:
            try:
                return json.loads(match2.group(1))
            except json.JSONDecodeError:
                pass

        # Last resort: grab everything after = up to the first ;
        pattern3 = rf"window\.{var_name}\s*=\s*(.*?);"
        match3 = re.search(pattern3, text, re.DOTALL)
        if match3:
            raw = match3.group(1).strip()
            jp_match = re.match(r'JSON\.parse\(\s*["\']?(.*?)["\']?\s*\)$', raw, re.DOTALL)
            if jp_match:
                raw = _decode_unicode_escapes(jp_match.group(1))
            try:
                return json.loads(raw)
            except json.JSONDecodeError:
                logger.warning(f"[Helpers] Found {var_name} but failed to parse. First 200 chars: {raw[:200]}")

    return None


def extract_case_ids_from_html(html: str) -> List[str]:
    """Extract unique case IDs from CasePeer HTML (pattern: /case/{id}/)."""
    ids = list(dict.fromkeys(re.findall(r'/case/(\d+)/', html)))
    return ids


def extract_id_from_url(html: str, pattern: str) -> Optional[str]:
    """Extract a numeric ID from a URL pattern in HTML."""
    match = re.search(pattern, html)
    return match.group(1) if match else None


def parse_dollar_amount(text: str) -> float:
    """Parse a dollar string like '$1,234.56' or '35k' into a float."""
    if not text:
        return 0.0
    text = text.strip()
    # Handle 'k' suffix (e.g. "35k" -> 35000)
    k_match = re.search(r'([\d,.]+)\s*k', text, re.IGNORECASE)
    if k_match:
        return float(k_match.group(1).replace(",", "")) * 1000
    # Standard dollar parsing
    cleaned = re.sub(r'[^0-9.]', '', text)
    return float(cleaned) if cleaned else 0.0


# ---------------------------------------------------------------------------
# Contact Directory lookup
# ---------------------------------------------------------------------------

def lookup_contact_directory(provider_name: str, contact_type_id: int = 4) -> List[Dict]:
    """
    Search CasePeer's contact directory for a provider.
    Returns list of matching contacts with name, email, phone, address.
    """
    search_term = provider_name.replace(" ", "+")
    endpoint = (
        f"contact-directory/?contact_type_id={contact_type_id}"
        f"&search%5Bvalue%5D={search_term}"
        f"&start=0&length=25"
    )
    result = casepeer_get(endpoint)
    html = extract_html(result)
    if not html:
        # Try parsing as DataTables JSON response
        if isinstance(result, dict) and "data" in result:
            return result["data"]
        return []

    # Parse HTML table rows if returned as HTML
    soup = BeautifulSoup(html, "html.parser")
    contacts = []
    for row in soup.select("tr"):
        cells = row.select("td")
        if len(cells) >= 3:
            contact = {
                "name": cells[0].get_text(strip=True) if cells else "",
                "email": "",
                "phone": "",
                "address": "",
            }
            # Extract email from mailto links
            email_link = row.select_one("a[href^='mailto:']")
            if email_link:
                contact["email"] = email_link.get("href", "").replace("mailto:", "")
            # Extract phone
            phone_link = row.select_one("a[href^='tel:']")
            if phone_link:
                contact["phone"] = phone_link.get("href", "").replace("tel:", "")
            # Get full text for address extraction
            contact["full_text"] = row.get_text(" ", strip=True)
            contacts.append(contact)
    return contacts


# ---------------------------------------------------------------------------
# Common CasePeer page scrapers
# ---------------------------------------------------------------------------

def get_treatment_providers(case_id: str) -> Dict[str, Any]:
    """
    Scrape the treatment page and return structured provider data with offer calculations.
    MRI=$400, X-Ray=$50, others = 2/3 of 33% of bill.
    """
    result = casepeer_get(f"case/{case_id}/medical/treatment/")
    html = extract_html(result)
    if not html:
        return {"error": "No HTML returned from treatment page"}

    soup = BeautifulSoup(html, "html.parser")

    # Patient name from panel-title
    patient_name = ""
    panel_title = soup.select_one(".panel-title")
    if panel_title:
        patient_name = panel_title.get_text(strip=True)

    # Extract patient DOB and incident date from page content
    patient_dob = ""
    incident_date = ""
    page_text = soup.get_text()
    dob_match = re.search(r'Date of Birth[:\s]+([0-9/\-]+)', page_text)
    if dob_match:
        patient_dob = dob_match.group(1)
    incident_match = re.search(r'(?:Date of (?:Injury|Incident)|DOI)[:\s]+([0-9/\-]+)', page_text)
    if incident_match:
        incident_date = incident_match.group(1)

    # Extract HEALTH_LIENS_DATA and LIEN_LETTERS from embedded scripts
    health_liens_data = extract_script_json(html, "HEALTH_LIENS_DATA") or []
    lien_letters = extract_script_json(html, "LIEN_LETTERS") or []
    logger.info(f"[Helpers] HEALTH_LIENS_DATA found: {len(health_liens_data)} items, LIEN_LETTERS: {len(lien_letters)} items")
    if not health_liens_data:
        # Debug: check if the variable exists in HTML at all
        has_health = "HEALTH_LIENS_DATA" in html
        has_lien = "LIEN_LETTERS" in html
        logger.warning(f"[Helpers] HEALTH_LIENS_DATA in HTML: {has_health}, LIEN_LETTERS in HTML: {has_lien}, HTML length: {len(html)}")

    # Calculate offers for each provider
    providers = []
    for lien in health_liens_data:
        # Extract from nested CasePeer structure
        contact = lien.get("contact", {})
        details = contact.get("details", {})
        addresses = details.get("addresses", {})
        physical = addresses.get("physical", {})

        name = details.get("company") or details.get("displayname") or "Unknown"
        specialties = (lien.get("contact_specialties") or "").lower()
        email = physical.get("email", "")
        phone = physical.get("phone", "")
        address_pt1 = physical.get("address_pt_1", "")
        address_pt2 = physical.get("address_pt_2", "")
        provider_address = f"{address_pt1}, {address_pt2}" if address_pt1 else ""

        # Bill amount: prefer original_cost, fall back to final_cost, still_owed
        bill_str = str(lien.get("original_cost") or lien.get("final_cost") or lien.get("still_owed") or "0")
        bill = parse_dollar_amount(bill_str)

        # Detect MRI/X-Ray from name or specialties
        name_lower = name.lower()
        is_mri = "mri" in name_lower or "mri" in specialties or "imaging" in name_lower
        is_xray = any(x in name_lower for x in ["x-ray", "xray"]) or \
                   any(x in specialties for x in ["x-ray", "xray", "radiology"])

        if is_mri:
            offered = 400.0
            reason = "MRI fixed rate"
        elif is_xray:
            offered = 50.0
            reason = "X-Ray fixed rate"
        else:
            max_offer = bill * 0.33
            offered = round(max_offer * (2 / 3), 2)
            reason = "2/3 of 33% of bill"

        providers.append({
            "provider_name": name,
            "specialties": specialties,
            "bill_amount": bill,
            "offered_amount": offered,
            "max_offer_33pct": round(bill * 0.33, 2),
            "offer_reason": reason,
            "lien_id": str(lien.get("id", "")),
            "phone": phone,
            "email": email,
            "address": provider_address,
        })

    # Find the "No Details Offer to Settle" letter template ID
    offer_letter_id = ""
    for letter in lien_letters:
        letter_name = str(letter.get("label", letter.get("name", ""))).lower()
        if "no details" in letter_name and "offer" in letter_name:
            offer_letter_id = str(letter.get("value", letter.get("id", "")))
            break

    return {
        "patient_name": patient_name,
        "patient_dob": patient_dob,
        "incident_date": incident_date,
        "providers": providers,
        "lien_letters": lien_letters,
        "offer_letter_template_id": offer_letter_id,
        "health_liens_count": len(health_liens_data),
    }


def get_settlement_page(case_id: str) -> Dict[str, Any]:
    """Fetch and parse the settlement/negotiations page for a case."""
    result = casepeer_get(f"case/{case_id}/settlement/negotiations/")
    html = extract_html(result)
    if not html:
        return {"error": "No HTML returned from settlement page"}

    soup = BeautifulSoup(html, "html.parser")
    providers = []

    rows = soup.select("tr")
    for row in rows:
        cells = row.select("td")
        if len(cells) >= 3:
            name_cell = row.select_one(".nopad.bottom.wordbreak")
            if name_cell:
                provider_name = name_cell.get_text(strip=True)
                link = row.select_one("a[href*='accept-unaccept']")
                provider_id = ""
                if link:
                    href = link.get("href", "")
                    id_match = re.search(r'/(\d+)/?$', href)
                    if id_match:
                        provider_id = id_match.group(1)
                amounts = re.findall(r'\$[\d,]+\.?\d*', row.get_text())
                providers.append({
                    "provider_name": provider_name,
                    "provider_id": provider_id,
                    "amounts": amounts,
                })

    # Extract form fields
    form_data = {}
    for inp in soup.select("input[name]"):
        name = inp.get("name", "")
        value = inp.get("value", "")
        if name.startswith("health-liens") or name == "csrfmiddlewaretoken":
            form_data[name] = value

    return {
        "providers": providers,
        "form_fields": form_data,
        "raw_html": html,
    }


def get_defendant_data(case_id: str) -> Dict[str, Any]:
    """Scrape the defendant page and extract insurance ID and deposited amount."""
    result = casepeer_get(f"case/{case_id}/defendant/defendant/")
    html = extract_html(result)
    if not html:
        return {"error": "No HTML returned from defendant page"}

    soup = BeautifulSoup(html, "html.parser")

    # Extract defendant name from title
    full_name = ""
    title = soup.select_one("title")
    if title:
        name_match = re.match(r'(.*?)\s*-\s*Defendant', title.get_text())
        if name_match:
            full_name = name_match.group(1).strip()

    # Extract insurance ID from URL pattern
    insurance_id = ""
    ins_link = soup.select_one("a[href*='/defendant/insurance/']")
    if ins_link:
        ins_match = re.search(r'/defendant/insurance/(\d+)/', ins_link.get("href", ""))
        if ins_match:
            insurance_id = ins_match.group(1)

    # Try to extract deposited amount from notes/content
    deposited_amount = 0.0
    page_text = soup.get_text()
    # Look for patterns like "check deposited 35k", "deposited $35,000"
    dep_match = re.search(r'(?:deposit(?:ed)?|check)\s+\$?([\d,.]+k?)', page_text, re.IGNORECASE)
    if dep_match:
        deposited_amount = parse_dollar_amount(dep_match.group(1))

    return {
        "full_name": full_name,
        "insurance_id": insurance_id,
        "deposited_amount": deposited_amount,
    }


def add_case_note(case_id: str, note: str) -> Dict:
    """Add a note to a CasePeer case."""
    base = get_local_base()
    try:
        resp = req.post(
            f"{base}/case/{case_id}/notes/add-case-note/",
            data={"note": note, "time_worked": ""},
            timeout=90,
        )
        return {"success": True}
    except Exception as e:
        return {"error": str(e)}
