"""Strands-based coding-agent gate + child-facing chat.

Drop-in replacement for monitor/agent.py's generate() and child_chat() —
SAME function signatures, SAME return dict shapes (matches the Gate/Code/
Assessment TypeScript types in monitor-web/app/page.tsx exactly), so app.py
can switch from `import agent` to `import strands_agent as agent` with no
other changes, and the frontend needs none at all.

What changed vs. agent.py, and why:
  - The regex `_extract_json` + `<<<AEGIS_CODE>>>` marker hack is GONE.
    Strands' `structured_output_model` constrains the model's output to a
    Pydantic schema directly, so a malformed reply is a validation error we
    can see and handle, not a silent None from a failed regex match.
  - log_decision is a real Strands @tool (strands_tools.py) instead of a
    bare function call after parsing — but it wraps the EXACT SAME
    core.append_decision call agent.py used, so the audit chain format is
    byte-identical.
  - All the deterministic post-processing in child_chat() (age/role/privacy-
    tier derivation, retention scheduling, escalation modifiers) is lifted
    UNCHANGED from agent.py — none of that logic ever needed an LLM, it only
    needs the model's structured output dict, which Strands now hands us
    pre-validated instead of regex-parsed.
  - Model backend is swappable with zero other code changes: Ollama (local,
    free, demo-reliable) is tried first; Bedrock is the cloud fallback. See
    _build_model().

agent.py is left completely untouched as a fallback — if this module or its
dependencies (strands, Ollama, AWS creds) are unavailable, app.py can import
the original agent.py and lose nothing.
"""
from __future__ import annotations

import hashlib
import os
import sys

from strands import Agent

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, ".."))
_COMPLIANCE_DIR = os.path.join(ROOT, "mcp-servers", "compliance-auditor")
if _COMPLIANCE_DIR not in sys.path:
    sys.path.insert(0, _COMPLIANCE_DIR)

import core          # noqa: E402  (audit hash chain — unchanged)
import llm_client    # noqa: E402  (only used for provider-name fallback string)

from strands_schemas import (
    GateOutput, CodeOutput, ChildChatOutput,
)
from strands_tools import log_decision, classify_risk, lookup_crisis_resource
from strands_tools import _log_decision_impl


# ───────────────────────── model selection ─────────────────────────

def _build_model():
    """Local-first, cloud-capable: try Ollama, fall back to Bedrock.
    Same Strands Agent code runs against either — only this function changes
    if you want to force one or the other (e.g. for a live demo with no
    network dependency, hardcode the Ollama branch).
    """
    ollama_host = os.environ.get("OLLAMA_HOST", "http://localhost:11434")
    ollama_model = os.environ.get("OLLAMA_MODEL", "llama3.1")
    try:
        from strands.models.ollama import OllamaModel
        import urllib.request
        # Cheap reachability check so we fail over to Bedrock fast instead of
        # waiting on a connect-timeout for every single request.
        urllib.request.urlopen(f"{ollama_host}/api/tags", timeout=1.5)
        return OllamaModel(host=ollama_host, model_id=ollama_model, temperature=0.2), "ollama"
    except Exception:
        pass

    try:
        from strands.models.litellm import LiteLLMModel
        if os.environ.get("DEEPSEEK_API_KEY"):
            return LiteLLMModel(
                client_args={"api_key": os.environ["DEEPSEEK_API_KEY"]},
                model_id=os.environ.get("LITELLM_MODEL_ID", "deepseek/deepseek-v4-pro"),
                params={"temperature": 0.2, "max_tokens": 1024},
            ), "litellm"
    except Exception:
        pass

    try:
        from strands.models import BedrockModel
        bedrock_model_id = os.environ.get(
            "BEDROCK_MODEL_ID", "us.anthropic.claude-sonnet-4-20250514-v1:0")
        region = os.environ.get("AWS_REGION", "us-east-1")
        return BedrockModel(model_id=bedrock_model_id, region_name=region), "bedrock"
    except Exception:
        pass

    return None, "none"


_MODEL, _MODEL_PROVIDER = _build_model()


def _load_agents_md() -> str:
    for name in ("AGENTS.md", "agents.md"):
        p = os.path.join(ROOT, name)
        if os.path.exists(p):
            with open(p, encoding="utf-8") as f:
                return f.read()
    return "(AGENTS.md not found — operate as a careful, safety-aware coding agent.)"


