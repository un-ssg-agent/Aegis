"""Pure-stdlib core of the compliance audit trail.

No third-party dependencies, so this module runs and self-tests with stock
python3. `server.py` wraps these functions as MCP tools; `verify` and
`report` also run from the command line for the live demo.

Design rule (the whole point of this project):
    The LLM NEVER computes a hash and NEVER writes a file. It only decides
    and calls log_decision(). This module does the deterministic work — so
    the audit trail cannot be faked by a chatty model that "writes" a log
    line with a made-up hash.

Tamper-evidence:
    Each record stores the SHA-256 hash of the PREVIOUS record (`prev_hash`)
    plus its own hash over the canonical form of all other fields. Altering,
    inserting, removing, or reordering any record breaks the chain, which
    verify_chain() detects and localises.
"""
from __future__ import annotations

import ast
import hashlib
import json
import os
import re
import sys
from datetime import datetime, timezone

GENESIS = "0" * 64


def _log_file(root: str) -> str:
    return os.path.join(root, "audit-trail", "decisions.jsonl")


def _canonical(record: dict) -> str:
    """Deterministic pre-image: every field EXCEPT the record's own `hash`,
    key-sorted, no incidental whitespace, UTF-8 preserved. Logger and verifier
    MUST use this identical function or hashes will never match."""
    payload = {k: v for k, v in record.items() if k != "hash"}
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def _read_all(root: str) -> list[dict]:
    path = _log_file(root)
    out: list[dict] = []
    if os.path.exists(path):
        with open(path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    out.append(json.loads(line))
    return out


_VALID_REQUESTER_ROLES = {
    "child_self", "adult_self", "worried_friend", "parent_or_caregiver",
    "teacher_or_educator", "developer", "reviewer", "unknown",
}
_VALID_AFFECTED_ROLES = {
    "child_self", "adult_self", "specific_child", "specific_adult",
    "group_of_children", "hypothetical", "platform_users", "unknown",
}
_VALID_OPERATING_MODES = {
    "direct_support", "proxy_concern", "developer_embedding",
    "reviewer_support", "governance_review",
}
_VALID_PROTECTION_MODES = {"baseline", "child_specific", "adult", "child_affected"}
_VALID_AGE_STATUS = {
    "known_child", "possible_child", "known_adult", "child_affected", "unknown",
}
_VALID_AUTHORITY_CATEGORIES = {
    "no_direct_authority", "caregiver", "institutional", "developer",
    "reviewer", "governance",
}
_VALID_PRIVACY_TIERS = {
    "no_record", "structured_indicator", "redacted_summary",
    "protected_record", "crisis_record",
}
_VALID_DISCLOSURE = {"none", "eligible", "performed"}
_VALID_HUMAN_REVIEW_TIERS = {
    "none", "optional", "required", "expedited", "immediate", "crisis",
}
_VALID_AUTHORIZATION_STATUS = {
    "not_applicable", "pending", "authorized", "denied",
}

# Deterministic policy-check IDs. Each is evaluated in code from the record's
# own fields below — never asked of the model — so a "pass" can never be an
# LLM's unverifiable self-assessment. Add new IDs here; never repurpose one.
_POLICY_CHECK_IDS = (
    "CRC16",                       # UN CRC art.16 — child's right to privacy
    "GC25-Privacy",                # UNCRC General Comment 25 — privacy by design
    "UNICEF-PDP-Minimization",     # UNICEF policy guidance — data minimization
    "UNICEF-AI-Privacy",           # UNICEF AI/children guidance — privacy safeguards
    "UNESCO-Proportionality",      # UNESCO AI ethics — proportionate/least-intrusive response
    "EUAI-Governance-Implementation",  # EU AI Act — human oversight implemented, not just stated
)


def _evaluate_policy_checks(
    retained_data: list,
    not_retained_data: list,
    external_disclosure: str,
    human_review_tier: str,
    privacy_tier: str,
) -> dict:
    """Deterministically score each policy-check ID as pass/fail/NA from the
    record's own privacy fields. No model input. Conservative by design:
    anything ambiguous fails rather than silently passing."""
    retained = [str(x).lower() for x in (retained_data or [])]
    not_retained = [str(x).lower() for x in (not_retained_data or [])]
    full_convo_retained = any("full conversation" in x or "full chat" in x for x in retained)
    excessive_pii = any(
        any(term in x for term in ("exact location", "exact address", "school name",
                                    "phone number", "private image", "full name"))
        for x in retained
    )
    auto_disclosure_from_score_alone = (
        external_disclosure == "performed" and human_review_tier in ("none", "optional")
    )

    checks = {
        # CRC16: privacy preserved unless full-conversation retention happened.
        "CRC16": "fail" if full_convo_retained else "pass",
        # GC25-Privacy: privacy-by-design unless excessive identifiers were kept.
        "GC25-Privacy": "fail" if excessive_pii else "pass",
        # UNICEF-PDP-Minimization: only applies once a privacy tier is set.
        "UNICEF-PDP-Minimization": (
            "na" if privacy_tier in ("", "no_record")
            else "fail" if (full_convo_retained or excessive_pii) else "pass"
        ),
        # UNICEF-AI-Privacy: no automatic external disclosure from a score alone.
        "UNICEF-AI-Privacy": "fail" if auto_disclosure_from_score_alone else "pass",
        # UNESCO-Proportionality: least-intrusive tier was actually used, not crisis-by-default.
        "UNESCO-Proportionality": (
            "fail" if (privacy_tier == "crisis_record" and human_review_tier not in ("immediate", "crisis"))
            else "pass"
        ),
        # EUAI-Governance-Implementation: human oversight was real, not symbolic,
        # whenever a review tier above "none" was set.
        "EUAI-Governance-Implementation": (
            "na" if human_review_tier == "none"
            else "fail" if auto_disclosure_from_score_alone else "pass"
        ),
    }
    # guarantee every declared ID is present even if logic above didn't set it
    return {cid: checks.get(cid, "na") for cid in _POLICY_CHECK_IDS}


def append_decision(
    root: str,
    domain: str,
    trigger: str,
    options: list,
    implications: str,
    user_choice: str,
    rationale: str = "",
    test_results: str = "",
    ai_act_ref: str = "",
    model: str = "",
    session: str = "",
    *,
    # --- role-aware fields (all optional; "unknown"/safe default if omitted) ---
    requester_role: str = "unknown",
    affected_person_role: str = "unknown",
    operating_mode: str = "governance_review",
    live_case: bool = False,
    protection_mode: str = "baseline",
    authority_category: str = "no_direct_authority",
    age_status: str = "unknown",
    # --- privacy decision fields ---
    privacy_tier: str = "no_record",
    retained_data: list | None = None,
    not_retained_data: list | None = None,
    external_disclosure: str = "none",
    disclosure_reason: str = "",
    # --- response + review fields ---
    response_decision: str = "",
    human_review_tier: str = "none",
    # --- S3+ tiered transparency: why key decisions were/weren't made ---
    review_trigger_reason: str = "",
    retention_decision_reason: str = "",
    clarification_decision_reason: str = "",
    identifier_avoidance_reason: str = "",
    policy_check_reason: str = "",
    # --- S4+ tiered transparency: reviewer evidence + concerns + deadlines ---
    reviewer_evidence_shown: list | None = None,
    reviewer_evidence_withheld: list | None = None,
    retention_deadline: str = "",
    primary_concern: str = "",
    secondary_concerns: list | None = None,
    escalation_modifiers: list | None = None,
    # --- S6/S7 / external-disclosure tiered transparency ---
    privacy_limitation_reason: str = "",
    disclosure_necessity_reason: str = "",
    minimum_info_shared: list | None = None,
    human_authorization_status: str = "not_applicable",
    post_incident_review_deadline: str = "",
) -> dict:
    """Append one tamper-evident decision record and return it.

    New keyword-only fields are additive and all default to safe/neutral
    values, so every existing call site (server.py, child_classifier/audit.py,
    monitor/app.py) keeps working unchanged and old records keep verifying —
    each record is hashed over only the fields it actually has.
    """
    def _check(value: str, allowed: set, field: str) -> str:
        if value not in allowed:
            raise ValueError(f"{field}={value!r} not in {sorted(allowed)}")
        return value

    requester_role = _check(requester_role, _VALID_REQUESTER_ROLES, "requester_role")
    affected_person_role = _check(affected_person_role, _VALID_AFFECTED_ROLES, "affected_person_role")
    operating_mode = _check(operating_mode, _VALID_OPERATING_MODES, "operating_mode")
    protection_mode = _check(protection_mode, _VALID_PROTECTION_MODES, "protection_mode")
    age_status = _check(age_status, _VALID_AGE_STATUS, "age_status")
    authority_category = _check(authority_category, _VALID_AUTHORITY_CATEGORIES, "authority_category")
    privacy_tier = _check(privacy_tier, _VALID_PRIVACY_TIERS, "privacy_tier")
    external_disclosure = _check(external_disclosure, _VALID_DISCLOSURE, "external_disclosure")
    human_review_tier = _check(human_review_tier, _VALID_HUMAN_REVIEW_TIERS, "human_review_tier")
    human_authorization_status = _check(
        human_authorization_status, _VALID_AUTHORIZATION_STATUS, "human_authorization_status")

    retained_data = list(retained_data or [])
    not_retained_data = list(not_retained_data or [])
    reviewer_evidence_shown = list(reviewer_evidence_shown or [])
    reviewer_evidence_withheld = list(reviewer_evidence_withheld or [])
    secondary_concerns = list(secondary_concerns or [])
    escalation_modifiers = list(escalation_modifiers or [])
    minimum_info_shared = list(minimum_info_shared or [])
    source_policy_checks = _evaluate_policy_checks(
        retained_data, not_retained_data, external_disclosure,
        human_review_tier, privacy_tier,
    )

    path = _log_file(root)
    entries = _read_all(root)
    prev_hash = entries[-1]["hash"] if entries else GENESIS
    seq = entries[-1]["seq"] + 1 if entries else 0

    record = {
        "seq": seq,
        "ts": datetime.now(timezone.utc).isoformat(),
        "domain": domain,                 # child-safety | privacy | security | fairness | ...
        "trigger": trigger,               # why the gate/escalation fired
        "options_presented": options,     # >= 2 alternatives shown
        "implications": implications,     # the tradeoff / what each option costs
        "user_choice": user_choice,       # the human (or system) decision
        "rationale": rationale,           # why it was chosen
        "test_results": test_results,     # any test/scan output, if available
        "ai_act_ref": ai_act_ref,         # verbatim legal anchor (not LLM-recalled)
        "model": model,                   # which model was driving
        "session": session,               # session id
        # --- role-aware fields ---
        "requester_role": requester_role,
        "affected_person_role": affected_person_role,
        "operating_mode": operating_mode,
        "live_case": bool(live_case),
        "protection_mode": protection_mode,
        "authority_category": authority_category,
        "age_status": age_status,
        # --- privacy decision fields ---
        "privacy_tier": privacy_tier,
        "retained_data": retained_data,
        "not_retained_data": not_retained_data,
        "external_disclosure": external_disclosure,
        "disclosure_reason": disclosure_reason,
        # --- response + review fields ---
        "response_decision": response_decision,
        "human_review_tier": human_review_tier,
        # --- S3+ tiered transparency ---
        "review_trigger_reason": review_trigger_reason,
        "retention_decision_reason": retention_decision_reason,
        "clarification_decision_reason": clarification_decision_reason,
        "identifier_avoidance_reason": identifier_avoidance_reason,
        "policy_check_reason": policy_check_reason,
        # --- S4+ tiered transparency ---
        "reviewer_evidence_shown": reviewer_evidence_shown,
        "reviewer_evidence_withheld": reviewer_evidence_withheld,
        "retention_deadline": retention_deadline,
        "primary_concern": primary_concern,
        "secondary_concerns": secondary_concerns,
        "escalation_modifiers": escalation_modifiers,
        # --- S6/S7 / external-disclosure tiered transparency ---
        "privacy_limitation_reason": privacy_limitation_reason,
        "disclosure_necessity_reason": disclosure_necessity_reason,
        "minimum_info_shared": minimum_info_shared,
        "human_authorization_status": human_authorization_status,
        "post_incident_review_deadline": post_incident_review_deadline,
        # --- deterministic policy verdicts (computed above, never model input) ---
        "source_policy_checks": source_policy_checks,
        "prev_hash": prev_hash,           # chain link
    }
    record["hash"] = hashlib.sha256(_canonical(record).encode("utf-8")).hexdigest()

    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "a", encoding="utf-8") as f:
        f.write(json.dumps(record, ensure_ascii=False) + "\n")

    # Autosave a readable projection next to the raw chain. Best-effort: the
    # .jsonl is the authoritative record, so a narrative-write failure must
    # never break the append above.
    try:
        narrative_path = os.path.join(root, "audit-trail", "narrative.md")
        with open(narrative_path, "w", encoding="utf-8") as f:
            f.write(render_narrative(root))
    except Exception:
        pass

    return record


