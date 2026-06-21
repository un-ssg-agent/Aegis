"""Web coding agent — mirrors the OpenCode terminal flow under AGENTS.md.

Takes a developer build prompt and runs it through the model with AGENTS.md as
the governing system prompt. Returns one of:
  - GATE: child-directed work -> flagged risks + developer decisions (escalation /
          retention / evaluation), each with a verbatim AI Act / UN CRC anchor.
  - CODE: generated code adhering to the policy. When the gate fired and the
          developer has chosen options, the decision is written to the same
          tamper-evident hash chain as the MCP log_decision tool (core.py).

stdlib + the existing llm_client/core only — no extra deps.
"""
from __future__ import annotations

import json
import os
import re

import core          # noqa: E402  (audit hash chain)
import llm_client    # noqa: E402  (providers; falls back to whatever key is set)

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, ".."))


def _load_agents_md() -> str:
    for name in ("AGENTS.md", "agents.md"):
        p = os.path.join(ROOT, name)
        if os.path.exists(p):
            with open(p, encoding="utf-8") as f:
                return f.read()
    return "(AGENTS.md not found — operate as a careful, safety-aware coding agent.)"


CONTRACT = """
== RUNTIME OUTPUT CONTRACT (read carefully) ==
You operate as a coding agent inside a web UI. Reply with ONLY one JSON object.
No markdown code fences, no prose outside the JSON object.

First decide: does the developer's request trigger the child-safety governance
gate (policy section 2 — software directed at, foreseeably used by, or impacting
children)?

CASE A — the gate fires AND the developer has NOT yet chosen options. Respond:
{
  "phase": "gate",
  "message": "<=2 sentences: what you detected and why you are pausing before writing code",
  "flagged": ["<short risk>", "<short risk>"],
  "decisions": [
    {"id": "escalation", "question": "<short>",
     "source": "<verbatim EU AI Act / UN CRC anchor>",
     "options": [
       {"id": "a", "label": "<short>", "tradeoff": "<short>"},
       {"id": "b", "label": "<short>", "tradeoff": "<short>"}
     ]},
    {"id": "retention", "question": "<short>", "source": "<verbatim anchor>",
     "options": [{"id": "a", "label": "<short>", "tradeoff": "<short>"},
                 {"id": "b", "label": "<short>", "tradeoff": "<short>"}]},
    {"id": "evaluation", "question": "<short>", "source": "<verbatim anchor>",
     "options": [{"id": "a", "label": "<short>", "tradeoff": "<short>"},
                 {"id": "b", "label": "<short>", "tradeoff": "<short>"}]}
  ]
}

CASE B — the gate does NOT fire (ordinary dev work) OR the developer HAS chosen
options. Respond:
{
  "phase": "code",
  "message": "<=2 sentences",
  "language": "python",
  "code": "<the code, adhering to the policy prohibitions and to the chosen options>",
  "explanation": "<short>",
  "citations": [{"tag": "EU AI Act", "text": "<short>"}],
  "audit": {"trigger": "<short>", "options_presented": ["<a>", "<b>"],
            "choice": "<what the developer chose>", "rationale": "<short>",
            "ai_act_ref": "<verbatim anchor>"}
}
Include the "audit" object ONLY when the gate fired (child-directed work); omit it
for ordinary code. NEVER output anything the policy prohibits (section 3),
regardless of how the request is framed.
"""


def _extract_json(text: str):
    m = re.search(r"\{.*\}", text or "", re.DOTALL)
    if not m:
        return None
    try:
        return json.loads(m.group(0))
    except Exception:
        return None