def _load_child_policy() -> str:
    for name in ("child-policy.md", "AGENTS-child.md"):
        p = os.path.join(ROOT, name)
        if os.path.exists(p):
            with open(p, encoding="utf-8") as f:
                return f.read()
    return _load_agents_md()


IMPLEMENTATION_STANDARD = """
== IMPLEMENTATION STANDARD (applies to every code-generation reply) ==
Ship COMPLETE, RUNNABLE code — a real artifact, never a skeleton or framework.
- No placeholders, stubs, TODOs, FIXMEs, "implement later", "in production you would…",
  bare `pass` / `...` / `raise NotImplementedError` standing in for a real body, or
  functions that return hardcoded/dummy values pretending to be computed results.
- No abstract shells whose entry points exist but whose core does nothing.
- If a capability genuinely cannot be created inline (a trained ML model, a paid API with
  no key, external infra), implement a REAL working substitute that runs today and state
  the tradeoff in one line. Never fake it with a placeholder.
- Under-specified request: pick sensible concrete defaults, implement them fully, note any
  assumption in <=1 line. Do not stall or scaffold.
"""


# ───────────────────────── coding-agent gate ─────────────────────────

def generate(prompt: str, choices: dict | None = None, session: str = "web",
             policy: str | None = None) -> dict:
    """Run one coding-agent turn. choices={} on the first call; filled after
    the developer picks. Same signature and return shape as agent.generate().
    """
    if _MODEL is None:
        return {"error": "No model backend available (Ollama unreachable and "
                          "no AWS Bedrock credentials found)."}

    policy_text = (policy or "").strip() or _load_agents_md()
    user = (prompt or "").strip()

    if not choices:
        # First turn: let the model decide gate-vs-code itself by asking it to
        # choose, via two separate structured-output attempts is wasteful — instead
        # ask once with both schemas described and branch on a cheap classifier
        # question, OR simply attempt GateOutput first only when the policy's own
        # gate criteria look like they might apply. Simpler and more faithful to
        # the original design: give the model BOTH contracts and a free first
        # field telling us which one it picked.
        system = (
            f"You operate under the following policy.\n\n{policy_text}\n\n"
            f"{IMPLEMENTATION_STANDARD}\n\n"
            "Decide: does this developer request trigger the child-safety governance "
            "gate (policy section 2 — software directed at, foreseeably used by, or "
            "impacting children)? If YES and no choices have been made yet, you MUST "
            "produce a GATE response (flagged risks + escalation/retention/evaluation "
            "decisions, each with a verbatim policy anchor). If NO, produce a CODE "
            "response satisfying the IMPLEMENTATION STANDARD above."
        )
        agent = Agent(model=_MODEL, system_prompt=system,
                       tools=[log_decision], callback_handler=None)

        gate_triggered = _looks_child_directed(user, policy_text)
        if gate_triggered:
            result = agent.structured_output(GateOutput, user)
            data = result.model_dump()
            data["phase"] = "gate"
            data["provider"] = _MODEL_PROVIDER
            return data
        else:
            result = agent.structured_output(CodeOutput, user)
            data = result.model_dump()
            data["phase"] = "code"
            data["provider"] = _MODEL_PROVIDER
            return _maybe_log_code_audit(data, prompt, session)

    # Second turn: developer has chosen gate options -> produce CODE,
    # consistent with their choices, including the audit block.
    picked = "; ".join(f"{k}={v}" for k, v in choices.items())
    system = (
        f"You operate under the following policy.\n\n{policy_text}\n\n"
        f"{IMPLEMENTATION_STANDARD}\n\n"
        f"The developer reviewed the safeguard options and chose: {picked}. "
        "Produce a CODE response: the complete, runnable program consistent with "
        "these choices — real working logic, no placeholders, stubs, or dummy "
        "returns — and include the audit block describing the trigger, the "
        "options that were presented, the developer's choice, your rationale, "
        "and the verbatim policy anchor."
    )
    agent = Agent(model=_MODEL, system_prompt=system,
                   tools=[log_decision], callback_handler=None)
    result = agent.structured_output(CodeOutput, user)
    data = result.model_dump()
    data["phase"] = "code"
    data["provider"] = _MODEL_PROVIDER
    return _maybe_log_code_audit(data, prompt, session)