def verify_chain(root: str):
    """Return (ok: bool, message: str, count: int, head_hash: str).
    Walks the whole file, recomputing every hash and checking every link."""
    entries = _read_all(root)
    if not entries:
        return True, "Empty: no audit trail yet.", 0, GENESIS
    prev = GENESIS
    for i, rec in enumerate(entries):
        recomputed = hashlib.sha256(_canonical(rec).encode("utf-8")).hexdigest()
        if rec.get("prev_hash") != prev:
            return (False,
                    f"BROKEN at seq {rec.get('seq', i)}: prev_hash mismatch "
                    f"(an entry was inserted, removed, or reordered).", i, prev)
        if rec.get("hash") != recomputed:
            return (False,
                    f"BROKEN at seq {rec.get('seq', i)}: content was altered "
                    f"after it was logged.", i, prev)
        prev = rec["hash"]
    return True, f"OK: {len(entries)} entries, chain intact.", len(entries), prev


def render_model_card(root: str) -> str:
    """Deterministically render the audit trail into an EU AI Act-style
    Model Card. No LLM call: the report is a faithful projection of the
    chain, itself anchored to the verified head hash."""
    entries = _read_all(root)
    ok, msg, n, head = verify_chain(root)
    now = datetime.now(timezone.utc).isoformat()
    chain_line = ("✅ INTACT" if ok else "❌ " + msg)

    by_domain: dict[str, int] = {}
    for e in entries:
        by_domain[e["domain"]] = by_domain.get(e["domain"], 0) + 1

    L: list[str] = []
    L.append("# Compliance Model Card")
    L.append("")
    L.append("_Auto-generated from the tamper-evident audit trail. "
             "Every claim below is traceable to `audit-trail/decisions.jsonl`._")
    L.append("")
    L.append("## 1. System identification")
    L.append(f"- Generated at: `{now}`")
    L.append(f"- Audit chain status: **{chain_line}**")
    L.append(f"- Chain head hash: `{head}`")
    L.append(f"- Decisions recorded: **{n}**  "
             + " ".join(f"({k}: {v})" for k, v in sorted(by_domain.items())))
    L.append("")
    L.append("## 2. Purpose & scope")
    L.append("This record documents the fairness / privacy / cybersecurity "
             "tensions surfaced to the developer during AI-assisted code "
             "generation, and the human decisions made at each one. It does "
             "**not** certify that the resulting system is fair or secure — "
             "it certifies what was flagged, what choices were offered, and "
             "what the human decided.")
    L.append("")
    L.append("## 3. Decisions log (human oversight)")
    if not entries:
        L.append("_No decisions recorded._")
    else:
        L.append("| seq | time (UTC) | domain | trigger | choice | legal anchor |")
        L.append("|----:|------------|--------|---------|--------|--------------|")
        for e in entries:
            L.append(f"| {e['seq']} | {e['ts']} | {e['domain']} | "
                     f"{e['trigger']} | **{e['user_choice']}** | {e.get('ai_act_ref','')} |")
        L.append("")
        L.append("### Decision details")
        for e in entries:
            L.append(f"#### seq {e['seq']} — {e['domain']}: {e['trigger']}")
            L.append(f"- Options presented: {e['options_presented']}")
            L.append(f"- Implications / tradeoff: {e['implications']}")
            L.append(f"- **Developer chose:** {e['user_choice']}")
            if e.get("rationale"):
                L.append(f"- Rationale: {e['rationale']}")
            if e.get("test_results"):
                L.append(f"- Test results: {e['test_results']}")
            if e.get("ai_act_ref"):
                L.append(f"- Legal anchor (verbatim): {e['ai_act_ref']}")
            L.append(f"- Record hash: `{e['hash']}`")
            L.append("")
    cs = [e for e in entries if e.get("domain") == "child-safety"]
    if cs:
        L.append("## 3b. Child-safety safeguards (UN CRC / UNICEF)")
        L.append("Explicit safeguarding choices recorded for child-facing systems:")
        for e in cs:
            L.append(f"- **{e['trigger']}**")
            L.append(f"  - choice (escalation / retention / evaluation): {e['user_choice']}")
            if e.get("ai_act_ref"):
                L.append(f"  - basis: {e['ai_act_ref']}")
        L.append("")
    L.append("## 4. Known limitations")
    L.append("- The compliance gate is **prompt-enforced**: the chain proves "
             "that *what was logged* was not altered, but cannot prove that "
             "*everything that should have been logged* was logged. A model "
             "that skips the gate leaves no record — by design this tool "
             "audits disclosed decisions, like any audit.")
    L.append("- Detection is keyword/pattern based; concealed intent "
             "(unnamed columns, no domain words) will not trigger.")
    L.append("- This tool makes no fairness judgement; fairness outcomes are "
             "measurable only at runtime on real data.")
    L.append("")
    L.append("## 5. Traceability")
    L.append("- Raw evidence: `audit-trail/decisions.jsonl` (append-only, "
             "SHA-256 hash chain).")
    L.append("- Verify independently: "
             "`python3 mcp-servers/compliance-auditor/core.py verify`")
    L.append("")
    L.append("<!-- Optional: an LLM-written narrative MAY be appended below, "
             "clearly labelled as non-authoritative. The verifiable facts are "
             "those above, anchored to the chain head hash. -->")
    L.append("")
    return "\n".join(L)

