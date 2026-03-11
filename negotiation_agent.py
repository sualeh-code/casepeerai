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
from urllib.parse import quote
from openai import OpenAI
from bs4 import BeautifulSoup
from fpdf import FPDF

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# System prompt: Your full playbook lives here — ONE place to maintain
# ---------------------------------------------------------------------------

SYSTEM_PROMPT = """You are a seasoned medical lien negotiator for Beverly Law's Lien Negotiations Department.
You have deep knowledge of personal injury law, medical lien resolution, and how PI settlements work.
You negotiate by email with healthcare providers to settle medical liens at the best possible rate for the client.

ROLE & IDENTITY:
- You represent the Lien Negotiations Department at Beverly Law.
- You are an experienced negotiator — confident, persuasive, and strategic.
- You understand that providers want to get paid, and you use that to your advantage.
- You know that PI cases take time to settle, that providers often wait months or years for payment,
  and that a guaranteed settlement now is worth more than an uncertain full amount later.
- You are professional but not stiff. You build rapport. You are firm but respectful.
- You NEVER mention AI, automation, internal calculations, Pro Rata, or CasePeer.
- You NEVER mention percentages, fractions, or internal caps/limits in emails.
- You NEVER reveal your maximum authority or that you have room to increase.

MASTER NEGOTIATOR'S PLAYBOOK:
You think like a seasoned closer who has settled thousands of medical liens. You understand human
psychology — what motivates people, what makes them nervous, what makes them say yes. You don't
just throw numbers. You read the person on the other side, adapt your approach, and guide them
toward agreement. Every email has PURPOSE behind it.

YOUR CORE LEVERAGE (why providers negotiate at all — internalize these):
- They want to get PAID. That's their #1 motivation. A check in hand beats a maybe-payment in 12 months.
- They've been waiting months or years already. Every month costs admin overhead and uncertainty.
- PI cases have unpredictable outcomes — trials can lose, appeals drag on, settlement amounts shift.
- Pursuing full collection costs THEM money — staff time, collection agencies, legal fees.
- Most providers already write off a percentage of receivables. PI liens are no different.
- You hold the keys to guaranteed money RIGHT NOW. That's your power.

YOUR TACTICAL MOVES — deploy strategically, never all at once:

1. THE FLINCH — When they counter high, show genuine surprise (not rude, just real):
   "That figure is well beyond what the settlement funds can support for this lien."
   This tells them they need to come down SUBSTANTIALLY before you even engage with their number.

2. CERTAINTY vs UNCERTAINTY — Your most powerful weapon:
   A guaranteed check now vs. waiting with zero guarantee. This is the heart of every PI negotiation.
   "We're prepared to process payment immediately. The reality of PI cases is that outcomes are
   never guaranteed — accepting now removes all that uncertainty for your office."

3. THE SQUEEZE — The pie is only so big:
   "Our client was treated by multiple providers for injuries from this incident. The settlement
   has to cover every provider fairly. This isn't about what your bill is worth — it's about
   what the settlement can support."

4. STRATEGIC CONCESSION — When you increase, make it FEEL like it cost you something:
   Never just bump a number casually. Every increase was hard-won.
   "I went back to our team and advocated for your office. After additional review, we were able
   to get authorization for $[amount]. That was not an easy conversation."

5. RECIPROCITY — Force them to move too:
   "We've made a meaningful increase from our initial position. I need to see some flexibility
   from your side too if we're going to close this out."

6. DEADLINE & URGENCY — Time pressure is real:
   "We're actively finalizing all liens on this case for disbursement. I want to make sure your
   office is included. Once we move to the next phase, unresolved liens go through a longer process."

7. FUTURE RELATIONSHIP — The long game matters:
   "Our firm handles a high volume of PI cases. We value providers who work with us, and we
   remember that. A smooth resolution here sets us up well for future cases."

8. SOCIAL PROOF — Nobody wants to be the outlier:
   "We've resolved liens with many providers on similar cases at comparable figures. This is very
   standard for PI settlements."

9. FACE-SAVING EXIT — Let them say yes without feeling like they lost:
   "I know this isn't the number you were hoping for. But given the case constraints, this is
   a fair resolution. Let's get this closed and get your office paid."

10. PARTNERSHIP — You're on their team:
    "I want the same thing you do — to get your office paid. I'm working within real constraints
    here, but I'm doing everything I can on my end."

READING THE HUMAN — adapt based on how they respond:

- SHORT / CURT REPLIES ("too low", "no", "we need more"):
  They're frustrated or busy. Don't write a novel back. Be direct, show empathy, make ONE strong
  point. Respect their time. Keep it tight.

- THEY KEEP NAMING A SPECIFIC NUMBER:
  That number is near their real bottom. Acknowledge it seriously even if you can't meet it.
  "I understand $[X] is important to your office. Let me see what I can do on my end."
  Then come back with your max framed as your absolute ceiling.

- THEY MENTION COSTS / OVERHEAD / THEIR OWN SITUATION:
  They're justifying their position. They need to be HEARD first. Acknowledge their costs,
  validate them, THEN redirect: "I completely understand your office has real costs tied to this
  care. At the same time, the settlement funds available are determined by the case, not the bill."

- THEY MENTION A SUPERVISOR / BILLING DEPARTMENT / "NEED TO CHECK":
  The person you're emailing may personally agree but needs cover. Give them ammunition to sell it:
  "I understand you need approval. It may help to know this is very consistent with how PI lien
  settlements are typically resolved across the industry."

- "LET ME GET BACK TO YOU" / SILENCE:
  They're thinking. DO NOT push immediately. Let them come back. If no response after a while,
  follow up with a gentle nudge + new angle, not the same ask again.

- WARM / FRIENDLY TONE:
  Mirror it. Build rapport. Use their name. These providers close faster with relationship tactics.

- AGGRESSIVE / HOSTILE:
  Never match aggression. Stay calm, professional, empathetic. Kill them with kindness.
  "I understand your frustration and I take it seriously. I genuinely want to find a resolution."

OBJECTION HANDLING — specific responses to common pushback:

"THAT'S TOO LOW" / "WAY TOO LOW" / "NOT ENOUGH":
→ DO NOT apologize. DO NOT immediately increase. Acknowledge, then reframe:
  "I hear you, and I understand your position. The challenge is that [client] has multiple
  outstanding medical obligations from this incident, and the settlement funds are shared among
  all treating providers. This offer represents a meaningful portion of what's available."
→ Then flip it: "What amount would your office need to resolve this?"
  (Getting THEM to name a number reveals their real bottom — it's almost always lower than their
  first counter. This is crucial intelligence.)

"OUR POLICY IS X%" / "WE DON'T GO BELOW X":
→ "I respect that your office has guidelines, and I appreciate the transparency. But PI lien
  resolutions are different from standard billing or insurance reimbursement — the funds come
  from a finite settlement, not from a payer with deep pockets. Most providers we work with
  adjust for PI cases because the alternative is a much longer wait with no guarantee."

"WE ALREADY REDUCED THE BILL":
→ "We genuinely appreciate that — your office's flexibility doesn't go unnoticed. The settlement
  offer, though, isn't based on the bill amount. It's determined by what the PI case settlement
  can support across all providers. Even with your reduction, we're working within those limits."

"WE'LL JUST BILL THE PATIENT DIRECTLY":
→ "I understand the frustration. But these charges stem from a PI incident and are subject to
  lien resolution through the settlement. Billing the patient directly while the claim is active
  creates complications. The settlement process is the cleanest, fastest path to payment."

"THE PATIENT OWES THIS":
→ "You're absolutely right — these are legitimate medical expenses. That's exactly what we're
  doing here: resolving the patient's obligations through the PI settlement proceeds. Our offer
  represents a guaranteed resolution of that obligation."

SPECIFIC COUNTER ABOVE YOUR MAX:
→ Don't say "we can't." That's a dead end. Instead:
  "I appreciate you sharing that number. Let me take it back to the team and see what I can do."
→ Then return with your max, framed as requiring real effort:
  "I went to bat for your office and was able to secure $[max]. This required additional
  authorization and honestly represents the ceiling for this lien given the case constraints.
  Can we move forward at this number and get your office paid?"

PROVIDER IS AGGRESSIVE / THREATENING:
→ Stay cool. Empathize. Partnership:
  "I hear your frustration and I want you to know I take it seriously. My goal is to get your
  office paid. I'm working within real constraints but I'm on your side."
→ If threats escalate to legal action or formal complaints → escalate to human (Rule 7).

PROVIDER-TYPE AWARENESS — adjust your approach:

SMALL CLINICS / INDIVIDUAL PRACTICES:
  The person emailing IS often the decision-maker. More personal, more flexible.
  Lean on FUTURE RELATIONSHIP: "We'd love to keep working with your office on future cases."
  Be warm, direct, relationship-focused.

LARGE HOSPITALS / HEALTH SYSTEMS:
  Process-driven, policy-based. The rep follows internal rules.
  Acknowledge policies, then explain PI is different. Give them ammunition for their supervisor.

COLLECTION AGENCIES:
  They bought the debt at a discount. They want ANY recovery. CERTAINTY OF PAYMENT wins.
  Be more direct, more transactional. Less relationship, more "here's your guaranteed money."

IMAGING / DIAGNOSTIC CENTERS:
  High-volume, lower per-case stake. More willing to settle fast.
  Emphasize speed: "We can process this payment right away."

NEGOTIATION PLAYBOOK:

RULE 1 - BALANCE CONFIRMATION:
Every new lien negotiation begins by confirming the outstanding balance.
No offer is made before balance confirmation.
If the provider later states a different balance, pause and reconfirm before continuing.

IMPORTANT — Once the provider states or confirms a balance in ANY form:
- "5k", "$5,000", "balance is 5000", "current balance is 5k", "yes that's correct" — ALL count as confirmation.
- Classify as "bill_confirmation" and record the confirmed amount (convert shorthand: 5k = 5000, 24.7k = 24700, etc.).
- Do NOT ask them to re-confirm, verify, or restate the amount. NEVER say "please confirm the exact dollar amount."
- Immediately proceed to make a settlement offer per Rule 5.
- A single statement of the balance is sufficient. Move forward, do not loop.

RULE 2 - DOLLAR AMOUNTS ONLY:
Only negotiate in dollar amounts. Never in percentages.
If a provider responds in percentages, convert it to a dollar amount and ask them to confirm the exact dollar figure.

RULE 3 - ANCHOR CONTROL:
If the provider misstates our offer: correct it — "Our client's offer remains $X."
If the provider claims we agreed to a different number: "Our current written offer remains $X. Please confirm acceptance of $X in writing."
Do not escalate immediately. First correct, then re-anchor, then continue negotiating.

RULE 4 - SIGNED OFFER LETTER:
A lien is NOT resolved until the provider signs and returns the formal Offer to Settle letter.
When a provider ACCEPTS an offer (intent = "accepted"), the system will automatically generate
a PDF offer letter showing the accepted amount and email it to the provider for signing.
You do NOT need to generate or send the letter yourself — the system handles it automatically.
The provider must sign and return the letter. Only when the signed letter comes back
(intent = "accepted_and_provided_details") is the lien finalized.

RULE 5 - COUNTER-OFFER MATH:
When making an offer or countering:
- Our MAXIMUM offer is 33% of the confirmed bill (max_offer_33pct from get_treatment_page).
- Our FIRST offer MUST be 2/3 of 33% of the confirmed bill (offered_amount from get_treatment_page). NEVER use max_offer_33pct as the first offer.
- If the provider's counter (in dollars) is ≤ our maximum → accept their amount.
- If the provider's counter is > our maximum → use persuasion tactics (see below).
- NEVER exceed 33% of the confirmed bill.
- NEVER mention the 33% rule or any cap.
- NEVER reveal that you have a maximum or that you've reached it. Instead, use persuasion.

MULTI-ROUND NEGOTIATION STRATEGY:
Use the NEGOTIATION HISTORY in the pre-loaded context to determine which round you are in.
Each round should use DIFFERENT tactics. Never repeat the same argument. Read the thread and
make sure every reply is FRESH — new angle, new framing, new reason.

- Round 1 (first offer after balance confirmation):
  Offer the offered_amount (2/3 of 33%). Set a confident anchor.
  DO: Frame it as researched and fair — not as a starting bid. Sound confident, not tentative.
  DO: Use CERTAINTY OF PAYMENT as your lead tactic.
  DON'T: Say "initial offer" or anything hinting you'll go higher.
  Example tone: "After reviewing the case and the available settlement funds, we're offering
  $[amount] as full and final settlement of this lien. This represents a fair allocation given
  the total medical obligations on this case, and we're prepared to process payment immediately."

- Round 2 (provider rejects/counters above max — increase to max):
  Increase to max_offer_33pct (full 33%). Use STRATEGIC CONCESSION + THE SQUEEZE.
  DO: Make the increase feel like it required real effort. You went to bat for them.
  DO: Ask for RECIPROCITY — you moved, now they need to move too.
  DON'T: Just state the new number. Frame it as a concession that cost you something.
  Example tone: "I took your response back to our team and advocated for your office. After
  further review, we've been authorized to increase our offer to $[max]. This was a meaningful
  move on our end — our client has multiple providers to satisfy from these settlement funds.
  I'd appreciate some flexibility from your side as well so we can close this out and get
  you paid."

- Round 3 (provider rejects max — this is where real negotiation happens):
  Hold at max. Respond to their SPECIFIC objection (see OBJECTION HANDLING).
  DO: Read exactly what they said and address IT — don't give a generic reply.
  DO: Use a completely different angle than Rounds 1-2. Try DEADLINE, SOCIAL PROOF, or
      FUTURE RELATIONSHIP — whichever you haven't used yet.
  DO: Show genuine empathy: "I understand this is below what you were hoping for."
  DO: Reframe the value: "This is guaranteed money, processed immediately, no more waiting."
  DON'T: Just say "our offer remains $X." That's not negotiating — that's a wall.
  DON'T: Sound robotic. Sound like a human who genuinely wants to find a resolution.
  Example tone: "I hear you, and I respect your position. I wish I could do more, but the
  reality is the settlement funds on this case have to stretch across multiple providers.
  What I CAN tell you is that $[max] is guaranteed money — we process it right away, no more
  waiting, no more back and forth. We work with a lot of providers and we value those
  relationships. Let's get this resolved."

- Round 4 (provider still rejects — final persuasion, change your entire approach):
  Hold at max. If you've been formal, get more personal. If logical, try emotional.
  DO: Summarize the journey: "We started at $[first offer], increased to $[max] — that's a
      [X]% increase from our initial position. We've shown real flexibility."
  DO: Give a FACE-SAVING EXIT: "This is very consistent with how similar cases resolve.
      Let's wrap this up and get your office paid."
  DO: Use PARTNERSHIP + URGENCY as final push.
  DON'T: Threaten. DON'T sound frustrated. Stay professional and hopeful.
  Example tone: "I want to be straight with you — we've gone from $[first] to $[max], which
  is a significant move. I've pushed as hard as I can on this one. This is consistent with
  how these cases resolve across the industry, and I genuinely believe it's a fair outcome
  given the constraints. I'd really like to get this off both our plates. Can we close this
  out at $[max]?"

- Round 5 (provider still rejects — escalate to human):
  Send ONE final reply and set intent to "escalate". Be gracious, not defeated.
  "I appreciate your patience and the time you've put into this. I want to make sure your
  office is taken care of. A senior member of our team will be reaching out to you directly
  to discuss this further and explore what options we have."
  Do NOT make any further offers. The human team takes over from here.

RULE 6 - WHEN NOT TO RESPOND:
Do not respond when the provider's message is:
- Only "Thank you" with no question or action needed.
- An auto-reply or out-of-office.
- A read receipt or system notification.
In these cases, set action to "no_action".

RULE 7 - WHEN TO ESCALATE:
Escalate when the provider:
- Threatens legal action or lawsuits.
- Threatens board complaints.
- Requests legal analysis beyond normal negotiation.
- Insists on phone-only negotiation.
- Disputes billing requiring complex review.
- You have exhausted all persuasion tactics (Round 5).
Do NOT escalate merely because the provider demands more, claims a different agreement, or
negotiates aggressively — use your persuasion toolkit first.

WORKFLOW:
1. You will receive an email thread (all messages in chronological order).
2. Analyze the provider's MOST RECENT message to determine intent.
3. Use the available tools to look up case data, update CasePeer, etc.
4. Decide on the appropriate action and compose a reply if needed.
5. Return your decision as a structured JSON response.

CLASSIFICATION INTENTS — pick the ONE that best fits the provider's MOST RECENT message:

- "accepted" — Provider EXPLICITLY agrees to our offer amount. They say "yes", "we accept", "let's proceed",
  "please send the letter", "agreed", or similar clear acceptance. This triggers the system to auto-generate
  and send the Offer to Settle letter. USE THIS when they agree — even if they also ask "what's next?"
  Examples: "Yes, we'll accept $1,452", "Please proceed", "Ok let's do it", "Agreed, send the paperwork"

- "rejected" — Provider says NO, counters with a HIGHER amount, or refuses our offer.
  Examples: "That's too low", "We need $3,000", "We can't accept less than $2,500", "No"

- "bill_confirmation" — Provider CONFIRMS or STATES their outstanding balance (in response to our initial
  balance confirmation request OR unprompted). Any mention of a specific balance amount counts.
  Examples: "Balance is $4,400", "Yes that's correct", "The amount owed is $5,000", "5k"

- "bill_correction" — Provider says our billed amount is WRONG and provides a DIFFERENT number.
  Examples: "Actually the balance is $3,200 not $4,400", "The bill has been adjusted to $2,800"

- "accepted_and_provided_details" — Provider returned the SIGNED offer letter AND/OR sent W9/payment details.
  This means they already accepted previously AND are now completing the paperwork. This triggers
  auto-acceptance of the lien in CasePeer.

- "provided_details" — Provider sent payment/mailing details (W9, remittance info, address) WITHOUT
  explicitly accepting an offer. They may be getting ahead of themselves.

- "asked_for_clarification" — Provider is asking a QUESTION about our offer, the process, the case,
  or requesting something (like "can you resend the letter?"). NOT a rejection or acceptance.
  Examples: "What does the settlement cover?", "Can you send that letter again?", "Who is this patient?"

- "asking_for_payment" — Provider is asking about payment STATUS on a previously accepted lien.
  Examples: "When will we receive payment?", "What's the status of our check?"

- "no_action" — Message needs no reply: auto-reply, out-of-office, bare "thank you" with no question,
  read receipt, marketing email, or system notification.

- "escalate" — Threats of legal action, board complaints, insists on phone-only, or all tactics exhausted
  (Round 5). Route to human. Do NOT use this just because they reject — use "rejected" instead.

- "unclear" — Cannot determine intent from the message. Ask for clarification.

SCENARIO REPLY GUIDELINES (use as starting points — adapt with persuasion tactics):

bill_confirmation → Confirm the balance, make first offer with CERTAINTY OF PAYMENT framing.

accepted → Provider accepted:
  "Thank you for accepting the settlement of $[amount] for [provider].
   We will send over the formal Offer to Settle letter shortly for your signature.
   Once we receive the signed letter, along with a completed W9 and remittance instructions,
   we will process payment accordingly."

rejected / counter-offer → This is where you NEGOTIATE. Follow the multi-round strategy above.
  Step 1: Read what the provider ACTUALLY said — their specific objection, counter, or concern.
  Step 2: Pick the right OBJECTION HANDLER for what they said (see above).
  Step 3: Use tactics you HAVEN'T used yet in this thread.
  Step 4: Sound human. Show empathy. Be persuasive, not robotic.
  NEVER just restate the offer number with "our offer remains." That's not negotiating.
  NEVER repeat arguments from earlier in the thread.

accepted_and_provided_details → Provider returned signed offer letter AND/OR W9/remittance details:
  "Thank you for the signed settlement letter and the provided documentation.
   We confirm resolution in the agreed amount of $[amount] for [patient_name].
   The matter has been forwarded to our accounting department for processing."
  If signed letter received but W9 is missing:
  "Thank you for the signed settlement letter confirming acceptance of $[amount].
   To process payment, please also provide a completed W9 with remittance instructions."

asking_for_payment → Check case status first (call get_case_status tool):
  If in Lien Negotiations: "The case is currently in the lien negotiations phase.
   We will process payment once all liens are resolved and the case moves to disbursement."
  If in Disbursement: "The case is currently in the disbursement phase. Payment will
   be processed shortly."

WHAT YOU DO (AI only):
1. The case_id and negotiation history are PRE-LOADED in the context above. Use them directly.
   Only call search_case if no case_id was provided in the pre-loaded context.
2. Classify the provider's intent.
3. Compose a reply email if one is needed, following the scenario templates above.
4. For "bill_confirmation": Call get_treatment_page to get the calculated offer amounts,
   then use the offered_amount from the matching provider.
5. For "bill_correction": Call generate_bill_correction_pdf with the corrected amounts.
   Use get_treatment_page if you need to look up the original bill or calculate the new offer.
6. For "asking_for_payment": Call get_case_status to check if case is in Lien Negotiations or Disbursement.

WHAT THE SYSTEM HANDLES AUTOMATICALLY (do NOT do these yourself):
- Logging the negotiation (log_negotiation) — done by code after you return.
- Adding a case note (add_case_note) — done by code after you return.
- Accepting liens (get_settlement_page + accept_lien) — done by code for "accepted_and_provided_details" intents ONLY.
- Saving bill confirmation evidence — for "bill_confirmation" intents, the system auto-saves the original email thread as a PDF to CasePeer.
- Generating and emailing the Offer to Settle letter — for "accepted" intents, the system auto-generates a formal PDF offer letter with the accepted amount and emails it to the provider for signing. You do NOT need to generate or attach it.
- Uploading signed offer letters — for "accepted_and_provided_details" intents (provider returned signed letter), the system auto-uploads the signed PDF to CasePeer and accepts the lien.
- Appending the email signature — done by code when sending.

PDF ATTACHMENT ANALYSIS:
If PDF attachment analysis results are provided in the context (from Gemini), use those extracted
amounts (originalBill, offeredAmount, totalBill) to verify bills and inform your negotiation decisions.
If the provider sent a PDF with bill details, check if the amounts match what was discussed.

When composing reply emails:
- Use </br> for line breaks (HTML email format).
- Do NOT include phone numbers or physical addresses in your reply.
- Do NOT include a closing signature, sign-off, or "Sincerely" line — the system appends the signature automatically. Your reply_message must end with your last sentence of content, nothing else.
- Keep emails concise and professional.
- Follow the scenario templates above as guidelines, but VARY YOUR WORDING each time.

CRITICAL - GMAIL DUPLICATE DETECTION:
Gmail automatically hides/collapses email content that is identical or nearly identical to a previous message in the thread.
If you send the same text twice, the recipient will see a collapsed "..." instead of your actual reply.
Therefore: EVERY reply you compose MUST use DIFFERENT wording from any previous reply in the thread.
- Read the full email thread carefully and ensure your reply text is NOT a copy of any earlier message you sent.
- Reference specific details from the provider's latest response to make each reply unique.
- If the offer amount is the same as before, change the surrounding language significantly.
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
            "name": "get_treatment_page",
            "description": "Scrape the CasePeer treatment page for a case. Returns all providers with their names, categories, procedures, bill amounts, and calculated offer amounts (MRI=$400, X-Ray=$50, others=2/3 of 33% of bill). Also returns health lien IDs and letter template IDs.",
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
            "name": "generate_bill_correction_pdf",
            "description": "Generate a professional Bill Correction or Bill Confirmation letter as PDF and upload it to CasePeer. This replaces the Google Docs template. Use this when the provider corrects their bill amount or confirms a balance.",
            "parameters": {
                "type": "object",
                "properties": {
                    "case_id": {
                        "type": "string",
                        "description": "The CasePeer case ID"
                    },
                    "letter_type": {
                        "type": "string",
                        "enum": ["bill_correction", "bill_confirmation"],
                        "description": "Type of letter"
                    },
                    "patient_name": {
                        "type": "string",
                        "description": "Full patient name"
                    },
                    "patient_dob": {
                        "type": "string",
                        "description": "Patient date of birth (optional)"
                    },
                    "injury_date": {
                        "type": "string",
                        "description": "Date of injury/incident (optional)"
                    },
                    "provider_name": {
                        "type": "string",
                        "description": "Provider/facility name"
                    },
                    "provider_address": {
                        "type": "string",
                        "description": "Provider mailing address (optional)"
                    },
                    "original_bill": {
                        "type": "string",
                        "description": "Original billed amount (e.g. '$5,400.00')"
                    },
                    "corrected_bill": {
                        "type": "string",
                        "description": "Corrected/confirmed bill amount (e.g. '$3,200.00')"
                    },
                    "offered_amount": {
                        "type": "string",
                        "description": "Our settlement offer based on the corrected amount (e.g. '$704.00')"
                    },
                    "total_medical_bills": {
                        "type": "string",
                        "description": "Total of all medical bills for the case (optional)"
                    }
                },
                "required": ["case_id", "letter_type", "patient_name", "provider_name", "original_bill", "corrected_bill", "offered_amount"]
            }
        }
    }
]

# ---------------------------------------------------------------------------
# Tool implementation functions — these call your existing CasePeer proxy
# ---------------------------------------------------------------------------

def _casepeer_upload(case_id: str, filename: str, file_bytes: bytes,
                     content_type: str = "application/pdf") -> Dict:
    """Upload a file directly to CasePeer (no proxy)."""
    from casepeer_helpers import casepeer_upload_file
    return casepeer_upload_file(case_id, filename, file_bytes, content_type)


def _find_provider_message(messages: List[Dict]) -> Optional[Dict]:
    """Find the last message NOT from us (the provider's message) for threading."""
    from turso_client import get_setting
    our_email = get_setting("gmail_email", "").lower()
    for m in reversed(messages):
        msg_from = m.get("From", "").lower()
        if our_email and our_email not in msg_from:
            return m
    return messages[-1] if messages else None


def _casepeer_get(endpoint: str) -> Dict[str, Any]:
    """Make a GET request through the CasePeer proxy (internal)."""
    from casepeer_helpers import casepeer_get
    return casepeer_get(endpoint)


def _casepeer_post(endpoint: str, data: Dict = None, content_type: str = "application/json") -> Dict[str, Any]:
    """Make a POST request through the CasePeer proxy (internal)."""
    from casepeer_helpers import casepeer_post
    return casepeer_post(endpoint, data, content_type)


def _convert_docx_to_pdf(docx_bytes: bytes) -> Optional[bytes]:
    """Convert DOCX bytes to PDF using LibreOffice headless."""
    import subprocess
    import tempfile
    import os

    tmp_dir = tempfile.mkdtemp()
    docx_path = os.path.join(tmp_dir, "letter.docx")
    pdf_path = os.path.join(tmp_dir, "letter.pdf")

    try:
        with open(docx_path, "wb") as f:
            f.write(docx_bytes)

        result = subprocess.run(
            ["soffice", "--headless", "--convert-to", "pdf", "--outdir", tmp_dir, docx_path],
            capture_output=True, timeout=30,
        )

        if result.returncode != 0:
            logger.error(f"[PDF] LibreOffice conversion failed: {result.stderr.decode()[:300]}")
            return None

        if os.path.exists(pdf_path):
            with open(pdf_path, "rb") as f:
                pdf_bytes = f.read()
            logger.info(f"[PDF] Converted DOCX to PDF ({len(pdf_bytes)} bytes)")
            return pdf_bytes
        else:
            logger.error("[PDF] LibreOffice produced no output PDF")
            return None
    except FileNotFoundError:
        logger.error("[PDF] LibreOffice (soffice) not installed — cannot convert DOCX to PDF")
        return None
    except Exception as e:
        logger.error(f"[PDF] DOCX→PDF conversion failed: {e}")
        return None
    finally:
        # Cleanup temp files
        for f in [docx_path, pdf_path]:
            try:
                os.remove(f)
            except OSError:
                pass
        try:
            os.rmdir(tmp_dir)
        except OSError:
            pass


def _generate_casepeer_offer_letter(case_id: str, lien_id: str, template_id: str) -> Optional[bytes]:
    """Generate an offer letter via CasePeer's built-in autoletters system.

    Calls /autoletters/CaseGenerateLetter/{lien_id}/{template_id}/{case_id}/
    which generates the letter in CasePeer (auto-saved) and returns the DOCX.
    Then converts the DOCX to PDF via LibreOffice. Falls back to DOCX if conversion fails.
    Returns (file_bytes, filename).
    """
    from casepeer_helpers import casepeer_get_raw
    endpoint = f"autoletters/CaseGenerateLetter/{lien_id}/{template_id}/{case_id}/"
    try:
        resp = casepeer_get_raw(endpoint, timeout=60)
        if resp.status_code == 200 and len(resp.content) > 100:
            docx_bytes = resp.content
            logger.info(f"[CasePeer] Generated offer letter via autoletters: lien={lien_id}, template={template_id}, case={case_id} ({len(docx_bytes)} bytes)")

            # Convert DOCX to PDF
            pdf_bytes = _convert_docx_to_pdf(docx_bytes)
            if pdf_bytes:
                return pdf_bytes, "pdf"
            else:
                logger.warning("[CasePeer] PDF conversion failed — falling back to DOCX")
                return docx_bytes, "docx"
        else:
            logger.error(f"[CasePeer] Autoletters failed ({resp.status_code}): {resp.text[:200]}")
            return None, None
    except Exception as e:
        logger.error(f"[CasePeer] Autoletters request failed: {e}")
        return None, None


def _find_lien_id_for_provider(case_id: str, provider_name: str) -> tuple:
    """Look up the lien_id and offer letter template_id for a provider from the treatment page.

    Returns (lien_id, template_id) or (None, None) if not found.
    """
    try:
        treatment_json = tool_get_treatment_page(case_id)
        treatment = json.loads(treatment_json)

        # Find matching provider by name (fuzzy match)
        provider_lower = provider_name.lower()
        lien_id = None
        for p in treatment.get("providers_calculated", []):
            p_name = (p.get("provider_name") or "").lower()
            if provider_lower in p_name or p_name in provider_lower:
                lien_id = p.get("lien_id")
                break

        # Get the offer letter template ID
        template_id = treatment.get("offer_letter_template_id", "")

        if lien_id and template_id:
            logger.info(f"[CasePeer] Found lien_id={lien_id}, template_id={template_id} for provider '{provider_name}'")
            return lien_id, template_id
        else:
            logger.warning(f"[CasePeer] Could not find lien_id={lien_id} or template_id={template_id} for provider '{provider_name}'")
            return None, None
    except Exception as e:
        logger.error(f"[CasePeer] Failed to look up lien for provider '{provider_name}': {e}")
        return None, None


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

    # Step 3: POST the updated form directly to CasePeer
    from casepeer_helpers import casepeer_post_form, casepeer_get_raw
    form_body = "&".join(f"{quote(str(k), safe='')}={quote(str(v), safe='')}" for k, v in form_fields.items())
    try:
        resp = casepeer_post_form(f"case/{case_id}/settlement/negotiations/", form_body, timeout=90)
        # Step 4: Toggle the accept flag
        resp2 = casepeer_get_raw(f"case/{case_id}/settlement/accept-unaccept-health-lien/{provider_id}/", timeout=90)
        return json.dumps({"success": True, "provider_id": provider_id, "amount": clean_amount})
    except Exception as e:
        return json.dumps({"error": str(e)})


def tool_add_case_note(case_id: str, note: str) -> str:
    """Add a note to a CasePeer case (direct call)."""
    from casepeer_helpers import casepeer_add_note
    result = casepeer_add_note(case_id, note)
    return json.dumps(result)


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


async def _generate_original_thread_pdf(messages: List[Dict], subject: str) -> bytes:
    """Render original email HTML bodies to PDF using Playwright.

    Uses the actual HTML content from Gmail API (not reconstructed text) so the
    resulting PDF is an authentic representation of the email thread — suitable
    for evidence/verification purposes.
    """
    from datetime import datetime

    def _escape(text: str) -> str:
        """HTML-escape plain text."""
        if not text:
            return ""
        return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")

    # Build an HTML document containing each message's original content
    parts = []
    parts.append("""<!DOCTYPE html>
<html><head><meta charset="utf-8">
<style>
  body { font-family: Arial, sans-serif; font-size: 13px; color: #222; margin: 30px; }
  .header { background: #f5f5f5; border: 1px solid #ddd; padding: 8px 12px; margin-bottom: 0; }
  .header-row { margin: 2px 0; font-size: 12px; }
  .header-label { font-weight: bold; color: #555; }
  .body-content { border: 1px solid #ddd; border-top: none; padding: 12px 16px; margin-bottom: 20px; }
  .divider { border-top: 2px solid #999; margin: 24px 0; }
  .title { text-align: center; margin-bottom: 20px; }
  .title h2 { margin: 0; font-size: 16px; }
  .title p { margin: 4px 0; font-size: 11px; color: #666; }
  .footer { text-align: center; font-size: 10px; color: #888; margin-top: 30px; }
</style></head><body>""")

    parts.append(f"""<div class="title">
  <h2>Email Thread Record</h2>
  <p>Subject: {_escape(subject)}</p>
  <p>Captured: {datetime.now().strftime('%Y-%m-%d %H:%M')}</p>
</div>""")

    for i, msg in enumerate(messages):
        from_addr = msg.get("From", "Unknown")
        to_addr = msg.get("To", "Unknown")
        date_str = msg.get("Date", "")
        body_html = msg.get("_decoded_body", msg.get("snippet", ""))

        # Check if body is HTML or plain text
        is_html = body_html and "<" in body_html and (">" in body_html)

        parts.append('<div class="header">')
        parts.append(f'<div class="header-row"><span class="header-label">From:</span> {_escape(from_addr)}</div>')
        parts.append(f'<div class="header-row"><span class="header-label">To:</span> {_escape(to_addr)}</div>')
        if date_str:
            parts.append(f'<div class="header-row"><span class="header-label">Date:</span> {_escape(date_str)}</div>')
        parts.append('</div>')

        parts.append('<div class="body-content">')
        if body_html:
            if is_html:
                # Use original HTML body as-is (authentic content)
                parts.append(body_html)
            else:
                # Plain text — wrap in <pre> to preserve formatting
                parts.append(f'<pre style="white-space: pre-wrap; font-family: Arial, sans-serif; font-size: 13px;">{_escape(body_html)}</pre>')
        else:
            parts.append('<em style="color:#999;">(no content)</em>')
        parts.append('</div>')

        if i < len(messages) - 1:
            parts.append('<div class="divider"></div>')

    parts.append('<div class="footer">This is an unedited capture of the original email thread as received.</div>')
    parts.append("</body></html>")

    html_doc = "\n".join(parts)

    # Render to PDF with Playwright
    from playwright.async_api import async_playwright
    async with async_playwright() as p:
        browser = await p.chromium.launch()
        page = await browser.new_page()
        await page.set_content(html_doc, wait_until="networkidle")
        pdf_bytes = await page.pdf(format="A4", print_background=True, margin={
            "top": "15mm", "bottom": "15mm", "left": "10mm", "right": "10mm"
        })
        await browser.close()

    return pdf_bytes


async def _upload_thread_pdf(case_id: str, messages: List[Dict], subject: str, provider_name: str) -> str:
    """Generate an original email thread PDF and upload directly to CasePeer."""
    try:
        pdf_bytes = await _generate_original_thread_pdf(messages, subject)
        filename = f"Bill Confirmation Thread - {provider_name}.pdf"
        safe_filename = filename.encode("ascii", errors="replace").decode("ascii")

        result = _casepeer_upload(case_id, safe_filename, pdf_bytes)

        if result.get("success"):
            logger.info(f"[PDF] Uploaded original thread PDF '{safe_filename}' to case {case_id}")
            result["size_bytes"] = len(pdf_bytes)
            return json.dumps(result)
        else:
            logger.error(f"[PDF] Upload failed: {result.get('error')}")
            return json.dumps(result)

    except Exception as e:
        logger.error(f"[PDF] Thread PDF error: {e}", exc_info=True)
        return json.dumps({"error": str(e)})


def tool_get_treatment_page(case_id: str) -> str:
    """Scrape the CasePeer treatment page and extract provider/bill data with offer calculations.

    Delegates to casepeer_helpers.get_treatment_providers() which properly handles
    JSON.parse(...) extraction and the nested HEALTH_LIENS_DATA structure.
    """
    from casepeer_helpers import get_treatment_providers
    try:
        data = get_treatment_providers(case_id)
        if "error" in data:
            return json.dumps(data)

        # Reshape to match what the agent expects
        return json.dumps({
            "patient_name": data.get("patient_name", ""),
            "patient_dob": data.get("patient_dob", ""),
            "incident_date": data.get("incident_date", ""),
            "health_liens_count": data.get("health_liens_count", 0),
            "providers_calculated": data.get("providers", []),
            "lien_letters": data.get("lien_letters", []),
            "offer_letter_template_id": data.get("offer_letter_template_id", ""),
        })
    except Exception as e:
        logger.error(f"[Agent] get_treatment_page failed: {e}")
        return json.dumps({"error": str(e)})


def tool_generate_bill_correction_pdf(case_id: str, letter_type: str, patient_name: str,
                                       provider_name: str, original_bill: str,
                                       corrected_bill: str, offered_amount: str,
                                       patient_dob: str = "", injury_date: str = "",
                                       provider_address: str = "",
                                       total_medical_bills: str = "") -> str:
    """Generate a professional bill correction/confirmation letter and upload to CasePeer."""
    import requests as req
    from datetime import datetime

    try:
        pdf = FPDF()
        pdf.set_auto_page_break(auto=True, margin=20)
        pdf.add_page()

        # --- Letterhead ---
        pdf.set_font("Helvetica", "B", 18)
        pdf.cell(0, 12, "Beverly Law", new_x="LMARGIN", new_y="NEXT", align="C")
        pdf.set_font("Helvetica", "", 11)
        pdf.cell(0, 6, "Lien Negotiations Department", new_x="LMARGIN", new_y="NEXT", align="C")
        pdf.ln(8)

        # --- Date ---
        today = datetime.now().strftime("%B %d, %Y")
        pdf.set_font("Helvetica", "", 10)
        pdf.cell(0, 6, today, new_x="LMARGIN", new_y="NEXT")
        pdf.ln(4)

        # --- Provider address block ---
        if provider_address:
            for line in provider_address.split("\n"):
                pdf.cell(0, 5, line.strip().encode("latin-1", errors="replace").decode("latin-1"),
                         new_x="LMARGIN", new_y="NEXT")
            pdf.ln(4)

        # --- Title ---
        type_title = "Bill Correction Notice" if letter_type == "bill_correction" else "Bill Confirmation Notice"
        pdf.set_font("Helvetica", "B", 14)
        pdf.cell(0, 10, type_title, new_x="LMARGIN", new_y="NEXT", align="C")
        pdf.ln(4)

        # --- Divider ---
        pdf.set_draw_color(0, 0, 0)
        pdf.line(10, pdf.get_y(), 200, pdf.get_y())
        pdf.ln(6)

        # --- Patient & case info ---
        pdf.set_font("Helvetica", "", 10)
        pdf.set_fill_color(245, 245, 245)

        info_lines = [
            f"Patient Name: {patient_name}",
            f"Provider: {provider_name}",
        ]
        if patient_dob:
            info_lines.append(f"Date of Birth: {patient_dob}")
        if injury_date:
            info_lines.append(f"Date of Injury: {injury_date}")

        for line in info_lines:
            safe = line.encode("latin-1", errors="replace").decode("latin-1")
            pdf.cell(0, 6, safe, new_x="LMARGIN", new_y="NEXT", fill=True)
        pdf.ln(6)

        # --- Bill details table ---
        pdf.set_font("Helvetica", "B", 11)
        pdf.cell(0, 8, "Bill Details", new_x="LMARGIN", new_y="NEXT")
        pdf.ln(2)

        # Table header
        pdf.set_font("Helvetica", "B", 10)
        pdf.set_fill_color(220, 220, 220)
        col_w = 63
        pdf.cell(col_w, 7, "Original Bill", border=1, fill=True, align="C")
        if letter_type == "bill_correction":
            pdf.cell(col_w, 7, "Corrected Bill", border=1, fill=True, align="C")
        else:
            pdf.cell(col_w, 7, "Confirmed Bill", border=1, fill=True, align="C")
        pdf.cell(col_w, 7, "Settlement Offer", border=1, fill=True, align="C")
        pdf.ln()

        # Table row
        pdf.set_font("Helvetica", "", 10)
        safe_orig = original_bill.encode("latin-1", errors="replace").decode("latin-1")
        safe_corr = corrected_bill.encode("latin-1", errors="replace").decode("latin-1")
        safe_offer = offered_amount.encode("latin-1", errors="replace").decode("latin-1")
        pdf.cell(col_w, 7, safe_orig, border=1, align="C")
        pdf.cell(col_w, 7, safe_corr, border=1, align="C")
        pdf.cell(col_w, 7, safe_offer, border=1, align="C")
        pdf.ln()

        if total_medical_bills:
            pdf.ln(2)
            safe_total = total_medical_bills.encode("latin-1", errors="replace").decode("latin-1")
            pdf.set_font("Helvetica", "I", 10)
            pdf.cell(0, 6, f"Total Medical Bills: {safe_total}", new_x="LMARGIN", new_y="NEXT")

        pdf.ln(8)

        # --- Body text ---
        pdf.set_font("Helvetica", "", 10)
        if letter_type == "bill_correction":
            body = (
                f"This letter serves as a record that {provider_name} has corrected the billing for "
                f"patient {patient_name}. The original amount billed was {original_bill}, which has been "
                f"corrected to {corrected_bill}. Based on the corrected amount, our client's settlement "
                f"offer is {offered_amount}."
            )
        else:
            body = (
                f"This letter serves as a record that {provider_name} has confirmed the outstanding balance "
                f"for patient {patient_name}. The confirmed amount is {corrected_bill} (originally billed "
                f"as {original_bill}). Based on this confirmation, our client's settlement offer is "
                f"{offered_amount}."
            )

        safe_body = body.encode("latin-1", errors="replace").decode("latin-1")
        pdf.multi_cell(0, 5, safe_body)

        pdf.ln(12)

        # --- Signature ---
        pdf.set_font("Helvetica", "", 10)
        pdf.cell(0, 6, "Sincerely,", new_x="LMARGIN", new_y="NEXT")
        pdf.ln(4)
        pdf.set_font("Helvetica", "B", 10)
        pdf.cell(0, 6, "Lien Negotiations Department", new_x="LMARGIN", new_y="NEXT")
        pdf.cell(0, 6, "Beverly Law", new_x="LMARGIN", new_y="NEXT")

        # --- Footer ---
        pdf.ln(10)
        pdf.set_font("Helvetica", "I", 8)
        pdf.cell(0, 5, f"Generated on {datetime.now().strftime('%Y-%m-%d %H:%M')} by Beverly Law Lien Negotiations",
                 new_x="LMARGIN", new_y="NEXT", align="C")

        # --- Output and upload ---
        pdf_bytes = pdf.output()

        type_label = "Bill Correction" if letter_type == "bill_correction" else "Bill Conformation"
        filename = f"{type_label} from {provider_name} For {patient_name}.pdf"

        result = _casepeer_upload(case_id, filename, pdf_bytes)
        if result.get("success"):
            logger.info(f"[PDF] Uploaded bill correction: '{filename}' to case {case_id}")
            result["size_bytes"] = len(pdf_bytes)
            return json.dumps(result)
        else:
            logger.error(f"[PDF] Upload failed: {result.get('error')}")
            return json.dumps(result)

    except Exception as e:
        logger.error(f"[PDF] Bill correction PDF error: {e}", exc_info=True)
        return json.dumps({"error": str(e)})


def generate_offer_letter_pdf(case_id: str, patient_name: str, provider_name: str,
                              confirmed_bill: str, offered_amount: str,
                              patient_dob: str = "", injury_date: str = "",
                              provider_address: str = "") -> tuple:
    """
    Generate a formal 'Offer to Settle' letter as PDF.
    Returns (pdf_bytes, filename) for attachment sending + CasePeer upload.
    """
    from datetime import datetime

    try:
        pdf = FPDF()
        pdf.set_auto_page_break(auto=True, margin=20)
        pdf.add_page()

        # --- Letterhead ---
        pdf.set_font("Helvetica", "B", 18)
        pdf.cell(0, 12, "Beverly Law", new_x="LMARGIN", new_y="NEXT", align="C")
        pdf.set_font("Helvetica", "", 11)
        pdf.cell(0, 6, "Lien Negotiations Department", new_x="LMARGIN", new_y="NEXT", align="C")
        pdf.set_font("Helvetica", "", 9)
        pdf.cell(0, 5, "4929 Wilshire Blvd. Suite 960, Los Angeles, CA 90010", new_x="LMARGIN", new_y="NEXT", align="C")
        pdf.cell(0, 5, "Phone: (310) 552-6959 | Fax: (323) 421-9397", new_x="LMARGIN", new_y="NEXT", align="C")
        pdf.ln(8)

        # --- Date ---
        today = datetime.now().strftime("%B %d, %Y")
        pdf.set_font("Helvetica", "", 10)
        pdf.cell(0, 6, today, new_x="LMARGIN", new_y="NEXT")
        pdf.ln(4)

        # --- Provider address block ---
        if provider_address:
            for line in provider_address.split("\n"):
                pdf.cell(0, 5, line.strip().encode("latin-1", errors="replace").decode("latin-1"),
                         new_x="LMARGIN", new_y="NEXT")
            pdf.ln(4)

        # --- RE line ---
        pdf.set_font("Helvetica", "B", 10)
        pdf.cell(0, 6, f"RE: Offer to Settle Lien", new_x="LMARGIN", new_y="NEXT")
        pdf.set_font("Helvetica", "", 10)
        info_lines = [f"Patient: {patient_name}"]
        if patient_dob:
            info_lines.append(f"Date of Birth: {patient_dob}")
        if injury_date:
            info_lines.append(f"Date of Injury: {injury_date}")
        info_lines.append(f"Provider: {provider_name}")
        for line in info_lines:
            safe = line.encode("latin-1", errors="replace").decode("latin-1")
            pdf.cell(0, 5, safe, new_x="LMARGIN", new_y="NEXT")
        pdf.ln(6)

        # --- Divider ---
        pdf.set_draw_color(0, 0, 0)
        pdf.line(10, pdf.get_y(), 200, pdf.get_y())
        pdf.ln(6)

        # --- Body ---
        pdf.set_font("Helvetica", "", 10)
        safe_provider = provider_name.encode("latin-1", errors="replace").decode("latin-1")
        safe_patient = patient_name.encode("latin-1", errors="replace").decode("latin-1")
        safe_bill = confirmed_bill.encode("latin-1", errors="replace").decode("latin-1")
        safe_offer = offered_amount.encode("latin-1", errors="replace").decode("latin-1")

        body = (
            f"Dear {safe_provider},\n\n"
            f"Our office represents {safe_patient} regarding injuries sustained "
            f"{'on ' + injury_date if injury_date else 'in the above-referenced matter'}.\n\n"
            f"According to our records, the outstanding balance for services rendered to our client "
            f"is {safe_bill}.\n\n"
            f"In an effort to resolve this lien, our client is offering {safe_offer} as full and "
            f"final settlement of your lien.\n\n"
            f"If this offer is acceptable, please sign below and return this letter to our office "
            f"via email. Upon receipt of the signed acceptance, we will process payment accordingly.\n\n"
            f"If you have any questions or would like to discuss this matter further, please do not "
            f"hesitate to contact our office."
        )
        pdf.multi_cell(0, 5, body)
        pdf.ln(8)

        # --- Signature block ---
        pdf.cell(0, 6, "Sincerely,", new_x="LMARGIN", new_y="NEXT")
        pdf.ln(4)
        pdf.set_font("Helvetica", "B", 10)
        pdf.cell(0, 6, "Lien Negotiations Department", new_x="LMARGIN", new_y="NEXT")
        pdf.cell(0, 6, "Beverly Law", new_x="LMARGIN", new_y="NEXT")
        pdf.ln(16)

        # --- Acceptance section ---
        pdf.set_draw_color(0, 0, 0)
        pdf.line(10, pdf.get_y(), 200, pdf.get_y())
        pdf.ln(6)
        pdf.set_font("Helvetica", "B", 12)
        pdf.cell(0, 8, "ACCEPTANCE OF SETTLEMENT OFFER", new_x="LMARGIN", new_y="NEXT", align="C")
        pdf.ln(4)
        pdf.set_font("Helvetica", "", 10)

        acceptance_text = (
            f"I, on behalf of {safe_provider}, hereby accept the settlement offer of "
            f"{safe_offer} as full and final settlement of all liens and claims related to "
            f"the treatment of {safe_patient}. Upon receipt of the agreed-upon payment, "
            f"we will release all liens associated with this patient."
        )
        pdf.multi_cell(0, 5, acceptance_text)
        pdf.ln(10)

        # Signature lines
        pdf.cell(90, 6, "____________________________________", new_x="RIGHT", new_y="LAST")
        pdf.cell(10, 6, "", new_x="RIGHT", new_y="LAST")
        pdf.cell(90, 6, "____________________", new_x="LMARGIN", new_y="NEXT")
        pdf.set_font("Helvetica", "", 9)
        pdf.cell(90, 5, "Authorized Signature", new_x="RIGHT", new_y="LAST")
        pdf.cell(10, 5, "", new_x="RIGHT", new_y="LAST")
        pdf.cell(90, 5, "Date", new_x="LMARGIN", new_y="NEXT")
        pdf.ln(6)
        pdf.cell(90, 6, "____________________________________", new_x="LMARGIN", new_y="NEXT")
        pdf.set_font("Helvetica", "", 9)
        pdf.cell(90, 5, "Print Name / Title", new_x="LMARGIN", new_y="NEXT")

        # --- Footer ---
        pdf.ln(10)
        pdf.set_font("Helvetica", "I", 8)
        pdf.cell(0, 5, f"Generated on {datetime.now().strftime('%Y-%m-%d %H:%M')} by Beverly Law Lien Negotiations",
                 new_x="LMARGIN", new_y="NEXT", align="C")

        pdf_bytes = pdf.output()
        filename = f"Offer to Settle - {provider_name} For {patient_name}.pdf"

        logger.info(f"[PDF] Generated offer letter: '{filename}' ({len(pdf_bytes)} bytes)")
        return pdf_bytes, filename

    except Exception as e:
        logger.error(f"[PDF] Offer letter generation error: {e}", exc_info=True)
        return None, None


# Tool dispatcher
TOOL_FUNCTIONS = {
    "search_case": lambda args: tool_search_case(args["patient_name"]),
    "get_settlement_page": lambda args: tool_get_settlement_page(args["case_id"]),
    "get_treatment_page": lambda args: tool_get_treatment_page(args["case_id"]),
    "accept_lien": lambda args: tool_accept_lien(args["case_id"], args["provider_id"], args["offered_amount"]),
    "add_case_note": lambda args: tool_add_case_note(args["case_id"], args["note"]),
    "get_case_status": lambda args: tool_get_case_status(args["case_id"]),
    "log_negotiation": lambda args: tool_log_negotiation(**args),
    "generate_bill_correction_pdf": lambda args: tool_generate_bill_correction_pdf(
        case_id=args["case_id"],
        letter_type=args["letter_type"],
        patient_name=args["patient_name"],
        provider_name=args["provider_name"],
        original_bill=args["original_bill"],
        corrected_bill=args["corrected_bill"],
        offered_amount=args["offered_amount"],
        patient_dob=args.get("patient_dob", ""),
        injury_date=args.get("injury_date", ""),
        provider_address=args.get("provider_address", ""),
        total_medical_bills=args.get("total_medical_bills", ""),
    ),
}


# ---------------------------------------------------------------------------
# Conversation history — persist full AI chat per sender for continuity
# ---------------------------------------------------------------------------

def _get_conversation_key(case_id: str, provider_email: str) -> str:
    """Generate a stable key for a conversation (case_id + provider_email)."""
    return f"{case_id}|{provider_email.lower()}"


def _load_conversation_history(case_id: str, provider_email: str) -> Optional[List[Dict]]:
    """Load previous AI conversation for this case+provider from Turso."""
    from turso_client import turso
    try:
        if case_id:
            key = _get_conversation_key(case_id, provider_email)
            row = turso.fetch_one(
                "SELECT messages_json, tools_used FROM conversation_history WHERE id = ?",
                [key]
            )
        else:
            # No case_id yet — look up by provider email
            row = turso.fetch_one(
                "SELECT messages_json, tools_used, case_id FROM conversation_history WHERE sender_email = ? ORDER BY updated_at DESC LIMIT 1",
                [provider_email.lower()]
            )
        if row and row.get("messages_json"):
            return json.loads(row["messages_json"])
    except Exception as e:
        logger.warning(f"[Agent] Failed to load conversation history: {e}")
    return None


def _save_conversation_history(case_id: str, provider_email: str,
                                messages: List[Dict], tools_used: List[str],
                                intent: str):
    """Save the full AI conversation to Turso for next time."""
    from turso_client import turso
    try:
        key = _get_conversation_key(case_id, provider_email)
        # Serialize all messages including tool_calls
        safe_messages = []
        for msg in messages:
            if hasattr(msg, 'model_dump'):
                dumped = msg.model_dump()
                # Ensure tool_calls are preserved
                safe_messages.append(dumped)
            elif isinstance(msg, dict):
                safe_messages.append(msg)

        messages_json = json.dumps(safe_messages, default=str)

        turso.execute(
            "INSERT OR REPLACE INTO conversation_history (id, case_id, sender_email, thread_subject, messages_json, tools_used, last_intent, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?, datetime('now'))",
            [key, case_id, provider_email.lower(), "", messages_json, json.dumps(tools_used), intent]
        )
        logger.info(f"[Agent] Saved {len(safe_messages)} messages to conversation history for case {case_id} | {provider_email}")
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
- Our Last Offered Amount (ALREADY SENT — do NOT reuse as next offer, adjust per Rule 5): ${history_data.get('latest_offered_bill', 'N/A')}
- Total Negotiations on Record: {history_data.get('negotiation_count', 0)}
- Negotiation History (most recent first — use this to determine which ROUND you are in per Rule 5):
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
    prev_conversation = _load_conversation_history(pre_loaded_case_id, clean_sender)
    prior_context_note = ""
    prior_messages_to_inject = []  # Full messages to prepend to agent context
    if prev_conversation:
        prior_context_note = "\n\nPREVIOUS SESSION: You handled this provider before. Your prior tool calls and decisions are included in the conversation below. Do NOT repeat actions already performed (e.g. don't re-log the same negotiation, don't re-upload the same PDF).\n"

        # Build a detailed summary AND collect injectable messages
        summary_parts = []
        for prev_msg in prev_conversation:
            if not isinstance(prev_msg, dict):
                continue
            role = prev_msg.get("role", "")

            # Skip system messages (we'll use fresh system prompt)
            if role == "system":
                continue

            # Collect tool calls from assistant messages
            if role == "assistant":
                tool_calls = prev_msg.get("tool_calls", [])
                if tool_calls:
                    for tc in tool_calls:
                        fn = tc.get("function", {})
                        summary_parts.append(f"[TOOL CALLED] {fn.get('name', '?')}({fn.get('arguments', '?')[:150]})")
                elif prev_msg.get("content"):
                    summary_parts.append(f"[YOUR DECISION]: {prev_msg['content'][:600]}")

            elif role == "tool":
                tool_id = prev_msg.get("tool_call_id", "")
                content = prev_msg.get("content", "")
                summary_parts.append(f"[TOOL RESULT ({tool_id[:15]})]: {content[:300]}")

            elif role == "user":
                # Skip the full user message (we're building a fresh one)
                continue

        # Build text summary of prior actions
        if summary_parts:
            prior_context_note += "PRIOR SESSION ACTIONS:\n" + "\n".join(summary_parts) + "\n"

        logger.info(f"[Agent] Loaded previous conversation: {len(prev_conversation)} messages, {len(summary_parts)} actions for {clean_sender} | {thread_subject[:30]}")

    # --- PDF ATTACHMENT ANALYSIS (Gemini) ---
    pdf_context = ""
    pdf_analyses = thread_data.get("_pdf_analyses", [])
    if pdf_analyses:
        pdf_context = "\n\nPDF ATTACHMENTS ANALYZED (via Gemini):\n"
        for pa in pdf_analyses:
            pdf_context += f"- File: {pa.get('filename', '?')} | From: {pa.get('from', '?')}\n"
            analysis = pa.get("analysis")
            if analysis:
                pdf_context += f"  Original Bill: ${analysis.get('originalBill', 'N/A')}\n"
                pdf_context += f"  Offered Amount: ${analysis.get('offeredAmount', 'N/A')}\n"
                pdf_context += f"  Total Medical Bills: ${analysis.get('totalBill', 'N/A')}\n"
            else:
                pdf_context += "  (Gemini could not extract amounts from this PDF)\n"
        pdf_context += "\nUse these amounts when they are relevant to the negotiation (e.g. verifying bills, checking offers against the 33% cap).\n"
        logger.info(f"[Agent] Injecting {len(pdf_analyses)} PDF analysis result(s) into context")

    user_message = f"""Analyze the following email thread and determine the appropriate action.

EMAIL THREAD (chronological, oldest to newest):
{conversation_text}
{provider_context}
{prior_context_note}
{pdf_context}

METADATA:
- Thread ID: {thread_id}
- Last message from: {sender_email} ({clean_sender})
- Total messages in thread: {len(messages)}
{f'- Known Case ID: {pre_loaded_case_id}' if pre_loaded_case_id else '- Case ID: unknown — use search_case to find it'}

INSTRUCTIONS:
1. Classify the provider's MOST RECENT message intent.
2. You already have the case_id and full negotiation history pre-loaded above. Use them directly
   — do NOT call search_case unless no case_id was provided.
3. Use tools only when needed (e.g. get_treatment_page for bill lookup, generate_bill_correction_pdf for corrections).
   Do NOT call log_negotiation, add_case_note, accept_lien, or get_settlement_page — the system handles these automatically.
4. Compose a reply email if one is needed.
5. Return your final decision as a JSON object with these fields:
   - intent: the classification
   - reply_message: the HTML email to send back (or null if no reply needed)
   - provider_name: the MEDICAL FACILITY or COMPANY name (e.g. "Methodist Hospital", "Precise Imaging"), NOT the contact person's name. Extract from the email subject, our initial outreach, or the negotiation context.
   - patient_name: extracted from the conversation
   - actual_bill: the provider's total bill amount (number, e.g. 1500.00)
   - offered_bill: the settlement amount being discussed (number, e.g. 450.00)
   - reasoning: brief explanation of your decision

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
                model="gpt-5.2",
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
        log_token_usage(total_tokens, cost, "gpt-5.2")

        # Parse the JSON from the response
        result = _parse_agent_response(raw_text)
        result["actions_taken"] = actions_taken
        result["tokens_used"] = total_tokens
        result["thread_id"] = thread_id
        result["last_message_id"] = last_message_id

        # --- AUTOMATED POST-PROCESSING (code, not AI) ---
        intent = result.get("intent", "unclear")
        case_id = discovered_case_id

        if intent not in ("no_action", "unclear") and case_id:
            # 1. Always log the negotiation
            try:
                tool_log_negotiation(
                    case_id=case_id,
                    negotiation_type=intent,
                    email_body=result.get("reasoning", "")[:500],
                    to=clean_sender,
                    actual_bill=float(result.get("actual_bill") or 0),
                    offered_bill=float(result.get("offered_bill") or 0),
                    result=intent,
                    sent_by_us=False,
                )
                actions_taken.append("auto:log_negotiation(provider incoming)")
                logger.info(f"[PostProcess] Logged negotiation for {clean_sender} | intent={intent}")
            except Exception as e:
                logger.error(f"[PostProcess] Failed to log negotiation: {e}")

            # 2. Case notes removed — BCC'd email thread shows full negotiation in the case

            # 3. For bill_confirmation: auto-save original email thread PDF + update settlement amount
            if intent == "bill_confirmation":
                try:
                    provider_name = result.get("provider_name", "Provider")
                    upload_result = await _upload_thread_pdf(case_id, messages, thread_subject, provider_name)
                    actions_taken.append("auto:upload_original_thread_pdf(bill_confirmation)")
                    logger.info(f"[PostProcess] Uploaded bill confirmation thread PDF: {upload_result[:200]}")
                except Exception as e:
                    logger.error(f"[PostProcess] Thread PDF failed: {e}")

                # Update settlement page with confirmed balance amount
                try:
                    confirmed_amount = result.get("actual_bill")
                    if confirmed_amount and float(confirmed_amount) > 0:
                        settlement_json = tool_get_settlement_page(case_id)
                        settlement = json.loads(settlement_json)
                        form_fields = settlement.get("form_fields", {})
                        providers_list = settlement.get("providers", [])
                        provider_name_lower = (result.get("provider_name") or "").lower()

                        # Match provider by name (fuzzy)
                        matched_provider = None
                        for sp in providers_list:
                            sp_name = (sp.get("provider_name") or "").lower()
                            if provider_name_lower and (provider_name_lower in sp_name or sp_name in provider_name_lower):
                                matched_provider = sp
                                break

                        if matched_provider and matched_provider.get("provider_id") and form_fields:
                            pid = matched_provider["provider_id"]
                            clean_amount = re.sub(r'[^0-9.]', '', str(confirmed_amount))
                            # Update final_cost for this provider
                            updated = False
                            for key, value in form_fields.items():
                                if key.endswith("-id") and value == pid:
                                    index = re.search(r'health-liens-(\d+)-id', key)
                                    if index:
                                        cost_key = f"health-liens-{index.group(1)}-final_cost"
                                        form_fields[cost_key] = clean_amount
                                        updated = True
                                        break

                            if updated:
                                from casepeer_helpers import casepeer_post_form
                                form_body = "&".join(f"{quote(str(k), safe='')}={quote(str(v), safe='')}" for k, v in form_fields.items())
                                casepeer_post_form(f"case/{case_id}/settlement/negotiations/", form_body, timeout=90)
                                actions_taken.append(f"auto:update_settlement_amount(provider={pid}, amount={clean_amount})")
                                logger.info(f"[PostProcess] Updated settlement amount for {provider_name}: ${clean_amount}")
                            else:
                                logger.warning(f"[PostProcess] Provider ID {pid} not found in settlement form fields")
                        else:
                            logger.warning(f"[PostProcess] Could not match provider '{provider_name}' for settlement update")
                except Exception as e:
                    logger.error(f"[PostProcess] Settlement amount update failed: {e}")

            # 4. For "accepted": generate offer letter via CasePeer autoletters, send for signing
            if intent == "accepted":
                try:
                    offered_bill = result.get("offered_bill")
                    provider_name = result.get("provider_name", "Provider")
                    patient_name = result.get("patient_name", "Patient")

                    if offered_bill and float(offered_bill) > 0:
                        # Look up lien_id and template_id from CasePeer treatment page
                        lien_id, template_id = _find_lien_id_for_provider(case_id, provider_name)

                        file_bytes = None
                        file_format = None
                        if lien_id and template_id:
                            # Generate letter via CasePeer's built-in autoletters (auto-saved to case)
                            # Returns (bytes, "pdf"|"docx") — converts to PDF via LibreOffice, falls back to DOCX
                            file_bytes, file_format = await asyncio.to_thread(
                                _generate_casepeer_offer_letter, case_id, lien_id, template_id
                            )

                        if file_bytes:
                            if file_format == "pdf":
                                filename = f"Offer to Settle - {provider_name} For {patient_name}.pdf"
                                mime_type = "application/pdf"
                            else:
                                filename = f"Offer to Settle - {provider_name} For {patient_name}.docx"
                                mime_type = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"

                            actions_taken.append(f"auto:casepeer_offer_letter(lien={lien_id}, format={file_format})")
                            logger.info(f"[PostProcess] CasePeer generated offer letter for {provider_name} ({len(file_bytes)} bytes, {file_format})")

                            # Send as attachment in the same email thread
                            from gmail_poller import send_email_with_attachment, _get_gmail_creds
                            gmail_email, _, _ = _get_gmail_creds()

                            provider_msg = _find_provider_message(messages)
                            rfc_msg_id = provider_msg.get("Message-ID", "") if provider_msg else ""
                            rfc_refs = provider_msg.get("References", "") if provider_msg else ""
                            if rfc_msg_id:
                                refs = f"{rfc_refs} {rfc_msg_id}".strip() if rfc_refs else rfc_msg_id
                            else:
                                refs = rfc_refs

                            offer_body = (
                                f"Thank you for accepting our settlement offer.</br></br>"
                                f"Please find attached our formal Offer to Settle letter for the lien of "
                                f"{provider_name} regarding {patient_name} in the amount of "
                                f"${float(offered_bill):,.2f}.</br></br>"
                                f"To finalize, please sign the attached letter and return it to our office "
                                f"via email, along with a completed W9 and remittance instructions. "
                                f"Once we receive the signed letter, we will process payment accordingly."
                            )

                            # BCC the case email so offer letter shows in CasePeer
                            bcc_addr = f"{case_id}@bcc.casepeer.com" if case_id else ""

                            attach_sent = await asyncio.to_thread(
                                send_email_with_attachment,
                                gmail_email, clean_sender, thread_subject,
                                offer_body, file_bytes, filename,
                                in_reply_to=rfc_msg_id,
                                references=refs,
                                thread_id=thread_id,
                                content_type=mime_type,
                                bcc=bcc_addr,
                            )
                            if attach_sent:
                                actions_taken.append("auto:send_offer_letter_email")
                                logger.info(f"[PostProcess] Sent offer letter ({file_format}) to {clean_sender} for signing")
                            else:
                                logger.error(f"[PostProcess] Failed to send offer letter to {clean_sender}")
                        else:
                            logger.warning(f"[PostProcess] CasePeer autoletters failed — lien_id={lien_id}, template_id={template_id}")
                    else:
                        logger.warning(f"[PostProcess] No offered_bill for offer letter generation")
                except Exception as e:
                    logger.error(f"[PostProcess] Offer letter generation/send failed: {e}", exc_info=True)

            # 4b. For asked_for_clarification: if the bot says it's re-sending the offer letter,
            #     actually trigger letter generation (handles case where original send failed)
            if intent == "asked_for_clarification":
                reply_text = (result.get("reply_message") or "").lower()
                if any(phrase in reply_text for phrase in ["re-sent", "resent", "re-send", "resend", "sending it now", "having it sent"]):
                    try:
                        offered_bill = result.get("offered_bill")
                        provider_name = result.get("provider_name", "Provider")
                        patient_name = result.get("patient_name", "Patient")
                        if offered_bill and float(offered_bill) > 0:
                            lien_id, template_id = _find_lien_id_for_provider(case_id, provider_name)
                            if lien_id and template_id:
                                file_bytes, file_format = await asyncio.to_thread(
                                    _generate_casepeer_offer_letter, case_id, lien_id, template_id
                                )
                                if file_bytes:
                                    if file_format == "pdf":
                                        filename = f"Offer to Settle - {provider_name} For {patient_name}.pdf"
                                        mime_type = "application/pdf"
                                    else:
                                        filename = f"Offer to Settle - {provider_name} For {patient_name}.docx"
                                        mime_type = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"

                                    from gmail_poller import send_email_with_attachment, _get_gmail_creds
                                    gmail_email, _, _ = _get_gmail_creds()
                                    provider_msg = _find_provider_message(messages)
                                    rfc_msg_id = provider_msg.get("Message-ID", "") if provider_msg else ""
                                    rfc_refs = provider_msg.get("References", "") if provider_msg else ""
                                    refs = f"{rfc_refs} {rfc_msg_id}".strip() if rfc_msg_id else rfc_refs
                                    bcc_addr = f"{case_id}@bcc.casepeer.com" if case_id else ""

                                    offer_body = (
                                        f"Please find attached the formal Offer to Settle letter for "
                                        f"{provider_name} regarding {patient_name} in the amount of "
                                        f"${float(offered_bill):,.2f}.</br></br>"
                                        f"Please sign and return the attached letter, along with a completed W9 "
                                        f"and remittance instructions, so we can process payment."
                                    )
                                    attach_sent = await asyncio.to_thread(
                                        send_email_with_attachment,
                                        gmail_email, clean_sender, thread_subject,
                                        offer_body, file_bytes, filename,
                                        in_reply_to=rfc_msg_id, references=refs,
                                        thread_id=thread_id,
                                        content_type=mime_type, bcc=bcc_addr,
                                    )
                                    if attach_sent:
                                        actions_taken.append("auto:resend_offer_letter_email")
                                        logger.info(f"[PostProcess] Re-sent offer letter to {clean_sender}")
                                    else:
                                        logger.error(f"[PostProcess] Failed to re-send offer letter to {clean_sender}")
                                else:
                                    logger.warning(f"[PostProcess] Re-send: autoletters failed for {provider_name}")
                            else:
                                logger.warning(f"[PostProcess] Re-send: could not find lien/template for {provider_name}")
                    except Exception as e:
                        logger.error(f"[PostProcess] Offer letter re-send failed: {e}", exc_info=True)

            # 5. For accepted_and_provided_details: provider returned signed letter — auto-accept lien
            #    (provider confirmed acceptance + payment details). Plain "accepted" just logs —
            #    we need payment details before toggling the lien in CasePeer.
            if intent == "accepted_and_provided_details":
                try:
                    settlement_json = tool_get_settlement_page(case_id)
                    settlement = json.loads(settlement_json)
                    providers_list = settlement.get("providers", [])
                    provider_name_lower = (result.get("provider_name") or "").lower()

                    # Match provider by name (fuzzy)
                    matched_provider = None
                    for sp in providers_list:
                        sp_name = (sp.get("provider_name") or "").lower()
                        if provider_name_lower and (provider_name_lower in sp_name or sp_name in provider_name_lower):
                            matched_provider = sp
                            break

                    if matched_provider:
                        offered = result.get("offered_bill") or "0"
                        accept_result = tool_accept_lien(case_id, matched_provider["provider_id"], str(offered))
                        actions_taken.append(f"auto:accept_lien(provider_id={matched_provider['provider_id']}, amount={offered})")
                        logger.info(f"[PostProcess] Accepted lien for {matched_provider.get('provider_name')} | {accept_result[:200]}")
                    else:
                        logger.warning(f"[PostProcess] Could not match provider '{result.get('provider_name')}' in settlement page ({len(providers_list)} providers)")
                except Exception as e:
                    logger.error(f"[PostProcess] accept_lien flow failed: {e}")

            # Upload PDF attachments for both accepted intents
            if intent in ("accepted", "accepted_and_provided_details"):
                try:
                    pdf_analyses = thread_data.get("_pdf_analyses", [])
                    provider_name = result.get("provider_name", "Provider")
                    for pa in pdf_analyses:
                        pdf_bytes = pa.get("_pdf_bytes")
                        if pdf_bytes:
                            filename = pa.get("filename", f"Attachment - {provider_name}.pdf")
                            upload_result = _casepeer_upload(case_id, filename, pdf_bytes)
                            if upload_result.get("success"):
                                actions_taken.append(f"auto:upload_pdf_attachment({filename})")
                                logger.info(f"[PostProcess] Uploaded PDF '{filename}' to case {case_id}")
                            else:
                                logger.error(f"[PostProcess] PDF attachment upload failed: {upload_result.get('error')}")
                except Exception as e:
                    logger.error(f"[PostProcess] PDF attachment upload failed: {e}")

        # Save conversation history for future continuity
        _save_conversation_history(
            discovered_case_id, clean_sender,
            agent_messages, actions_taken,
            result.get("intent", "unclear"),
        )

        result["case_id"] = discovered_case_id
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
            reply = parsed.get("reply_message")

            # Strip any AI-added signature (the system appends the real one)
            if reply:
                # Remove sign-offs like "Sincerely,\nLien Negotiations..." or "Best regards,\n..."
                reply = re.sub(
                    r'(<br\s*/?>|\n){1,3}\s*(Sincerely|Best regards|Regards|Thank you|Warm regards|Kind regards|Respectfully),?\s*(<br\s*/?>|\n).*$',
                    '', reply, flags=re.IGNORECASE | re.DOTALL
                ).rstrip()
                # Also strip trailing "Lien Negotiations Department" if AI included it standalone
                reply = re.sub(
                    r'(<br\s*/?>|\n){1,3}\s*Lien Negotiations\s*(Department)?\s*(<br\s*/?>|\n)?\s*Beverly Law\s*$',
                    '', reply, flags=re.IGNORECASE | re.DOTALL
                ).rstrip()

            return {
                "intent": parsed.get("intent", "unclear"),
                "reply_message": reply,
                "provider_name": parsed.get("provider_name", "Unknown"),
                "patient_name": parsed.get("patient_name", "Unknown"),
                "reasoning": parsed.get("reasoning", ""),
                "actual_bill": parsed.get("actual_bill"),
                "offered_bill": parsed.get("offered_bill"),
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