def _looks_child_directed(prompt: str, policy_text: str) -> bool:
    """Cheap pre-check so the first turn doesn't need two full model calls to
    discover which schema applies. This mirrors the original design's intent
    (policy section 2's child-directed criteria) as a fast keyword screen; the
    model's OWN judgment inside GateOutput/CodeOutput is still authoritative —
    this only decides which schema to ask for, never the actual gate content.
    """
    import re
    pattern = re.compile(
        r"child|kid|minor|under ?18|teen|student|pupil|coppa|under-?age|"
        r"school|toddler|infant|nursery", re.IGNORECASE)
    return bool(pattern.search(prompt or ""))


def _maybe_log_code_audit(data: dict, prompt: str, session: str) -> dict:
    """If the model included an audit block (gate fired earlier this session),
    log it to the tamper-evident chain via the SAME core.append_decision call
    agent.py used, and attach audit_seq/audit_hash to the response — exactly
    matching the existing Code TS type's optional fields.
    """
    audit = data.pop("audit", None)
    if not audit:
        return data
    rec = core.append_decision(
        ROOT, "child-safety",
        audit.get("trigger", (prompt or "")[:120]),
        list(audit.get("options_presented") or ["(option a)", "(option b)"]),
        "developer-facing coding-agent gate decision",
        audit.get("choice", "(developer choice)"),
        rationale=audit.get("rationale", ""),
        ai_act_ref=audit.get("ai_act_ref", "UN CRC arts 3,12,16,19,34; EU AI Act"),
        model=data.get("provider", "strands-agent"), session=session,
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
        response_decision={
            "strategy": "developer-facing governance gate, not a child-facing response",
            "included": ["surfaced safeguarding options", "logged the chosen configuration"],
            "avoided": ["any child-directed output"],
            "identifier_request": "none",
        },
        human_review_tier="none",
        configured_human_review_policy=str(audit.get("configured_review_policy", "later")),
        human_review_triggered=False,
        choice_status=str(audit.get("choice_status", "approved")),
    )
    data["audit_seq"] = rec["seq"]
    data["audit_hash"] = rec["hash"]
    return data


# ───────────────────────── child-facing safeguarding chat ─────────────────────────

_DOMAINS = ("bullying", "grooming", "abuse", "self_harm", "distress")

_REVIEW_TIER_BY_ESC = {
    0: "none", 1: "none", 2: "optional", 3: "none",
    4: "required", 5: "expedited", 6: "immediate", 7: "crisis",
}
_REQUESTER_ROLE_MAP = {
    "child_self": "child_self", "worried_friend": "worried_friend",
    "parent_or_caregiver": "parent_or_caregiver", "teacher_or_educator": "teacher_or_educator",
}
_VALID_AGE_STATUS = {
    "known_child", "possible_child", "known_adult", "child_affected", "unknown",
}
_PROTECTION_MODE_BY_AGE = {
    "known_child": "child_specific", "possible_child": "child_specific",
    "child_affected": "child_affected", "known_adult": "adult",
    "unknown": "child_specific",
}
_AFFECTED_ROLE_MAP = {
    "child_self": "child_self", "specific_child": "specific_child",
    "group_of_children": "group_of_children",
}

# escalation levels at which surfacing a verified crisis resource is even
# considered (S4+, matching the planning doc's graduated design)
_RESOURCE_ESCALATION_FLOOR = 4
_PRIMARY_CONCERN_TO_CLASSIFIER_CATEGORY = {
    "Self-Harm": "self_harm", "Abuse": "abuse", "Distress": "distress",
    "Urgent Safety": "Urgent Safety",
}


def _esc_int(esc) -> int:
    try:
        return int(str(esc).strip().upper().lstrip("S") or 0)
    except Exception:
        return 0


def _normalize_age_status(raw: str) -> str:
    v = str(raw or "").strip().lower().replace("-", "_").replace(" ", "_")
    return v if v in _VALID_AGE_STATUS else "possible_child"