# --- narrative helpers -------------------------------------------------------
# These turn the structured record fields into readable English. They are pure
# string/dict transforms with no LLM call, so the narrative below stays a
# faithful, reproducible projection of the chain rather than an invented story.

_MEASURE_NAMES = {
    "pii_exposure": "PII exposure",
    "self_harm": "self-harm",
    "sexual_exploitation": "sexual exploitation",
}
_RISK_LEVELS = {
    "HIGH_RISK": "high-risk",
    "CONCERNING": "concerning",
    "SENSITIVE": "sensitive",
    "SAFE": "safe",
}


def _measure_name(key: str) -> str:
    return _MEASURE_NAMES.get(key, key.replace("_", " "))


def _join(parts: list[str]) -> str:
    """Oxford-comma join: ['a'] -> 'a', ['a','b'] -> 'a and b',
    ['a','b','c'] -> 'a, b, and c'."""
    parts = [p for p in parts if p]
    if not parts:
        return ""
    if len(parts) == 1:
        return parts[0]
    if len(parts) == 2:
        return f"{parts[0]} and {parts[1]}"
    return ", ".join(parts[:-1]) + ", and " + parts[-1]


def _loose_dict(text) -> dict:
    """Best-effort extraction of a dict from a value that may be a real dict,
    a JSON string, a Python-repr string, or prose with a `{...}` blob inside."""
    if isinstance(text, dict):
        return text
    if not isinstance(text, str):
        return {}
    for attempt in (text, "{" + text.split("{", 1)[-1].rsplit("}", 1)[0] + "}"
                    if "{" in text and "}" in text else text):
        for parser in (json.loads, ast.literal_eval):
            try:
                val = parser(attempt)
                if isinstance(val, dict):
                    return val
            except (ValueError, SyntaxError):
                continue
    return {}