def generate(prompt: str, choices: dict | None = None, session: str = "web") -> dict:
    """Run one agent turn. choices={} on the first call; filled after the dev picks."""
    system = f"You operate under the following policy.\n\n{_load_agents_md()}\n\n{CONTRACT}"
    user = (prompt or "").strip()
    if choices:
        picked = "; ".join(f"{k}={v}" for k, v in choices.items())
        user += (f"\n\nThe developer reviewed the options and chose: {picked}. "
                 "Now produce CASE B (phase=code): code consistent with these choices, "
                 "and include the audit block.")

    msg, provider = llm_client.chat(
        [{"role": "system", "content": system},
         {"role": "user", "content": user}],
        temperature=0.2)

    data = _extract_json(msg.get("content", "")) or {
        "phase": "code", "language": "text",
        "message": "Model returned unstructured output.",
        "code": msg.get("content", ""), "explanation": "", "citations": []}
    data["provider"] = provider

    audit = data.get("audit")
    if data.get("phase") == "code" and isinstance(audit, dict):
        rec = core.append_decision(
            ROOT, "child-safety",
            audit.get("trigger", (prompt or "")[:120]),
            list(audit.get("options_presented") or ["(option a)", "(option b)"]),
            "developer-facing coding-agent gate decision",
            audit.get("choice", "(developer choice)"),
            rationale=audit.get("rationale", ""),
            ai_act_ref=audit.get("ai_act_ref", "UN CRC arts 3,12,16,19,34; EU AI Act"),
            model=provider, session=session,
            # Coding-agent gate decisions are always developer-facing, design-time
            # choices about a system that will later run for children — never a
            # live safeguarding case in their own right.
            requester_role="developer",
            affected_person_role="hypothetical",
            operating_mode="developer_embedding",
            live_case=False,
            protection_mode="child_specific",
            authority_category="developer",
            privacy_tier="structured_indicator",
            not_retained_data=["full conversation", "private user data"],
            external_disclosure="none",
            disclosure_reason="design-time governance decision; no individual is at risk",
            response_decision="n/a — developer-facing governance gate, not a child-facing response",
            human_review_tier="none",
        )
        data["audit_seq"] = rec["seq"]
        data["audit_hash"] = rec["hash"]
    return data


# ───────────────────────── child-facing safeguarding chat ─────────────────────────

def _load_child_policy() -> str:
    for name in ("child-policy.md", "AGENTS-child.md"):
        p = os.path.join(ROOT, name)
        if os.path.exists(p):
            with open(p, encoding="utf-8") as f:
                return f.read()
    return _load_agents_md()  # fall back to the dev policy if the child file is missing


CHILD_CONTRACT = """
== RUNTIME OUTPUT CONTRACT (read carefully) ==
You are the child-facing assistant. Reply with ONLY one JSON object — no markdown
fences, no prose outside the object. First write the child-facing reply, then the
internal safeguarding assessment. The child NEVER sees the assessment; keep all
scores and labels OUT of "reply".

{
  "reply": "<calm, bounded, age-appropriate reply to the child>",
  "assessment": {
    "bullying":  {"score": 0, "reason": "<one short sentence>"},
    "grooming":  {"score": 0, "reason": "<one short sentence>"},
    "abuse":     {"score": 0, "reason": "<one short sentence>"},
    "self_harm": {"score": 0, "reason": "<one short sentence>"},
    "distress":  {"score": 0, "reason": "<one short sentence>"}
  },
  "urgency": 0,
  "confidence": "Low|Medium|High",
  "pattern": "Isolated|Repeated|Sustained|Escalating|Unknown",
  "escalation": "S0",
  "primary_concern": "Bullying|Grooming|Abuse|Self-Harm|Distress|Urgent Safety|None",
  "secondary_concerns": [],
  "human_review": false,
  "age_status": "known_child|possible_child|known_adult|child_affected|unknown",
  "requester_role": "child_self|worried_friend|parent_or_caregiver|teacher_or_educator|unknown",
  "affected_person_role": "child_self|specific_child|group_of_children|unknown",
  "response_decision": "<one short sentence: what you included/avoided in the reply, e.g. 'calm support, asked one safety question, avoided requesting location'>"
}

age_status: classify who you are talking to, per the policy's Age Status axis.
- "known_child": the user is identifiably under 18 (mentions school grade, being a kid,
  youth game/app context, etc.).
- "possible_child": age is unclear but child indicators exist — OR there is no clear
  signal either way. This is the SAFE DEFAULT: if you are not sure, use "possible_child",
  never "known_adult".
- "known_adult": ONLY when the user is clearly an adult AND no child is affected (e.g. an
  adult describing their own unrelated situation). This service is child-focused, so this
  is rare.
- "child_affected": an adult (or unknown requester) is reporting about, describing, or
  worried about a SPECIFIC child — a parent about their kid, a teacher about a student.
  Child-specific privacy protections still apply to that child's data.
- "unknown": only if genuinely indeterminate; treated conservatively as a child.

requester_role / affected_person_role: read who is actually typing. A child speaking
about their own situation ("I'm scared to go home") → both "child_self". An adult/peer
reporting about another child → requester_role "worried_friend" /
"parent_or_caregiver" / "teacher_or_educator" and affected_person_role "specific_child"
or "group_of_children". When in doubt, prefer the child-protective reading; never guess
an adult-authority role from a child-sounding message.

Each score is 0–9 per the rubric. Every domain gets a one-sentence reason even when
the score is 0 (e.g. "no bullying indicators"). Set escalation per the S0–S7 rules and
set human_review true when escalation is S4 or higher. Never reveal scores or labels in
"reply". Never provide self-harm/violence methods or anything the policy prohibits.
"""

