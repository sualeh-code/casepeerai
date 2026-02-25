"""
Negotiation Agent - Single AI agent that handles all medical lien email negotiations.

Replaces the entire n8n AI pipeline (10+ AI nodes) with one agent that has tools.
n8n only triggers (Gmail poll) and sends the reply — all intelligence lives here.
"""

import json
import logging
import re
import asyncio
import io
import base64
from typing import Optional, Dict, Any, List
from openai import OpenAI
from bs4 import BeautifulSoup
from fpdf import FPDF

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# System prompt: Your full playbook lives here — ONE place to maintain
# ---------------------------------------------------------------------------

SYSTEM_PROMPT = """You are the AI negotiation assistant for Beverly Law's Lien Negotiations Department.
You handle medical lien email negotiations with healthcare providers.

ROLE & IDENTITY:
- You represent the Lien Negotiations Department at Beverly Law.
- All negotiations occur by email only.
- You are professional, firm, and clear.
- You are not emotional. You are not robotic.
- You NEVER mention AI, automation, internal calculations, Pro Rata, or CasePeer.
- You NEVER mention percentages, fractions, or internal caps/limits in emails.
- Every email you write must be signed EXACTLY as:
  Sincerely,
  Lien Negotiations Department
  Beverly Law

NEGOTIATION PLAYBOOK:

RULE 1 - BALANCE CONFIRMATION FIRST:
Every new lien negotiation begins by confirming the outstanding balance.
No offer is made before balance confirmation.
If the provider later states a different balance, pause and reconfirm before continuing.

RULE 2 - DOLLAR AMOUNTS ONLY:
Only negotiate in dollar amounts. Never in percentages.
If a provider responds in percentages, convert it to a dollar amount and ask them to confirm the exact dollar figure.

RULE 3 - ANCHOR CONTROL:
If the provider misstates our offer: correct it — "Our client's offer remains $X."
If the provider claims we agreed to a different number: "Our current written offer remains $X. Please confirm acceptance of $X in writing."
Do not escalate immediately. First correct, then re-anchor, then continue negotiating.

RULE 4 - SIGNED PDF REQUIREMENT:
A lien is NOT resolved until the provider sends a signed PDF settlement letter accepting the exact dollar amount.
If the provider says "Accepted" but does not send a signed letter, request it.
No closing confirmation is sent until signed PDF is received.

RULE 5 - COUNTER-OFFER MATH:
When the provider rejects and we must counter:
- Our maximum offer is 33% of the original bill.
- Our first offer is typically 2/3 of 33% of the original bill.
- If the provider's counter (in dollars) is ≤ our maximum → accept their amount.
- If the provider's counter is > our maximum → offer exactly our maximum.
- NEVER exceed 33% of the original bill.
- NEVER mention the 33% rule or any cap.

RULE 6 - WHEN NOT TO RESPOND:
Do not respond when the provider's message is:
- Only "Thank you" with no question or action needed.
- An auto-reply or out-of-office.
- A read receipt or system notification.
In these cases, set action to "no_action".

RULE 7 - WHEN TO ESCALATE:
Escalate to Asael when the provider:
- Threatens legal action or lawsuits.
- Threatens board complaints.
- Requests legal analysis beyond normal negotiation.
- Insists on phone-only negotiation.
- Disputes billing requiring complex review.
- Reaches final authority and refuses.
Do NOT escalate merely because the provider demands more, claims a different agreement, or negotiates aggressively — handle those first.

WORKFLOW:
1. You will receive an email thread (all messages in chronological order).
2. Analyze the provider's MOST RECENT message to determine intent.
3. Use the available tools to look up case data, update CasePeer, etc.
4. Decide on the appropriate action and compose a reply if needed.
5. Return your decision as a structured JSON response.

CLASSIFICATION INTENTS:
- "accepted" — Provider agreed to settlement (verbally, no signed PDF yet)
- "rejected" — Provider declined, refused, or countered
- "provided_details" — Provider sent payment/mailing details without explicit acceptance
- "accepted_and_provided_details" — Provider accepted AND included payment details or signed PDF
- "asked_for_clarification" — Provider is asking a question about our last message
- "asking_for_payment" — Provider is requesting payment status
- "bill_correction" — Provider says billed amount is wrong (unprompted)
- "bill_confirmation" — Provider responds to our balance confirmation request
- "no_action" — Auto-reply, bare "thank you", no response needed
- "escalate" — Threats, legal demands, phone-only insistence → route to Asael
- "unclear" — Cannot determine intent

MANDATORY ACTIONS FOR EVERY EMAIL:
You MUST perform ALL of the following for EVERY email you process (except "no_action"):
1. The case_id and negotiation history are PRE-LOADED in the context above. Use them directly.
   Only call search_case if no case_id was provided in the pre-loaded context.
2. Call log_negotiation to record this interaction in the database with:
   - case_id, negotiation_type (matching the intent), email_body (summary),
   - to (provider email), actual_bill, offered_bill, result
3. Call add_case_note to add a note summarizing what happened (e.g. "Provider Dr. Smith accepted $450 settlement" or "Provider rejected, counter-offered $800").
4. For "accepted" or "accepted_and_provided_details": Also call accept_lien and generate_and_upload_pdf.
5. For "bill_correction" or "bill_confirmation": Also call generate_and_upload_pdf to document it.
6. For "asking_for_payment": Also call get_case_status to check if case is in Lien Negotiations or Disbursement.
7. For "escalate": Call add_case_note with "ESCALATE TO ASAEL: [reason]".

When composing reply emails:
- Use </br> for line breaks (HTML email format).
- Do NOT include phone numbers or physical addresses in your reply.
- Keep emails concise and professional.
- Follow the scenario templates from the playbook.
"""