def _describe_measures(scores: dict) -> str:
    """Turn {'self_harm': 9.6, 'grooming': 0.0, ...} into prose, auto-detecting
    a 0-10 vs 0-1 scale and folding the long tail of zeros into one clause."""
    numeric = {k: v for k, v in scores.items() if isinstance(v, (int, float))}
    if not numeric:
        return ""
    scale10 = any(v > 1.0 for v in numeric.values())
    fmt = (lambda v: f"{v:g}/10") if scale10 else (lambda v: f"{v:.2f}")
    nonzero = sorted([(k, v) for k, v in numeric.items() if v > 0],
                     key=lambda kv: -kv[1])
    zeros = [k for k, v in numeric.items() if v == 0]
    if not nonzero:
        return "every category came back clean (all at zero)"
    lead = _join([f"{_measure_name(k)} at {fmt(v)}" for k, v in nonzero])
    if not zeros:
        return lead
    if len(zeros) <= 2:
        return f"{lead}, while {_join([_measure_name(k) for k in zeros])} stayed at zero"
    return f"{lead}, while every other category stayed at zero"


def _parse_votes(rationale: str):
    """['deepseek-chat', '0.95'], ... from 'deepseek:deepseek-chat=0.95; ...'."""
    return re.findall(r"(?:[\w.\-]+:)?([\w.\-]+)=([0-9.]+)", rationale or "")