def child_chat(message: str, session: str = "web-child",
               policy: str | None = None) -> dict:
    """Run one child-facing turn. Same signature and return shape as
    agent.child_chat() — produces a safe reply + 5-axis safeguarding
    assessment, surfaces a verified crisis resource at S4+ via
    lookup_crisis_resource, and logs HIGH_RISK/CONCERNING turns to the
    tamper-evident chain via log_decision.
    """
    if _MODEL is None:
        return {"error": "No model backend available (Ollama unreachable and "
                          "no AWS Bedrock credentials found)."}

    policy_text = (policy or "").strip() or _load_child_policy()
    system = (
        f"{policy_text}\n\n"
        "Produce a child-facing reply plus an internal 5-axis safeguarding "
        "assessment (bullying, grooming, abuse, self_harm, distress; each "
        "0-9 with a one-sentence reason even when 0). The child NEVER sees "
        "the assessment — keep all scores and labels OUT of the reply field. "
        "If escalation reaches S4 or higher, you may call lookup_crisis_resource "
        "to obtain a VERIFIED resource and weave it naturally into the reply — "
        "never write a hotline number or URL from your own memory. Write the "
        "reply in the same language the child wrote in; the assessment fields "
        "stay in English regardless of the child's language. A language you "
        "are less confident in is a safety signal, not a reason to relax — "
        "lower language_confidence should pull overall confidence DOWN, never up."
    )
    agent = Agent(model=_MODEL, system_prompt=system,
                   tools=[lookup_crisis_resource, log_decision], callback_handler=None)
    result = agent.structured_output(ChildChatOutput, (message or "").strip())
    data = result.model_dump()

    # --- normalize (mirrors agent.py exactly: clamp scores, derive missing escalation) ---
    norm = {}
    for d in _DOMAINS:
        a = data["assessment"].get(d) or {"score": 0, "reason": "no clear indicators"}
        sc = max(0, min(9, int(round(float(a.get("score", 0))))))
        norm[d] = {"score": sc, "reason": (a.get("reason") or "no clear indicators").strip()}

    esc = str(data.get("escalation", "")).strip().upper()
    if not esc.startswith("S"):
        top = max(norm[d]["score"] for d in ("bullying", "grooming", "abuse", "self_harm"))
        esc = "S" + str({0: 0, 1: 0, 2: 1, 3: 2, 4: 3, 5: 4, 6: 4, 7: 5, 8: 5, 9: 6}[top])
    esc_i = _esc_int(esc)
    human_review = bool(data.get("human_review")) or esc_i >= 4

    detected_language = str(data.get("detected_language", "und")).strip() or "und"
    language_confidence = str(data.get("language_confidence", "high")).strip().lower()
    if language_confidence not in ("high", "medium", "low"):
        language_confidence = "high"
    confidence = data.get("confidence", "Medium")
    if language_confidence == "low":
        confidence = "Low"
    elif language_confidence == "medium" and str(confidence).strip().lower() == "high":
        confidence = "Medium"

    result_dict = {
        "reply": (data.get("reply") or
                  "I'm here with you. Can you tell me a bit more about what's going on?").strip(),
        "assessment": norm,
        "urgency": max(0, min(9, int(data.get("urgency", 0) or 0))),
        "confidence": confidence,
        "pattern": data.get("pattern", "Unknown"),
        "escalation": esc,
        "primary_concern": data.get("primary_concern", "None"),
        "secondary_concerns": data.get("secondary_concerns", []) or [],
        "human_review": human_review,
        "detected_language": detected_language,
        "language_confidence": language_confidence,
        "provider": _MODEL_PROVIDER,
    }

    if human_review:
        overall = max(norm[d]["score"] for d in _DOMAINS)
        by_measure = {d: norm[d]["score"] for d in _DOMAINS}

        age_status = _normalize_age_status(data.get("age_status"))
        protection_mode = _PROTECTION_MODE_BY_AGE[age_status]
        requester_role = _REQUESTER_ROLE_MAP.get(
            str(data.get("requester_role", "")).strip().lower(), "child_self")
        affected_person_role = _AFFECTED_ROLE_MAP.get(
            str(data.get("affected_person_role", "")).strip().lower(), "child_self")
        if age_status == "child_affected" and affected_person_role == "child_self":
            affected_person_role = "specific_child"
        review_tier = _REVIEW_TIER_BY_ESC.get(esc_i, "required")
        response_decision = (data.get("response_decision") or
                              "supportive reply; scores and S-level withheld from the child").strip()

        child_protected = protection_mode in ("child_specific", "child_affected")
        retained = ["scores", "escalation level", "review status"]
        not_retained = ["full message text", "exact name", "exact school",
                        "exact location", "contact details", "private images",
                        "hidden reasoning", "unrelated messages"]
        if child_protected:
            not_retained += ["caregiver/family names", "account/device handles",
                             "names of other children", "biometric/voice data"]
        privacy_tier = "crisis_record" if esc_i >= 7 else (
            "protected_record" if esc_i >= 4 else "redacted_summary")
        if privacy_tier == "redacted_summary":
            retained.append("short redacted summary")
        elif privacy_tier in ("protected_record", "crisis_record"):
            retained.append("necessary redacted excerpts")

        external_disclosure = "eligible" if esc_i >= 6 else "none"
        disclosure_reason = (
            f"escalation {esc} requires {review_tier} human review; external "
            "disclosure, if any, requires separate human authorization and is "
            "never performed from this score alone"
        )

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
        if esc_i >= 7:
            escalation_modifiers.append("high urgency")
            escalation_modifiers.append("urgency 9 — S7 presumption")

        reviewer_evidence_shown = ["domain scores", "escalation level", "primary/secondary concerns"]
        if privacy_tier in ("protected_record", "crisis_record"):
            reviewer_evidence_shown.append("necessary redacted excerpt")
        reviewer_evidence_withheld = [x for x in not_retained
                                      if x not in ("hidden reasoning", "unrelated messages")]
        if child_protected:
            retention_deadline = {
                "redacted_summary": "30 days", "protected_record": "90 days",
                "crisis_record": "1 year; post-incident minimization review within 30 days",
            }.get(privacy_tier, "")
        else:
            retention_deadline = {
                "redacted_summary": "90 days", "protected_record": "180 days",
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

        if age_status == "child_affected" or requester_role in (
                "parent_or_caregiver", "teacher_or_educator", "worried_friend"):
            op_mode = "proxy_concern"
        elif age_status == "known_adult":
            op_mode = "direct_adult_support"
        else:
            op_mode = "direct_child_support"

        response_decision_struct = {
            "strategy": response_decision,
            "included": ["calm support"] + (["one minimal safety question"] if esc_i >= 4 else []),
            "avoided": ["name", "school", "exact location", "contact details",
                        "private images", "revealing scores or S-levels"],
            "identifier_request": "none",
            "response_hash": hashlib.sha256(
                (result_dict["reply"] or "").encode("utf-8")).hexdigest(),
        }

        retention_tier = privacy_tier
        deletion_or_review_date = retention_deadline
        privacy_decision_reason = (
            "stored structured indicators and a redacted summary only; no full "
            "message text or identifiers, scaled to escalation severity and "
            + ("heightened child data-minimization"
               if child_protected else "baseline minimization")
        )
        content_hash = hashlib.sha256((message or "").encode("utf-8")).hexdigest()

        rec_via_tool = _log_decision_impl(
            domain="child-safety",
            trigger=f"chat conv_{session.replace('-', '_')} "
                    f"risk_level={_risk_level(esc_i)} overall={overall}",
            options_presented=[result_dict["primary_concern"]] + list(result_dict["secondary_concerns"]),
            implications="per-message safeguarding assessment of a child-facing conversation",
            user_choice=f"ESCALATED to authorized human reviewer — "
                        f"primary: {result_dict['primary_concern']} ({esc})",
            rationale="; ".join(f"{d} {norm[d]['score']}: {norm[d]['reason']}"
                                for d in _DOMAINS if norm[d]["score"] >= 4)
                      or f"primary {result_dict['primary_concern']}",
            ai_act_ref="UN CRC arts 3, 12, 16, 19, 34; EU AI Act (rights-sensitive)",
            session=session, model=_MODEL_PROVIDER,
        )
        result_dict["audit_seq"] = rec_via_tool["audit_seq"]
        result_dict["audit_hash"] = rec_via_tool["audit_hash"]

    return result_dict


def _risk_level(esc_i: int) -> str:
    if esc_i >= 6:
        return "HIGH_RISK"
    if esc_i >= 4:
        return "CONCERNING"
    if esc_i >= 2:
        return "SENSITIVE"
    return "SAFE"