# ---------------------------------------------------------------------------
# Tool definitions for OpenAI function calling
# ---------------------------------------------------------------------------

TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "search_case",
            "description": "Search CasePeer for a case by patient name. Use this only if the pre-loaded context does not include a case_id.",
            "parameters": {
                "type": "object",
                "properties": {
                    "patient_name": {
                        "type": "string",
                        "description": "The patient's name to search for"
                    }
                },
                "required": ["patient_name"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_settlement_page",
            "description": "Fetch the settlement/negotiations HTML page for a case. Returns provider IDs, names, actual bills, and offered amounts.",
            "parameters": {
                "type": "object",
                "properties": {
                    "case_id": {
                        "type": "string",
                        "description": "The CasePeer case ID"
                    }
                },
                "required": ["case_id"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "accept_lien",
            "description": "Mark a health lien as accepted in CasePeer and update the final cost to the offered amount.",
            "parameters": {
                "type": "object",
                "properties": {
                    "case_id": {
                        "type": "string",
                        "description": "The CasePeer case ID"
                    },
                    "provider_id": {
                        "type": "string",
                        "description": "The health lien provider ID from the settlement page"
                    },
                    "offered_amount": {
                        "type": "string",
                        "description": "The agreed settlement dollar amount (e.g. '450.00')"
                    }
                },
                "required": ["case_id", "provider_id", "offered_amount"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "add_case_note",
            "description": "Add a note to a case in CasePeer for record-keeping.",
            "parameters": {
                "type": "object",
                "properties": {
                    "case_id": {
                        "type": "string",
                        "description": "The CasePeer case ID"
                    },
                    "note": {
                        "type": "string",
                        "description": "The note text to add"
                    }
                },
                "required": ["case_id", "note"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_case_status",
            "description": "Get the current case status (e.g. 'Lien Negotiations', 'Disbursement') from CasePeer.",
            "parameters": {
                "type": "object",
                "properties": {
                    "case_id": {
                        "type": "string",
                        "description": "The CasePeer case ID"
                    }
                },
                "required": ["case_id"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "log_negotiation",
            "description": "Log a negotiation event (email sent/received, offer, acceptance, etc.) to the database.",
            "parameters": {
                "type": "object",
                "properties": {
                    "case_id": {
                        "type": "string",
                        "description": "The CasePeer case ID"
                    },
                    "negotiation_type": {
                        "type": "string",
                        "description": "Type: 'Accepted', 'Rejected', 'Counter-offer', 'Payment Inquiry', 'Bill Correction', 'Bill Confirmation', 'Clarification', 'Escalation'"
                    },
                    "email_body": {
                        "type": "string",
                        "description": "Summary of the email content"
                    },
                    "to": {
                        "type": "string",
                        "description": "Provider email address"
                    },
                    "actual_bill": {
                        "type": "number",
                        "description": "The original bill amount"
                    },
                    "offered_bill": {
                        "type": "number",
                        "description": "The amount offered/accepted"
                    },
                    "result": {
                        "type": "string",
                        "description": "Result of this negotiation step"
                    },
                    "sent_by_us": {
                        "type": "boolean",
                        "description": "True if this logs OUR reply/action, False if logging the provider's incoming message. Default: false (provider message)."
                    }
                },
                "required": ["case_id", "negotiation_type", "email_body"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "generate_and_upload_pdf",
            "description": "Generate a PDF document from the email trail and upload it to CasePeer as a case document. Use this to create acceptance letters, bill correction records, bill confirmation records, or any negotiation documentation.",
            "parameters": {
                "type": "object",
                "properties": {
                    "case_id": {
                        "type": "string",
                        "description": "The CasePeer case ID to upload the document to"
                    },
                    "document_title": {
                        "type": "string",
                        "description": "Title for the PDF document (e.g. 'Acceptance Of Dr. Smith', 'Bill Correction from Metro Hospital For John Doe')"
                    },
                    "document_type": {
                        "type": "string",
                        "enum": ["acceptance", "bill_correction", "bill_confirmation", "email_trail", "other"],
                        "description": "Type of document being created"
                    },
                    "content_sections": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "heading": {"type": "string", "description": "Section heading"},
                                "body": {"type": "string", "description": "Section body text"}
                            },
                            "required": ["heading", "body"]
                        },
                        "description": "Sections of content to include in the PDF. For email trails, each section is one email (heading=sender, body=email text). For acceptance letters, include case details, agreed amount, etc."
                    },
                    "metadata": {
                        "type": "object",
                        "properties": {
                            "provider_name": {"type": "string"},
                            "patient_name": {"type": "string"},
                            "amount": {"type": "string"},
                            "date": {"type": "string"}
                        },
                        "description": "Optional metadata to display in the document header"
                    }
                },
                "required": ["case_id", "document_title", "document_type", "content_sections"]
            }
        }
    }
]

# ---------------------------------------------------------------------------
# Tool implementation functions — these call your existing CasePeer proxy
# ---------------------------------------------------------------------------

def _get_local_base() -> str:
    """Get the local proxy URL, respecting Render's PORT env var."""
    import os
    port = os.getenv("PORT", "8000")
    return f"http://localhost:{port}"


def _casepeer_get(endpoint: str) -> Dict[str, Any]:
    """Make a GET request through the CasePeer proxy (internal)."""
    import requests as req
    base = _get_local_base()

    # Use the local proxy to leverage existing auth session
    # Timeout 90s to allow for CasePeer re-authentication if session expired
    try:
        resp = req.get(f"{base}/{endpoint.lstrip('/')}", timeout=90)
        resp.raise_for_status()
        return resp.json()
    except Exception as e:
        logger.error(f"CasePeer GET {endpoint} failed: {e}")
        return {"error": str(e)}


def _casepeer_post(endpoint: str, data: Dict = None, content_type: str = "application/json") -> Dict[str, Any]:
    """Make a POST request through the CasePeer proxy (internal)."""
    import requests as req
    base = _get_local_base()
    try:
        if content_type == "multipart/form-data":
            resp = req.post(
                f"{base}/{endpoint.lstrip('/')}",
                data=data,
                timeout=90
            )
        else:
            resp = req.post(
                f"{base}/{endpoint.lstrip('/')}",
                json=data,
                timeout=90
            )
        resp.raise_for_status()
        return resp.json()
    except Exception as e:
        logger.error(f"CasePeer POST {endpoint} failed: {e}")
        return {"error": str(e)}


def _lookup_negotiation_history(provider_email: str) -> str:
    """Look up existing negotiation history by provider email, grouped by case_id.

    A provider can have multiple clients/cases, so we group history per case
    and return all of them so the agent can match the right one.
    """
    from turso_client import turso
    try:
        rows = turso.fetch_all(
            'SELECT case_id, negotiation_type, email_body, actual_bill, offered_bill, result, date, sent_by_us FROM negotiations WHERE "to" = ? ORDER BY date DESC LIMIT 30',
            [provider_email]
        )

        if not rows:
            return json.dumps({"found": False, "message": f"No negotiation history for {provider_email}"})

        # Group negotiations by case_id (provider may have multiple clients)
        cases = {}
        for r in rows:
            cid = str(r.get("case_id", ""))
            if cid not in cases:
                cases[cid] = {
                    "case_id": cid,
                    "latest_actual_bill": r.get("actual_bill"),
                    "latest_offered_bill": r.get("offered_bill"),
                    "history": []
                }
            cases[cid]["history"].append({
                "type": r.get("negotiation_type", ""),
                "summary": (r.get("email_body", "") or "")[:200],
                "actual_bill": r.get("actual_bill"),
                "offered_bill": r.get("offered_bill"),
                "result": r.get("result", ""),
                "date": r.get("date", ""),
                "sent_by_us": bool(r.get("sent_by_us", 0))
            })

        cases_list = list(cases.values())

        # If only one case, return it directly
        if len(cases_list) == 1:
            c = cases_list[0]
            return json.dumps({
                "found": True,
                "multiple_cases": False,
                "case_id": c["case_id"],
                "provider_email": provider_email,
                "latest_actual_bill": c["latest_actual_bill"],
                "latest_offered_bill": c["latest_offered_bill"],
                "negotiation_count": len(c["history"]),
                "history": c["history"]
            })

        # Multiple cases — return all so agent can match by patient name in email
        return json.dumps({
            "found": True,
            "multiple_cases": True,
            "provider_email": provider_email,
            "case_count": len(cases_list),
            "cases": cases_list
        })

    except Exception as e:
        logger.error(f"lookup_negotiation failed: {e}")
        return json.dumps({"error": str(e)})


def tool_search_case(patient_name: str) -> str:
    """Search CasePeer for a case by patient name."""
    result = _casepeer_get(f"api/v1/case/case-search/?search={patient_name}")
    if isinstance(result, dict) and "error" in result:
        return json.dumps({"error": result["error"]})

    # The API returns the case data — extract ID
    if isinstance(result, dict) and "id" in result:
        return json.dumps({"case_id": str(result["id"]), "patient_name": result.get("patient_name", patient_name)})
    elif isinstance(result, list) and len(result) > 0:
        case = result[0]
        return json.dumps({"case_id": str(case.get("id", "")), "patient_name": case.get("patient_name", patient_name)})

    return json.dumps(result)


def tool_get_settlement_page(case_id: str) -> str:
    """Fetch and parse the settlement/negotiations page for a case."""
    result = _casepeer_get(f"case/{case_id}/settlement/negotiations/")

    html = result.get("response", "") if isinstance(result, dict) else ""
    if not html:
        return json.dumps({"error": "No HTML returned from settlement page"})

    # Parse with BeautifulSoup instead of AI — faster, free, reliable
    soup = BeautifulSoup(html, "html.parser")
    providers = []

    # Extract provider rows from the settlement table
    rows = soup.select("tr")
    for row in rows:
        cells = row.select("td")
        if len(cells) >= 3:
            name_cell = row.select_one(".nopad.bottom.wordbreak")
            if name_cell:
                provider_name = name_cell.get_text(strip=True)
                # Try to extract the provider ID from links or hidden inputs
                link = row.select_one("a[href*='accept-unaccept']")
                provider_id = ""
                if link:
                    href = link.get("href", "")
                    id_match = re.search(r'/(\d+)/?$', href)
                    if id_match:
                        provider_id = id_match.group(1)

                # Try to get amounts from the row
                amounts = re.findall(r'\$[\d,]+\.?\d*', row.get_text())
                providers.append({
                    "provider_name": provider_name,
                    "provider_id": provider_id,
                    "amounts": amounts
                })

    # Also extract form fields for lien update
    form_data = {}
    for inp in soup.select("input[name]"):
        name = inp.get("name", "")
        value = inp.get("value", "")
        if name.startswith("health-liens") or name == "csrfmiddlewaretoken":
            form_data[name] = value

    return json.dumps({
        "providers": providers,
        "form_fields": form_data,
        "raw_length": len(html)
    })


def tool_accept_lien(case_id: str, provider_id: str, offered_amount: str) -> str:
    """Accept a lien: update the final cost and mark as accepted."""
    # Step 1: Get current form fields
    settlement_data = json.loads(tool_get_settlement_page(case_id))
    form_fields = settlement_data.get("form_fields", {})

    if not form_fields:
        return json.dumps({"error": "Could not retrieve settlement form fields"})

    # Step 2: Find the matching lien and update its final_cost
    clean_amount = re.sub(r'[^0-9.]', '', offered_amount)
    updated = False
    for key, value in form_fields.items():
        if key.endswith("-id") and value == provider_id:
            index = re.search(r'health-liens-(\d+)-id', key)
            if index:
                cost_key = f"health-liens-{index.group(1)}-final_cost"
                form_fields[cost_key] = clean_amount
                updated = True
                break

    if not updated:
        return json.dumps({"error": f"Provider ID {provider_id} not found in settlement form"})

    # Step 3: POST the updated form
    form_body = "&".join(f"{k}={v}" for k, v in form_fields.items())
    import requests as req
    base = _get_local_base()
    try:
        resp = req.post(
            f"{base}/case/{case_id}/settlement/negotiations/",
            data=form_body,
            headers={"Content-Type": "application/x-www-form-urlencoded"},
            timeout=90
        )
        # Step 4: Toggle the accept flag
        resp2 = req.get(
            f"{base}/case/{case_id}/settlement/accept-unaccept-health-lien/{provider_id}/",
            timeout=90
        )
        return json.dumps({"success": True, "provider_id": provider_id, "amount": clean_amount})
    except Exception as e:
        return json.dumps({"error": str(e)})


def tool_add_case_note(case_id: str, note: str) -> str:
    """Add a note to a CasePeer case."""
    import requests as req
    base = _get_local_base()
    try:
        resp = req.post(
            f"{base}/case/{case_id}/notes/add-case-note/",
            data={"note": note, "time_worked": ""},
            timeout=90
        )
        return json.dumps({"success": True})
    except Exception as e:
        return json.dumps({"error": str(e)})


def tool_get_case_status(case_id: str) -> str:
    """Get the case status from CasePeer."""
    result = _casepeer_get(f"case/{case_id}/")
    html = result.get("response", "") if isinstance(result, dict) else ""
    if not html:
        return json.dumps({"case_status": "Unknown"})

    soup = BeautifulSoup(html, "html.parser")

    # Extract patient name from title
    title_tag = soup.select_one("title")
    patient_name = "Unknown"
    if title_tag:
        match = re.match(r'(.*?)\s*-\s*Home', title_tag.get_text())
        if match:
            patient_name = match.group(1).strip()

    # Extract case status from select
    select = soup.select_one('select[name="casestatus"]')
    case_status = "Unknown"
    if select:
        selected = select.select_one("option[selected]")
        if selected:
            case_status = selected.get_text(strip=True)

    return json.dumps({"case_status": case_status, "patient_name": patient_name})


def tool_log_negotiation(case_id: str, negotiation_type: str, email_body: str,
                         to: str = "", actual_bill: float = 0, offered_bill: float = 0,
                         result: str = "", sent_by_us: bool = False) -> str:
    """Log a negotiation event to the Turso database."""
    from turso_client import turso
    try:
        turso.execute(
            "INSERT INTO negotiations (case_id, negotiation_type, \"to\", email_body, date, actual_bill, offered_bill, sent_by_us, result) VALUES (?, ?, ?, ?, datetime('now'), ?, ?, ?, ?)",
            [case_id, negotiation_type, to, email_body, actual_bill, offered_bill, 1 if sent_by_us else 0, result]
        )
        return json.dumps({"success": True})
    except Exception as e:
        return json.dumps({"error": str(e)})


def tool_generate_and_upload_pdf(case_id: str, document_title: str, document_type: str,
                                  content_sections: List[Dict], metadata: Dict = None) -> str:
    """Generate a PDF from content sections and upload it to CasePeer."""
    import requests as req
    from datetime import datetime

    try:
        # --- Generate PDF ---
        pdf = FPDF()
        pdf.set_auto_page_break(auto=True, margin=20)
        pdf.add_page()

        # Header: Beverly Law letterhead
        pdf.set_font("Helvetica", "B", 16)
        pdf.cell(0, 10, "Beverly Law", new_x="LMARGIN", new_y="NEXT", align="C")
        pdf.set_font("Helvetica", "", 10)
        pdf.cell(0, 6, "Lien Negotiations Department", new_x="LMARGIN", new_y="NEXT", align="C")
        pdf.ln(4)

        # Document type label
        type_labels = {
            "acceptance": "Settlement Acceptance Record",
            "bill_correction": "Bill Correction Record",
            "bill_confirmation": "Bill Confirmation Record",
            "email_trail": "Email Correspondence Record",
            "other": "Negotiation Record",
        }
        pdf.set_font("Helvetica", "B", 13)
        pdf.cell(0, 10, type_labels.get(document_type, "Negotiation Record"), new_x="LMARGIN", new_y="NEXT", align="C")
        pdf.ln(2)

        # Metadata block (if provided)
        if metadata:
            pdf.set_font("Helvetica", "", 10)
            pdf.set_fill_color(240, 240, 240)
            meta_lines = []
            if metadata.get("provider_name"):
                meta_lines.append(f"Provider: {metadata['provider_name']}")
            if metadata.get("patient_name"):
                meta_lines.append(f"Patient: {metadata['patient_name']}")
            if metadata.get("amount"):
                meta_lines.append(f"Amount: {metadata['amount']}")
            meta_lines.append(f"Date: {metadata.get('date', datetime.now().strftime('%Y-%m-%d'))}")

            for line in meta_lines:
                pdf.cell(0, 6, line, new_x="LMARGIN", new_y="NEXT", fill=True)
            pdf.ln(4)

        # Divider
        pdf.set_draw_color(100, 100, 100)
        pdf.line(10, pdf.get_y(), 200, pdf.get_y())
        pdf.ln(6)

        # Content sections
        for section in content_sections:
            heading = section.get("heading", "")
            body = section.get("body", "")

            # Section heading
            pdf.set_font("Helvetica", "B", 11)
            # Sanitize heading text for fpdf (replace unsupported chars)
            safe_heading = heading.encode("latin-1", errors="replace").decode("latin-1")
            pdf.cell(0, 7, safe_heading, new_x="LMARGIN", new_y="NEXT")

            # Section body
            pdf.set_font("Helvetica", "", 10)
            # Sanitize body text
            safe_body = body.encode("latin-1", errors="replace").decode("latin-1")
            pdf.multi_cell(0, 5, safe_body)
            pdf.ln(3)

            # Light divider between sections
            pdf.set_draw_color(200, 200, 200)
            pdf.line(10, pdf.get_y(), 200, pdf.get_y())
            pdf.ln(4)

        # Footer
        pdf.ln(6)
        pdf.set_font("Helvetica", "I", 9)
        pdf.cell(0, 5, f"Generated on {datetime.now().strftime('%Y-%m-%d %H:%M')} by Beverly Law Lien Negotiations", new_x="LMARGIN", new_y="NEXT", align="C")

        # --- Output PDF to bytes ---
        pdf_bytes = pdf.output()

        # --- Upload to CasePeer ---
        filename = f"{document_title}.pdf"
        files = {"file": (filename, pdf_bytes, "application/pdf")}
        data = {"docname": filename}

        base = _get_local_base()
        resp = req.post(
            f"{base}/internal-api/proxy_upload_file/{case_id}",
            files=files,
            data=data,
            timeout=60
        )

        if resp.status_code == 200:
            logger.info(f"[PDF] Uploaded '{filename}' to case {case_id}")
            return json.dumps({"success": True, "filename": filename, "size_bytes": len(pdf_bytes)})
        else:
            logger.error(f"[PDF] Upload failed: {resp.status_code} - {resp.text[:200]}")
            return json.dumps({"error": f"Upload failed with status {resp.status_code}", "details": resp.text[:200]})

    except Exception as e:
        logger.error(f"[PDF] Generation/upload error: {e}", exc_info=True)
        return json.dumps({"error": str(e)})


# Tool dispatcher
TOOL_FUNCTIONS = {
    "search_case": lambda args: tool_search_case(args["patient_name"]),
    "get_settlement_page": lambda args: tool_get_settlement_page(args["case_id"]),
    "accept_lien": lambda args: tool_accept_lien(args["case_id"], args["provider_id"], args["offered_amount"]),
    "add_case_note": lambda args: tool_add_case_note(args["case_id"], args["note"]),
    "get_case_status": lambda args: tool_get_case_status(args["case_id"]),
    "log_negotiation": lambda args: tool_log_negotiation(**args),
    "generate_and_upload_pdf": lambda args: tool_generate_and_upload_pdf(
        args["case_id"], args["document_title"], args["document_type"],
        args["content_sections"], args.get("metadata")
    ),
}


# ---------------------------------------------------------------------------
# Conversation history — persist full AI chat per sender for continuity
# ---------------------------------------------------------------------------

def _get_conversation_key(sender_email: str, thread_subject: str) -> str:
    """Generate a stable key for a conversation (sender + cleaned subject)."""
    clean_subj = re.sub(r'^(Re:|Fwd?:)\s*', '', thread_subject, flags=re.IGNORECASE).strip().lower()
    return f"{sender_email.lower()}|{clean_subj}"


def _load_conversation_history(sender_email: str, thread_subject: str) -> Optional[List[Dict]]:
    """Load previous AI conversation for this sender+thread from Turso."""
    from turso_client import turso
    try:
        key = _get_conversation_key(sender_email, thread_subject)
        row = turso.fetch_one(
            "SELECT messages_json, tools_used FROM conversation_history WHERE id = ?",
            [key]
        )
        if row and row.get("messages_json"):
            return json.loads(row["messages_json"])
    except Exception as e:
        logger.warning(f"[Agent] Failed to load conversation history: {e}")
    return None


def _save_conversation_history(sender_email: str, thread_subject: str,
                                messages: List[Dict], tools_used: List[str],
                                intent: str, case_id: str = ""):
    """Save the full AI conversation to Turso for next time."""
    from turso_client import turso
    try:
        key = _get_conversation_key(sender_email, thread_subject)
        # Only save serializable messages (strip tool_calls objects)
        safe_messages = []
        for msg in messages:
            if hasattr(msg, 'model_dump'):
                safe_messages.append(msg.model_dump())
            elif isinstance(msg, dict):
                safe_messages.append(msg)

        turso.execute(
            "INSERT OR REPLACE INTO conversation_history (id, case_id, sender_email, thread_subject, messages_json, tools_used, last_intent, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?, datetime('now'))",
            [key, case_id, sender_email.lower(), thread_subject, json.dumps(safe_messages), json.dumps(tools_used), intent]
        )
        logger.info(f"[Agent] Saved conversation history for {sender_email} | {thread_subject[:30]}")
    except Exception as e:
        logger.warning(f"[Agent] Failed to save conversation history: {e}")


# ---------------------------------------------------------------------------
# Email thread parser — replaces Code1 + Code3 from n8n
# ---------------------------------------------------------------------------

def parse_email_thread(thread_data: Dict) -> str:
    """
    Parse a Gmail thread (as sent by n8n) into a readable conversation string.
    Handles base64 decoding, quoted reply removal, and sender extraction.
    """
    import base64

    messages = thread_data.get("messages", [])
    if not messages:
        return "No messages in thread."

    conversation_parts = []

    for msg in messages:
        # Extract sender
        from_field = msg.get("From", "")
        headers = msg.get("payload", {}).get("headers", [])
        if not from_field:
            from_header = next((h for h in headers if h.get("name", "").lower() == "from"), None)
            from_field = from_header["value"] if from_header else "Unknown"

        # Clean sender name
        name_match = re.match(r'^(.*?)<', from_field)
        sender = name_match.group(1).strip() if name_match else from_field

        # Extract body — check _decoded_body first (set by IMAP poller),
        # then try Gmail API format (base64 payload), then fall back to snippet
        body = msg.get("_decoded_body", "")

        if not body:
            payload = msg.get("payload", {})
            if payload.get("body", {}).get("data"):
                try:
                    raw = payload["body"]["data"].replace("-", "+").replace("_", "/")
                    body = base64.b64decode(raw).decode("utf-8", errors="replace")
                except Exception:
                    body = ""

            if not body and payload.get("parts"):
                for part in payload["parts"]:
                    if part.get("mimeType") == "text/plain" and part.get("body", {}).get("data"):
                        try:
                            raw = part["body"]["data"].replace("-", "+").replace("_", "/")
                            body = base64.b64decode(raw).decode("utf-8", errors="replace")
                            break
                        except Exception:
                            continue

        if not body:
            body = msg.get("snippet", "")

        # Clean body: remove quoted replies and excessive whitespace
        # Use non-greedy match and only strip from "On ... wrote:" to end
        body = re.sub(r'\nOn [^\n]+wrote:\s*\n.*', '', body, flags=re.DOTALL)
        # Remove quoted lines (lines starting with >)
        body = re.sub(r'^>.*$', '', body, flags=re.MULTILINE)
        body = re.sub(r'\s+', ' ', body).strip()

        conversation_parts.append(f"{sender}: {body}")

    return "\n---\n".join(conversation_parts)


# ---------------------------------------------------------------------------
# Main agent runner
# ---------------------------------------------------------------------------

async def process_negotiation_email(thread_data: Dict) -> Dict[str, Any]:
    """
    Main entry point. Receives a Gmail thread from n8n, runs the single agent,
    and returns the action + reply message.

    Args:
        thread_data: The full Gmail thread JSON as forwarded by n8n

    Returns:
        {
            "intent": "accepted|rejected|...",
            "reply_message": "HTML email body to send (or null if no reply)",
            "actions_taken": ["list of actions performed"],
            "provider_name": "...",
            "patient_name": "...",
            "reasoning": "..."
        }
    """
    from turso_client import get_setting, log_token_usage

    # Get OpenAI API key
    api_key = get_setting("openai_api_key")
    if not api_key:
        api_key = __import__("os").getenv("OPENAI_API_KEY")
    if not api_key:
        return {"error": "OpenAI API key not configured. Set it in Settings or OPENAI_API_KEY env var."}

    client = OpenAI(api_key=api_key)

    # Parse the email thread into readable text
    conversation_text = parse_email_thread(thread_data)

    # Extract metadata for context
    messages = thread_data.get("messages", [])
    first_msg = messages[0] if messages else {}
    last_msg = messages[-1] if messages else {}

    thread_id = first_msg.get("threadId", "")
    last_message_id = last_msg.get("id", "")
    sender_email = last_msg.get("From", "")

    # Clean sender email (extract from "Name <email>" format)
    email_match = re.search(r'<(.+?)>', sender_email)
    clean_sender = email_match.group(1) if email_match else sender_email.strip()

    # --- PRE-LOAD PROVIDER CONTEXT from database ---
    # This gives the agent full history without needing to call tools first
    provider_context = ""
    pre_loaded_case_id = ""
    try:
        negotiation_history = _lookup_negotiation_history(clean_sender)
        history_data = json.loads(negotiation_history)

        if history_data.get("found"):
            if history_data.get("multiple_cases"):
                # Provider has multiple clients — present each case separately
                provider_context = f"""
KNOWN PROVIDER CONTEXT (this provider has {history_data['case_count']} active cases with Beverly Law):
- Provider Email: {history_data['provider_email']}
- IMPORTANT: Match the patient name in the email to the correct case below.
"""
                for case_data in history_data.get("cases", []):
                    cid = case_data["case_id"]
                    provider_context += f"\n--- CASE {cid} ---\n"
                    provider_context += f"  Latest Actual Bill: ${case_data.get('latest_actual_bill', 'N/A')}\n"
                    provider_context += f"  Latest Offered Amount: ${case_data.get('latest_offered_bill', 'N/A')}\n"
                    provider_context += f"  Negotiations: {len(case_data.get('history', []))}\n"
                    for h in case_data.get("history", []):
                        direction = "WE SENT" if h.get("sent_by_us") else "PROVIDER SENT"
                        provider_context += f"    [{h.get('date', '?')}] {direction} | Type: {h.get('type', '?')} | Bill: ${h.get('actual_bill', '?')} | Offer: ${h.get('offered_bill', '?')} | Result: {h.get('result', '')} | {h.get('summary', '')}\n"

                provider_context += "\nMatch the patient name from the email to the correct case above. Use ONLY that case_id for all tool calls."
                logger.info(f"[Agent] Pre-loaded multi-case context for {clean_sender}: {history_data['case_count']} cases")
            else:
                # Single case — straightforward
                pre_loaded_case_id = history_data.get("case_id", "")
                provider_context = f"""
KNOWN PROVIDER CONTEXT (from database — this provider has prior negotiations):
- Case ID: {history_data['case_id']}
- Provider Email: {history_data['provider_email']}
- Latest Actual Bill: ${history_data.get('latest_actual_bill', 'N/A')}
- Latest Offered Amount: ${history_data.get('latest_offered_bill', 'N/A')}
- Total Negotiations on Record: {history_data.get('negotiation_count', 0)}
- Negotiation History (most recent first):
"""
                for h in history_data.get("history", []):
                    direction = "WE SENT" if h.get("sent_by_us") else "PROVIDER SENT"
                    provider_context += f"  [{h.get('date', '?')}] {direction} | Type: {h.get('type', '?')} | Bill: ${h.get('actual_bill', '?')} | Offer: ${h.get('offered_bill', '?')} | Result: {h.get('result', '')} | {h.get('summary', '')}\n"

                provider_context += f"\nYou already have the case_id={history_data['case_id']}. Do NOT call search_case. Use this case_id for all tool calls."
                logger.info(f"[Agent] Pre-loaded context for {clean_sender}: case_id={pre_loaded_case_id}, {history_data.get('negotiation_count', 0)} prior negotiations")
        else:
            provider_context = f"\nNO PRIOR NEGOTIATIONS FOUND for {clean_sender}. This may be a new provider. Call search_case with the patient name to find the case."
            logger.info(f"[Agent] No prior negotiations for {clean_sender}")

    except Exception as e:
        logger.warning(f"[Agent] Failed to pre-load provider context: {e}")
        provider_context = "\nCould not pre-load provider context. Use search_case with the patient name to find the case."

    # --- LOAD PREVIOUS CONVERSATION HISTORY ---
    thread_subject = last_msg.get("Subject", "")
    prev_conversation = _load_conversation_history(clean_sender, thread_subject)
    prior_context_note = ""
    if prev_conversation:
        prior_context_note = f"\n\nPREVIOUS CONVERSATION HISTORY:\nYou have already interacted with this provider in a prior session. Below is a summary of your previous tool calls and decisions. Use this to maintain continuity — do NOT repeat actions you already performed (e.g. don't re-log the same negotiation, don't re-upload the same PDF).\n"
        # Extract previous actions summary from the saved messages
        for prev_msg in prev_conversation:
            if isinstance(prev_msg, dict):
                role = prev_msg.get("role", "")
                if role == "assistant" and prev_msg.get("content"):
                    prior_context_note += f"[YOUR PREVIOUS RESPONSE]: {prev_msg['content'][:500]}\n"
                elif role == "tool":
                    prior_context_note += f"[PREVIOUS TOOL RESULT]: {prev_msg.get('content', '')[:200]}\n"
        logger.info(f"[Agent] Loaded previous conversation history for {clean_sender} | {thread_subject[:30]}")

    user_message = f"""Analyze the following email thread and determine the appropriate action.

EMAIL THREAD (chronological, oldest to newest):
{conversation_text}
{provider_context}
{prior_context_note}

METADATA:
- Thread ID: {thread_id}
- Last message from: {sender_email} ({clean_sender})
- Total messages in thread: {len(messages)}
{f'- Known Case ID: {pre_loaded_case_id}' if pre_loaded_case_id else '- Case ID: unknown — use search_case to find it'}

INSTRUCTIONS:
1. Classify the provider's MOST RECENT message intent.
2. You already have the case_id and full negotiation history pre-loaded above. Use them directly
   — do NOT call search_case unless no case_id was provided.
3. Use tools to update records (log_negotiation, add_case_note, etc.).
   - When logging with log_negotiation, set sent_by_us=true when logging YOUR reply/action, and sent_by_us=false when logging the provider's incoming message.
4. Compose a reply email if one is needed.
5. Return your final decision as a JSON object with these fields:
   - intent: the classification
   - reply_message: the HTML email to send back (or null if no reply needed)
   - provider_name: extracted from the conversation
   - patient_name: extracted from the conversation
   - reasoning: brief explanation of your decision
   - actions_taken: list of what you did

IMPORTANT: After using tools and gathering information, you MUST return a final text response containing the JSON object. Do not end on a tool call."""

    # Run the agent loop
    agent_messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": user_message}
    ]

    actions_taken = []
    discovered_case_id = pre_loaded_case_id  # may be updated by tool calls
    max_iterations = 10
    total_tokens = 0

    for iteration in range(max_iterations):
        try:
            response = await asyncio.to_thread(
                client.chat.completions.create,
                model="gpt-4.1",
                messages=agent_messages,
                tools=TOOLS,
                tool_choice="auto",
                temperature=0.2
            )
        except Exception as e:
            logger.error(f"OpenAI API call failed: {e}")
            return {"error": f"OpenAI API call failed: {e}"}

        choice = response.choices[0]
        message = choice.message
        total_tokens += response.usage.total_tokens if response.usage else 0

        # If the model wants to call tools
        if message.tool_calls:
            agent_messages.append(message)

            for tool_call in message.tool_calls:
                fn_name = tool_call.function.name
                fn_args = json.loads(tool_call.function.arguments)
                logger.info(f"[Agent] Tool call: {fn_name}({fn_args})")

                # Track case_id from any tool that uses it
                if not discovered_case_id and fn_args.get("case_id"):
                    discovered_case_id = fn_args["case_id"]

                # Execute the tool
                if fn_name in TOOL_FUNCTIONS:
                    try:
                        result = await asyncio.to_thread(TOOL_FUNCTIONS[fn_name], fn_args)
                    except Exception as e:
                        result = json.dumps({"error": str(e)})
                else:
                    result = json.dumps({"error": f"Unknown tool: {fn_name}"})

                # If search_case returned a case_id, capture it
                if fn_name == "search_case" and not discovered_case_id:
                    try:
                        sr = json.loads(result)
                        if sr.get("case_id"):
                            discovered_case_id = sr["case_id"]
                    except Exception:
                        pass

                actions_taken.append(f"{fn_name}({json.dumps(fn_args)})")
                logger.info(f"[Agent] Tool result: {result[:200]}...")

                agent_messages.append({
                    "role": "tool",
                    "tool_call_id": tool_call.id,
                    "content": result
                })

            continue  # Let the model process tool results

        # Model returned a final text response
        raw_text = message.content or ""
        logger.info(f"[Agent] Final response (iteration {iteration}): {raw_text[:300]}...")

        # Log token usage
        cost = (total_tokens / 1000) * 0.002  # Approximate cost
        log_token_usage(total_tokens, cost, "gpt-4.1")

        # Parse the JSON from the response
        result = _parse_agent_response(raw_text)
        result["actions_taken"] = actions_taken
        result["tokens_used"] = total_tokens
        result["thread_id"] = thread_id
        result["last_message_id"] = last_message_id

        # Save conversation history for future continuity
        _save_conversation_history(
            clean_sender, thread_subject,
            agent_messages, actions_taken,
            result.get("intent", "unclear"),
            case_id=discovered_case_id
        )

        return result

    # If we hit max iterations
    logger.warning(f"[Agent] Hit max iterations ({max_iterations})")
    return {
        "intent": "unclear",
        "reply_message": None,
        "reasoning": "Agent reached maximum iterations without producing a final response.",
        "actions_taken": actions_taken,
        "tokens_used": total_tokens,
        "thread_id": thread_id,
        "last_message_id": last_message_id,
    }


def _parse_agent_response(text: str) -> Dict[str, Any]:
    """Extract the JSON decision from the agent's final text response."""
    # Try to find JSON in the response
    json_match = re.search(r'\{[\s\S]*\}', text)
    if json_match:
        try:
            parsed = json.loads(json_match.group())
            return {
                "intent": parsed.get("intent", "unclear"),
                "reply_message": parsed.get("reply_message"),
                "provider_name": parsed.get("provider_name", "Unknown"),
                "patient_name": parsed.get("patient_name", "Unknown"),
                "reasoning": parsed.get("reasoning", ""),
            }
        except json.JSONDecodeError:
            pass

    # Fallback: return the raw text as reasoning
    return {
        "intent": "unclear",
        "reply_message": None,
        "provider_name": "Unknown",
        "patient_name": "Unknown",
        "reasoning": text[:500],
    }