def _parse_signals(test_results) -> list[str]:
    data = _loose_dict(test_results)
    out = []
    for sig in data.get("signals", []) or []:
        if isinstance(sig, dict) and sig.get("description"):
            out.append(sig["description"])
    return out


def _render_options(opts) -> str:
    rendered = []
    for o in opts or []:
        if isinstance(o, dict) and "axis" in o:
            choices = " / ".join(str(c) for c in o.get("options", []))
            rendered.append(f"{o['axis']} ({choices})")
        else:
            rendered.append(str(o))
    return "; ".join(rendered)


_ROLE_LABELS = {
    "child_self": "the child themself",
    "adult_self": "the adult themself",
    "worried_friend": "a worried friend",
    "parent_or_caregiver": "a parent or caregiver",
    "teacher_or_educator": "a teacher or educator",
    "developer": "a developer/operator",
    "reviewer": "a reviewer",
    "unknown": "an unidentified requester",
    "specific_child": "a specific identified child",
    "specific_adult": "a specific identified adult",
    "group_of_children": "a group of children",
    "hypothetical": "a hypothetical/future case",
    "platform_users": "platform users in general",
}
_PROTECTION_LABELS = {
    "baseline": "baseline safeguarding",
    "child_specific": "child-specific safeguarding",
    "adult": "adult-appropriate safeguarding",
    "child_affected": "child-affected safeguarding (adult requester, child impact)",
}
_AGE_STATUS_LABELS = {
    "known_child": "a known child",
    "possible_child": "a possible child (age unclear — treated as a child)",
    "known_adult": "a known adult",
    "child_affected": "an adult/unknown requester with a specific child affected",
    "unknown": "an unknown age status (treated conservatively)",
}
_PRIVACY_TIER_LABELS = {
    "no_record": "no record was created",
    "structured_indicator": "only a structured indicator was recorded",
    "redacted_summary": "a redacted summary was recorded",
    "protected_record": "a protected record was created",
    "crisis_record": "a crisis record was created",
}
_REVIEW_TIER_LABELS = {
    "none": "no human review",
    "optional": "optional human review",
    "required": "required human review",
    "expedited": "expedited human review",
    "immediate": "immediate human review",
    "crisis": "crisis-protocol review",
}


def _policy_check_sentence(checks: dict) -> str:
    if not checks:
        return ""
    order = [c for c in _POLICY_CHECK_IDS if c in checks] or list(checks.keys())
    parts = [f"{cid} = {checks[cid]}" for cid in order]
    return "Source-policy checks applied: " + "; ".join(parts) + "."


def _privacy_sentence(e: dict) -> str:
    tier = e.get("privacy_tier")
    retained = e.get("retained_data") or []
    not_retained = e.get("not_retained_data") or []
    disclosure = e.get("external_disclosure")
    reason = e.get("disclosure_reason") or ""
    if not tier and not retained and not not_retained and not disclosure:
        return ""
    bits = []
    if tier:
        bits.append(_PRIVACY_TIER_LABELS.get(tier, tier.replace("_", " ")))
    if retained:
        bits.append(f"retained: {_join(retained)}")
    if not_retained:
        bits.append(f"not retained: {_join(not_retained)}")
    s = "Privacy decision: " + "; ".join(bits) + "." if bits else ""
    if disclosure:
        disc_label = {"none": "none", "eligible": "eligible but not performed",
                      "performed": "performed"}.get(disclosure, disclosure)
        s += f" External disclosure: {disc_label}."
        if reason:
            s += f" Reason: {reason.rstrip('.')}."
    return s


# --- escalation level extraction (for the length-budget rule) ---------------

def _escalation_level(e: dict) -> int:
    """Best-effort S-level (0-7) for an entry, used only to size the narrative.
    Tries, in order: an explicit 'S<n>' in user_choice/trigger; the legacy
    risk_level=<LEVEL> convention used by the original classifier/panel
    entries (SAFE/SENSITIVE/CONCERNING/HIGH_RISK); human_review_tier; an
    escalated/ESCALATED choice with no other signal; else 0."""
    for field in ("user_choice", "trigger", "rationale", "implications"):
        m = re.search(r"\bS([0-7])\b", str(e.get(field, "")))
        if m:
            return int(m.group(1))
    m = re.search(r"risk_level=(\w+)", str(e.get("trigger", "")))
    if m:
        legacy_floor = {"SAFE": 0, "SENSITIVE": 2, "CONCERNING": 4, "HIGH_RISK": 6}
        if m.group(1) in legacy_floor:
            return legacy_floor[m.group(1)]
    tier_floor = {
        "none": 0, "optional": 2, "required": 4,
        "expedited": 5, "immediate": 6, "crisis": 7,
    }
    if e.get("human_review_tier"):
        return tier_floor.get(e["human_review_tier"], 0)
    if "escalat" in str(e.get("user_choice", "")).lower():
        return 4  # an unscored but explicitly escalated decision: treat as S4 floor
    return 0


