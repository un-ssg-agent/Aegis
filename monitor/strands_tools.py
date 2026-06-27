"""Strands tools used by the coding-agent gate and the child-facing chat.

Two tools wrap EXISTING code (core.append_decision, child_classifier) rather
than reimplementing anything — the audit chain and the rule-based classifier
stay exactly as they are; these are thin, schema-typed call surfaces so a
Strands Agent can invoke them directly.

lookup_crisis_resource is new: it answers the "can we surface a real helpline
to a child in crisis" question from the planning doc. The model NEVER invents
a hotline number itself — it can only call this tool and weave the verified
result into its reply. Coverage is intentionally small and conservative; see
RESOURCES below and extend it before relying on it for non-English regions.
"""
from __future__ import annotations

import os
import sys
from typing import Any

from strands import tool

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, ".."))
COMPLIANCE_DIR = os.path.join(ROOT, "mcp-servers", "compliance-auditor")
sys.path.insert(0, COMPLIANCE_DIR)

import core  # noqa: E402  (audit hash chain — unchanged)

sys.path.insert(0, COMPLIANCE_DIR)  # child_classifier is a package inside compliance-auditor
from child_classifier import classify_message  # noqa: E402


# ───────────────────────── log_decision ─────────────────────────

def _log_decision_impl(
    domain: str,
    trigger: str,
    options_presented: list[str],
    implications: str,
    user_choice: str,
    rationale: str = "",
    ai_act_ref: str = "",
    session: str = "web",
    model: str = "strands-agent",
) -> dict:
    """Plain-Python implementation, called directly by strands_agent.py (NOT
    through the @tool wrapper) so we get the raw dict back with certainty,
    rather than relying on how @tool unwraps a direct call's return value.
    See the @tool-decorated log_decision below for the model-facing version.
    """
    rec = core.append_decision(
        ROOT, domain, trigger, list(options_presented or ["(option a)", "(option b)"]),
        implications, user_choice, rationale=rationale,
        ai_act_ref=ai_act_ref or "UN CRC arts 3,12,16,19,34; EU AI Act",
        model=model, session=session,
    )
    return {"audit_seq": rec["seq"], "audit_hash": rec["hash"]}


@tool
def log_decision(
    domain: str,
    trigger: str,
    options_presented: list[str],
    implications: str,
    user_choice: str,
    rationale: str = "",
    ai_act_ref: str = "",
    session: str = "web",
    model: str = "strands-agent",
) -> dict:
    """Append a tamper-evident decision to the audit hash chain.

    Call this AFTER a developer has chosen among presented gate options (or
    after a child-facing turn crosses a safeguarding threshold) and BEFORE
    acting on that choice. Do NOT invent a hash — this tool computes the
    real SHA-256 chain via core.append_decision. `domain` is one of:
    child-safety | privacy | security | fairness.

    Returns: {"audit_seq": int, "audit_hash": str}
    """
    return _log_decision_impl(
        domain, trigger, options_presented, implications, user_choice,
        rationale=rationale, ai_act_ref=ai_act_ref, session=session, model=model,
    )


# ───────────────────────── classify_risk ─────────────────────────

@tool
def classify_risk(text: str, conversation_id: str | None = None) -> dict:
    """Score a single child-facing chat message for safety risk using the
    in-house rule-based classifier (mcp-servers/compliance-auditor/child_classifier).

    This is NOT an LLM call — it runs the existing deterministic pattern-match
    + scoring engine (8 categories: self_harm, grooming, bullying,
    sexual_exploitation, violence, pii_exposure, discrimination, distress) and
    returns its output as-is. Use this as a fast, explainable second signal
    alongside the LLM's own 5-axis assessment — NOT a replacement for it; the
    two systems currently use different category sets (see planning doc §4.2).

    Returns the classifier's native assessment dict: overall (1.0-10.0),
    risk_level (SAFE|SENSITIVE|CONCERNING|HIGH_RISK), by_measure (per-category
    scores), top_signals (matched pattern descriptions).
    """
    return classify_message(text, conversation_id=conversation_id)


# ───────────────────────── lookup_crisis_resource ─────────────────────────

# Verified, conservative starter set. Each entry is a real, currently-operating
# service as of this writing — do NOT let the model invent additional entries.
# Extend this table (don't ask the model to) before claiming broader coverage
# in the Innovation Brief.
RESOURCES: dict[str, dict[str, Any]] = {
    "default_international": {
        "name": "Find A Helpline",
        "description": "Directory of crisis lines by country",
        "url": "https://findahelpline.com",
    },
    "en-US": {
        "name": "988 Suicide & Crisis Lifeline",
        "phone": "988",
        "text": "Text 988",
        "url": "https://988lifeline.org",
    },
    "en-GB": {
        "name": "Childline",
        "phone": "0800 1111",
        "url": "https://www.childline.org.uk",
    },
    "en-CA": {
        "name": "Kids Help Phone",
        "phone": "1-800-668-6868",
        "text": "Text CONNECT to 686868",
        "url": "https://kidshelpphone.ca",
    },
    "en-AU": {
        "name": "Kids Helpline",
        "phone": "1800 55 1800",
        "url": "https://kidshelpline.com.au",
    },
}

# category -> whether a resource should even be considered (kept narrow:
# this is about safety-critical categories, not every flagged concern)
_RESOURCE_ELIGIBLE_CATEGORIES = {"self_harm", "abuse", "distress", "Urgent Safety", "Self-Harm"}


def _lookup_crisis_resource_impl(
    category: str,
    region_hint: str | None = None,
    language: str | None = None,
) -> dict | None:
    """Plain-Python implementation, called directly by strands_agent.py for the
    DETERMINISTIC S4+ guarantee (NOT through the @tool wrapper). The returned
    resource content is ALWAYS drawn from the verified RESOURCES table above —
    never invented — so this is safe to call with no model in the loop. Returns
    None if the category isn't safety-critical enough to surface a resource.
    """
    if category not in _RESOURCE_ELIGIBLE_CATEGORIES:
        return None
    key = region_hint if region_hint in RESOURCES else "default_international"
    resource = dict(RESOURCES[key])
    resource["region_used"] = key
    resource["coverage_note"] = (
        "International directory — country-specific line not confirmed for this region"
        if key == "default_international" else "Verified region-specific resource"
    )
    return resource


@tool
def lookup_crisis_resource(
    category: str,
    region_hint: str | None = None,
    language: str | None = None,
) -> dict | None:
    """Look up a VERIFIED crisis resource for a child-facing safeguarding reply.

    The model must call this tool to obtain a resource — it must never write a
    hotline number or URL from its own memory, since a hallucinated crisis
    number in a child-safety product is a serious failure mode. Returns None
    if the category isn't safety-critical enough to warrant surfacing a
    resource (use normal supportive reply instead).

    region_hint: a BCP-47-ish region code if known (e.g. "en-US", "en-GB").
    Defaults to the international directory when unknown — coverage here is
    intentionally small; extend RESOURCES before claiming broader reach.
    """
    return _lookup_crisis_resource_impl(category, region_hint, language)