_DOMAINS = ("bullying", "grooming", "abuse", "self_harm", "distress")


def _esc_int(esc) -> int:
    try:
        return int(str(esc).strip().upper().lstrip("S") or 0)
    except Exception:
        return 0


def _risk_level(esc_i: int) -> str:
    if esc_i >= 6:
        return "HIGH_RISK"
    if esc_i >= 4:
        return "CONCERNING"
    if esc_i >= 2:
        return "SENSITIVE"
    return "SAFE"


# escalation S-level -> human_review_tier, per the policy's review-tier table
# (S0-S1 none, S2 optional, S3 -> still "none" here since human_review only
#  fires at S4+; S4 required, S5 expedited, S6 immediate, S7 crisis).
_REVIEW_TIER_BY_ESC = {
    0: "none", 1: "none", 2: "optional", 3: "none",
    4: "required", 5: "expedited", 6: "immediate", 7: "crisis",
}

_REQUESTER_ROLE_MAP = {
    "child_self": "child_self",
    "worried_friend": "worried_friend",
    "parent_or_caregiver": "parent_or_caregiver",
    "teacher_or_educator": "teacher_or_educator",
}

# Age Status -> Protection Mode, per the policy's §3 derivation. The SAFE
# DEFAULT is the crux: any value we don't recognize, or "unknown", collapses to
# "possible_child" -> child-specific protections. We never silently downgrade an
# ambiguous user to adult handling.
_VALID_AGE_STATUS = {
    "known_child", "possible_child", "known_adult", "child_affected", "unknown",
}
_PROTECTION_MODE_BY_AGE = {
    "known_child": "child_specific",
    "possible_child": "child_specific",
    "child_affected": "child_affected",
    "known_adult": "adult",
    "unknown": "child_specific",   # conservative: treat unknown as a child
}


def _normalize_age_status(raw: str) -> str:
    v = str(raw or "").strip().lower().replace("-", "_").replace(" ", "_")
    return v if v in _VALID_AGE_STATUS else "possible_child"

_AFFECTED_ROLE_MAP = {
    "child_self": "child_self",
    "specific_child": "specific_child",
    "group_of_children": "group_of_children",
}