def _has_disclosure_or_incident(e: dict) -> bool:
    return (e.get("external_disclosure") in ("eligible", "performed")
            or e.get("domain") == "human-review"
            or bool(e.get("post_incident_review_deadline")))


def _detail_level(e: dict) -> str:
    """Length-budget rule: below S3 -> 'row' (short structured line, 5-12
    lines worth of content compressed to ~1-2 sentences); S3-S4 -> 'summary'
    (1-2 short paragraphs, current default behaviour); S5+ or disclosure/
    override/incident -> 'expanded' (adds the S4+ and S6+/disclosure
    tiered-transparency sentences)."""
    esc = _escalation_level(e)
    if esc >= 5 or _has_disclosure_or_incident(e):
        return "expanded"
    if esc >= 3:
        return "summary"
    return "row"


def _cap_first(s: str) -> str:
    """Capitalize only the first character, unlike str.capitalize() which
    also lowercases the rest of the string (mangling acronyms like S4/S6)."""
    return s[:1].upper() + s[1:] if s else s


def _s3_sentence(e: dict) -> str:
    """S3+: why review/retention/clarification/identifier/policy decisions
    were made — only rendered once escalation reaches S3."""
    bits = []
    if e.get("review_trigger_reason"):
        bits.append(f"review was triggered because {e['review_trigger_reason'].rstrip('.')}")
    if e.get("retention_decision_reason"):
        bits.append(f"retention was set because {e['retention_decision_reason'].rstrip('.')}")
    if e.get("clarification_decision_reason"):
        bits.append(f"the response asked/avoided clarification because "
                     f"{e['clarification_decision_reason'].rstrip('.')}")
    if e.get("identifier_avoidance_reason"):
        bits.append(f"identifiers were avoided because {e['identifier_avoidance_reason'].rstrip('.')}")
    if e.get("policy_check_reason"):
        bits.append(f"policy checks {e['policy_check_reason'].rstrip('.')}")
    if not bits:
        return ""
    return " " + _cap_first(_join(bits)) + "."


def _s4_sentence(e: dict) -> str:
    """S4+: reviewer evidence, retention deadline, concern routing, modifiers."""
    bits = []
    shown = e.get("reviewer_evidence_shown") or []
    withheld = e.get("reviewer_evidence_withheld") or []
    if shown or withheld:
        s = ""
        if shown:
            s += f"reviewer evidence shown: {_join(shown)}"
        if withheld:
            s += (("; " if s else "") + f"withheld: {_join(withheld)}")
        bits.append(s)
    if e.get("retention_deadline"):
        bits.append(f"retention deadline: {e['retention_deadline']}")
    primary = e.get("primary_concern")
    secondary = e.get("secondary_concerns") or []
    if primary:
        s = f"primary concern: {primary}"
        if secondary:
            s += f"; secondary concerns: {_join(secondary)}"
        bits.append(s)
    modifiers = e.get("escalation_modifiers") or []
    if modifiers:
        bits.append(f"escalation modifiers applied: {_join(modifiers)}")
    if not bits:
        return ""
    return " " + _cap_first("; ".join(bits)) + "."


def _s6_sentence(e: dict) -> str:
    """S6/S7 or external-disclosure: why privacy was limited/disclosure was
    necessary or blocked, minimum info shared, human authorization, and the
    post-incident minimization review deadline."""
    bits = []
    if e.get("privacy_limitation_reason"):
        bits.append(f"privacy was limited because {e['privacy_limitation_reason'].rstrip('.')}")
    if e.get("disclosure_necessity_reason"):
        bits.append(f"disclosure was {e.get('external_disclosure', 'assessed')} because "
                     f"{e['disclosure_necessity_reason'].rstrip('.')}")
    info = e.get("minimum_info_shared") or []
    if info:
        bits.append(f"minimum information shared: {_join(info)}")
    auth = e.get("human_authorization_status")
    if auth and auth != "not_applicable":
        auth_lbl = {"pending": "pending", "authorized": "authorized",
                    "denied": "denied"}.get(auth, auth)
        bits.append(f"human authorization: {auth_lbl}")
    if e.get("post_incident_review_deadline"):
        bits.append(f"post-incident minimization review due: {e['post_incident_review_deadline']}")
    if not bits:
        return ""
    return " " + _cap_first(_join(bits)) + "."


def _short_row(e: dict, when: str, ctx: str) -> str:
    """The 'row' detail level: a compact structured line for entries below
    S3 with no disclosure/incident — the per-message minimum the policy
    requires (who asked, who is affected, was it live, escalation, choice),
    without the full narrative paragraph treatment."""
    seq = e.get("seq")
    domain = e.get("domain", "")
    choice = e.get("user_choice", "") or "(none)"
    esc = e.get("human_review_tier", "none")
    bits = [f"entry #{seq}", f"{when}", f"domain: {domain}"]
    if e.get("trigger"):
        bits.append(f"trigger: {e['trigger'][:80].rstrip('.')}")
    bits.append(f"choice: {choice}")
    bits.append(f"human review tier: {_REVIEW_TIER_LABELS.get(esc, esc)}")
    line = " · ".join(bits) + "." + ctx
    if e.get("ai_act_ref"):
        line += f" Legal anchor: {e['ai_act_ref']}."
    line += f" Record sealed under hash: `{e['hash']}`"
    return line


def render_narrative(root: str) -> str:
    """Deterministically render the audit trail as a human-readable decision
    summary — one entry per record, generated from sealed audit fields. This
    is NOT hidden chain-of-thought: it summarizes recorded decision factors
    (who asked, who is affected, what was chosen, what was retained, which
    policy checks passed) using fixed string templates and no LLM call, so
    every sentence traces back to a field that was written to the chain at
    decision time. Like render_model_card(), it is a faithful, reproducible
    projection of audit-trail/decisions.jsonl, anchored to the verified head
    hash.
    """
    entries = _read_all(root)
    ok, msg, n, head = verify_chain(root)

    def _when(ts: str) -> str:
        try:
            return datetime.fromisoformat(ts).strftime("%-d %B %Y at %H:%M UTC")
        except (ValueError, TypeError):
            return ts

    L: list[str] = []
    L.append("# Compliance audit trail — decision summary")
    L.append("")
    status = "intact and verified" if ok else f"BROKEN — {msg}"
    L.append(f"Audit chain head: `{head}`")
    L.append("")
    L.append(
        "This report is a human-readable summary generated deterministically "
        "from `audit-trail/decisions.jsonl`. It summarizes sealed decision "
        "fields, written as a deterministic decision summary generated from "
        "sealed audit fields — not hidden chain-of-thought. The hash chain is "
        f"currently **{status}**, covering {n} recorded decision event(s). "
        "Each paragraph ends with the hash of the record it summarizes."
    )
    L.append("")
    if not entries:
        L.append("_No decisions have been recorded yet._")
        return "\n".join(L) + "\n"

    for e in entries:
        when = _when(e.get("ts", ""))
        seq = e.get("seq")
        trigger = e.get("trigger", "")
        choice = e.get("user_choice", "")
        rationale = e.get("rationale", "") or ""
        anchor = e.get("ai_act_ref", "") or ""
        domain = e.get("domain", "")
        escalated = "escalat" in choice.lower()

        # role/case context line — only when the record actually carries these
        # fields (new schema); older entries render exactly as before.
        requester = e.get("requester_role")
        affected = e.get("affected_person_role")
        protection = e.get("protection_mode")
        age_status = e.get("age_status")
        live_case = e.get("live_case")
        ctx = ""
        if requester or affected or protection is not None:
            req_lbl = _ROLE_LABELS.get(requester, requester or "an unidentified requester")
            aff_lbl = _ROLE_LABELS.get(affected, affected or "an unspecified affected party")
            prot_lbl = _PROTECTION_LABELS.get(protection, (protection or "baseline").replace("_", " "))
            live_lbl = "Yes" if live_case else "No"
            ctx = (f" Requester role: {req_lbl}. Affected person role: {aff_lbl}. "
                   f"Protection mode: {prot_lbl}. Live safeguarding case: {live_lbl}.")
            if age_status and age_status != "unknown":
                ctx += f" Age status: {_AGE_STATUS_LABELS.get(age_status, age_status)}."
            if live_case is False:
                ctx += (" Because this was not a live safeguarding case, the system "
                        "did not create a child case record or trigger safeguarding "
                        "escalation on this entry.")

        # length-budget rule: entries below S3 with no disclosure/incident get
        # a compact structured row instead of the full narrative paragraph.
        level = _detail_level(e)
        if level == "row":
            L.append(_short_row(e, when, ctx))
            L.append("")
            continue

        # --- shape 1: a human reviewer closed an escalation -------------------
        if domain == "human-review":
            m = re.match(r"REVIEWED by (.+?):\s*(.+)", choice)
            who = m.group(1) if m else "a reviewer"
            disp = (m.group(2) if m else choice).replace("_", " ")
            target = re.search(r"(conv_\w+|test_\w+)", trigger)
            tgt = f"conversation {target.group(1)}" if target else "the escalation"
            s = (f"On {when} the loop closed on {tgt}: {who} reviewed it and "
                 f"marked it **{disp}** (entry #{seq}).")
            if rationale:
                s += f" Their note: {rationale.rstrip('.')}."
            s += (" This is the human-in-the-loop step doing its job — the "
                  "record shows a person made the call, not the system.")

        # --- shape 2: a single conversation scored by the classifier ----------
        elif "risk_level=" in trigger:
            cid = re.search(r"(conv_\w+|test_\w+)", trigger)
            cid = cid.group(1) if cid else "a conversation"
            lvl = re.search(r"risk_level=(\w+)", trigger)
            lvl = _RISK_LEVELS.get(lvl.group(1), lvl.group(1).lower()) if lvl else "flagged"
            overall = re.search(r"overall=([0-9.]+)", trigger)
            overall = overall.group(1) if overall else "?"
            measures = _describe_measures(
                _loose_dict(e.get("test_results")).get("by_measure", {})
                or _loose_dict(e.get("implications")))
            signals = _parse_signals(e.get("test_results"))

            openers = [
                f"On {when}, conversation {cid} came back **{lvl}**, scoring "
                f"{overall}/10 overall (entry #{seq}).",
                f"On {when}, the classifier put conversation {cid} at {overall}/10, "
                f"landing it in **{lvl}** territory (entry #{seq}).",
                f"On {when}, {cid} tripped the classifier — **{lvl}** at {overall}/10 "
                f"(entry #{seq}).",
            ]
            s = openers[(seq or 0) % len(openers)]
            if measures:
                s += f" The scores recorded were {measures}."
            if signals:
                quoted = _join([f"\u201c{d}\u201d" for d in signals])
                s += f" Concretely, it matched {quoted}."
            s += (" Because a child may be at risk, the recorded decision was "
                  "to route this to a human monitor rather than clear it "
                  "automatically.")

        # --- shape 3: a multi-model risk panel voted -------------------------
        elif _parse_votes(rationale) and ("per-measure" in (e.get("implications") or "")
                                          or "panel" in trigger):
            subject = "a block of generated code" if domain == "code" else "a conversation"
            agg = re.search(r"aggregate ([0-9.]+)", trigger)
            agg = agg.group(1) if agg else "?"
            votes = _parse_votes(rationale)
            vote_text = _join([f"{model} scored it {score}" for model, score in votes])
            measures = _describe_measures(_loose_dict(e.get("implications")))
            s = (f"On {when}, a risk panel reviewed {subject} (entry #{seq}). "
                 f"The panel runs the material past three independent models, "
                 f"and the recorded combined score was {agg} — past the 0.6 "
                 f"line at which the system records an escalation rather than "
                 f"clearing it automatically.")
            if vote_text:
                s += f" Recorded model scores: {vote_text}."
            if measures:
                s += f" Recorded per-measure breakdown: {measures}."
            s += (" The recorded decision was to escalate to a human monitor."
                  if escalated else
                  " The recorded decision was not to escalate.")

        # --- shape 4: a design / governance choice ----------------------------
        else:
            opts = _render_options(e.get("options_presented"))
            label = "a fairness concern" if domain == "fairness" else "a governance decision"
            s = (f"On {when}, {label} came up — {trigger.rstrip('.')} (entry "
                 f"#{seq}). Rather than apply a default silently — these are "
                 f"safeguarding tradeoffs, not neutral technical settings — the "
                 f"system surfaced the options: {opts}.")
            impl = e.get("implications", "")
            if impl:
                s += f" The tradeoff recorded: {impl.rstrip('.')}."
            s += f" The recorded choice was {choice}"
            s += f", with the recorded reasoning that {rationale.rstrip('.').lower()}." if rationale else "."

        s += ctx

        review_tier = e.get("human_review_tier")
        if review_tier:
            s += f" Human review tier: {_REVIEW_TIER_LABELS.get(review_tier, review_tier)}."

        resp_decision = e.get("response_decision")
        if resp_decision:
            s += f" Response decision: {resp_decision.rstrip('.')}."

        priv_sentence = _privacy_sentence(e)
        if priv_sentence:
            s += " " + priv_sentence

        checks = e.get("source_policy_checks")
        if checks:
            s += " " + _policy_check_sentence(checks)

        # expanded detail level (S5+, S6/S7, or disclosure/override/incident):
        # add the S3+/S4+/S6+ tiered-transparency sentences. 'summary' level
        # (S3-S4) stops here, matching the policy's "1-2 short paragraphs"
        # budget for case summaries.
        if level == "expanded":
            s += _s3_sentence(e)
            s += _s4_sentence(e)
            s += _s6_sentence(e)

        if anchor:
            s += f" Legal anchor: {anchor}."
        s += f" Record sealed under hash: `{e['hash']}`"
        L.append(s)
        L.append("")
    return "\n".join(L)
def _cli(argv: list[str]) -> int:
    root = os.environ.get("COMPLIANCE_ROOT", os.getcwd())
    cmd = argv[1] if len(argv) > 1 else "verify"
    if cmd == "verify":
        ok, msg, n, head = verify_chain(root)
        print(("✅ " if ok else "") + msg)
        if n:
            print(f"   head: {head}")
        return 0 if ok else 1
    if cmd == "report":
        dest = os.path.join(root, argv[2] if len(argv) > 2 else "compliance_report.md")
        with open(dest, "w", encoding="utf-8") as f:
            f.write(render_model_card(root))
        print(f"✅ wrote {dest}")
        return 0
    if cmd == "narrate":
        dest = os.path.join(root, argv[2] if len(argv) > 2 else "audit-trail/narrative.md")
        with open(dest, "w", encoding="utf-8") as f:
            f.write(render_narrative(root))
        print(f"✅ wrote {dest}")
        return 0
    print(f"usage: core.py [verify|report [path]]", file=sys.stderr)
    return 2


if __name__ == "__main__":
    raise SystemExit(_cli(sys.argv))