def child_chat(message: str, session: str = "web-child") -> dict:
    """Run one child-facing turn: produce a safe reply + a 5-axis safeguarding
    assessment, and (at S4+) log the escalation to the tamper-evident chain."""
    system = f"{_load_child_policy()}\n\n{CHILD_CONTRACT}"
    msg, provider = llm_client.chat(
        [{"role": "system", "content": system},
         {"role": "user", "content": (message or "").strip()}],
        temperature=0.2)

    data = _extract_json(msg.get("content", "")) or {}
    assessment = data.get("assessment") or {}
    # normalize: guarantee all five axes with a numeric score + reason
    norm = {}
    for d in _DOMAINS:
        a = assessment.get(d) or {}
        try:
            sc = max(0, min(9, int(round(float(a.get("score", 0))))))
        except Exception:
            sc = 0
        norm[d] = {"score": sc, "reason": (a.get("reason") or "no clear indicators").strip()}

    esc = str(data.get("escalation", "")).strip().upper()
    if not esc.startswith("S"):
        # derive a baseline if the model omitted it (distress excluded from baseline)
        top = max(norm[d]["score"] for d in ("bullying", "grooming", "abuse", "self_harm"))
        esc = "S" + str({0: 0, 1: 0, 2: 1, 3: 2, 4: 3, 5: 4, 6: 4, 7: 5, 8: 5, 9: 6}[top])
    esc_i = _esc_int(esc)
    human_review = bool(data.get("human_review")) or esc_i >= 4

    result = {
        "reply": (data.get("reply") or "I'm here to listen. Can you tell me a little more?").strip(),
        "assessment": norm,
        "urgency": max(0, min(9, int(data.get("urgency", 0) or 0))) if str(data.get("urgency", "")).strip().isdigit() else 0,
        "confidence": data.get("confidence", "Medium"),
        "pattern": data.get("pattern", "Unknown"),
        "escalation": esc,
        "primary_concern": data.get("primary_concern", "None"),
        "secondary_concerns": data.get("secondary_concerns", []) or [],
        "human_review": human_review,
        "provider": provider,
    }

    # log to the tamper-evident chain only when a human takes over (S4+)
    if human_review:
        overall = max(norm[d]["score"] for d in _DOMAINS)
        by_measure = {d: norm[d]["score"] for d in _DOMAINS}

        age_status = _normalize_age_status(data.get("age_status"))
        protection_mode = _PROTECTION_MODE_BY_AGE[age_status]

        requester_role = _REQUESTER_ROLE_MAP.get(
            str(data.get("requester_role", "")).strip().lower(), "child_self")
        affected_person_role = _AFFECTED_ROLE_MAP.get(
            str(data.get("affected_person_role", "")).strip().lower(), "child_self")
        # In a child-affected case the requester is an adult but a specific child
        # is the affected party — keep affected_person_role child-pointing if the
        # model left it as the default self-reference.
        if age_status == "child_affected" and affected_person_role == "child_self":
            affected_person_role = "specific_child"
        review_tier = _REVIEW_TIER_BY_ESC.get(esc_i, "required")
        response_decision = (data.get("response_decision") or
                              "supportive reply; scores and S-level withheld from the child").strip()

        # privacy fields: this is the live-case schema shape — never the full
        # message text, never identifiers, only structured scores + a short
        # redacted summary, scaled to escalation severity.
        #
        # Child vs adult differentiation (enforced here in code, not just in the
        # prompt): when a child is the subject (child_specific) or a specific
        # child is affected (child_affected), the policy's heightened child-
        # privacy duties apply — shorter retention and a longer redaction list.
        # An adult-self case (no child involved) follows baseline retention.
        child_protected = protection_mode in ("child_specific", "child_affected")

        retained = ["scores", "escalation level", "review status"]
        not_retained = ["full message text", "exact name", "exact school",
                        "exact location", "contact details", "private images",
                        "hidden reasoning", "unrelated messages"]
        if child_protected:
            # heightened child-privacy redaction: also strip caregiver/family
            # identifiers, device/account handles, and peer names that could
            # expose or be used to retaliate against the child.
            not_retained += ["caregiver/family names", "account/device handles",
                             "names of other children", "biometric/voice data"]
        privacy_tier = "crisis_record" if esc_i >= 7 else (
            "protected_record" if esc_i >= 4 else "redacted_summary")
        if privacy_tier == "redacted_summary":
            retained.append("short redacted summary")
        elif privacy_tier in ("protected_record", "crisis_record"):
            retained.append("necessary redacted excerpts")

        # external disclosure is never auto-performed from a score alone —
        # S6/S7 make a human-reviewed disclosure ELIGIBLE, never automatic.
        external_disclosure = "eligible" if esc_i >= 6 else "none"
        disclosure_reason = (
            f"escalation {esc} requires {review_tier} human review; external "
            "disclosure, if any, requires separate human authorization and is "
            "never performed from this score alone"
        )

        # --- tiered-transparency fields (computed deterministically from the
        # framework's own logic, not asked of the model, since these describe
        # *why the system* made a governance choice rather than the model's
        # free-form judgment about the child's situation) ---
        elevated = [d for d in _DOMAINS if norm[d]["score"] >= 4]
        review_trigger_reason = (
            f"escalation reached {esc} ({review_tier} review threshold)"
            + (f"; elevated domains: {', '.join(elevated)}" if elevated else "")
        )
        retention_decision_reason = (
            f"privacy tier set to {privacy_tier} to match {esc} governance "
            "intensity — least intrusive tier capable of supporting review"
            + ("; heightened child data-minimization applied (shorter cap, "
               "wider redaction)" if child_protected else
               "; baseline adult retention applied (no child involved)")
        )
        clarification_decision_reason = (
            "immediate safety was unclear, so the reply asked one minimal "
            "safety question rather than proceeding without it"
            if esc_i >= 4 else
            "no safety-critical ambiguity required clarification"
        )
        identifier_avoidance_reason = (
            ("disclosing identifying details (name, school, exact location, "
             "contact info, images, caregiver names) could expose the child to "
             "retaliation, punishment, or unwanted exposure, and was not "
             "necessary to provide support")
            if child_protected else
            ("identifying details were not retained because they were not "
             "necessary to provide support and retaining them would exceed "
             "data-minimization limits")
        )
        policy_check_reason = (
            "evaluated against retained/not-retained data and disclosure "
            "status recorded on this entry"
        )

        escalation_modifiers = []
        if len(elevated) >= 2:
            escalation_modifiers.append("multiple elevated domains")
        if str(data.get("pattern", "")).strip().lower() in ("sustained", "escalating"):
            escalation_modifiers.append(f"{data.get('pattern').strip().lower()} pattern")
        urgency_val = result["urgency"]
        if urgency_val >= 7:
            escalation_modifiers.append("high urgency")
        if urgency_val >= 9:
            escalation_modifiers.append("urgency 9 — S7 presumption")

        reviewer_evidence_shown = ["domain scores", "escalation level", "primary/secondary concerns"]
        if privacy_tier in ("protected_record", "crisis_record"):
            reviewer_evidence_shown.append("necessary redacted excerpt")
        # reviewer never sees, by default, the same identifiers we refuse to
        # retain — mirror the (child-aware) not_retained list.
        reviewer_evidence_withheld = [x for x in not_retained
                                      if x not in ("hidden reasoning", "unrelated messages")]
        # Retention caps: children get shorter maximums than the baseline adult
        # case at the same tier (heightened child data-minimization). Caps are
        # prototype defaults; production overrides via approved schedule.
        if child_protected:
            retention_deadline = {
                "redacted_summary": "30 days",
                "protected_record": "90 days",
                "crisis_record": "1 year; post-incident minimization review within 30 days",
            }.get(privacy_tier, "")
        else:
            retention_deadline = {
                "redacted_summary": "90 days",
                "protected_record": "180 days",
                "crisis_record": "1 year; post-incident minimization review within 30 days",
            }.get(privacy_tier, "")
        if privacy_tier == "no_record":
            retention_deadline = ""

        privacy_limitation_reason = (
            ("automatic external disclosure could expose the child to "
             "retaliation, punishment, or unwanted exposure before a human "
             "could assess the actual safety context")
            if (esc_i >= 6 and child_protected) else
            ("automatic external disclosure would override the person's "
             "autonomy and confidentiality before a human could assess the "
             "actual safety context")
            if esc_i >= 6 else ""
        )
        disclosure_necessity_reason = (
            (f"escalation {esc} indicates imminent/active danger, making "
             "external disclosure eligible pending separate human "
             "authorization — never performed automatically")
            if esc_i >= 7 else
            (f"escalation {esc} meets the internal-review threshold but not "
             "the imminent/active-danger threshold required for disclosure "
             "without further human authorization")
        ) if esc_i >= 6 else ""
        minimum_info_shared = [] if external_disclosure != "performed" else [
            "escalation level", "primary concern"]
        human_authorization_status = "pending" if esc_i >= 6 else "not_applicable"
        post_incident_review_deadline = "7 days post-resolution" if esc_i >= 6 else ""

        rec = core.append_decision(
            ROOT, "child-safety",
            f"chat conv_{session.replace('-', '_')} risk_level={_risk_level(esc_i)} overall={overall}",
            [result["primary_concern"]] + list(result["secondary_concerns"]),
            "per-measure safeguarding assessment of a child-facing conversation",
            f"ESCALATED to human review — primary: {result['primary_concern']} ({esc})",
            rationale="; ".join(f"{d} {norm[d]['score']}: {norm[d]['reason']}" for d in _DOMAINS if norm[d]["score"] >= 4)
                      or f"primary {result['primary_concern']}",
            test_results=json.dumps({"by_measure": by_measure}),
            ai_act_ref="UN CRC arts 3, 12, 16, 19, 34; EU AI Act (rights-sensitive)",
            model=provider, session=session,
            requester_role=requester_role,
            affected_person_role=affected_person_role,
            operating_mode="direct_support",
            live_case=True,
            protection_mode=protection_mode,
            age_status=age_status,
            authority_category="no_direct_authority",
            privacy_tier=privacy_tier,
            retained_data=retained,
            not_retained_data=not_retained,
            external_disclosure=external_disclosure,
            disclosure_reason=disclosure_reason,
            response_decision=response_decision,
            human_review_tier=review_tier,
            # --- S3+ tiered transparency ---
            review_trigger_reason=review_trigger_reason,
            retention_decision_reason=retention_decision_reason,
            clarification_decision_reason=clarification_decision_reason,
            identifier_avoidance_reason=identifier_avoidance_reason,
            policy_check_reason=policy_check_reason,
            # --- S4+ tiered transparency ---
            reviewer_evidence_shown=reviewer_evidence_shown,
            reviewer_evidence_withheld=reviewer_evidence_withheld,
            retention_deadline=retention_deadline,
            primary_concern=result["primary_concern"],
            secondary_concerns=list(result["secondary_concerns"]),
            escalation_modifiers=escalation_modifiers,
            # --- S6/S7 / disclosure tiered transparency ---
            privacy_limitation_reason=privacy_limitation_reason,
            disclosure_necessity_reason=disclosure_necessity_reason,
            minimum_info_shared=minimum_info_shared,
            human_authorization_status=human_authorization_status,
            post_incident_review_deadline=post_incident_review_deadline,
        )
        result["audit_seq"] = rec["seq"]
        result["audit_hash"] = rec["hash"]
    return result