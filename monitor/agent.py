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
            model=provider, session=session)
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
  "human_review": false
}

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
            model=provider, session=session)
        result["audit_seq"] = rec["seq"]
        result["audit_hash"] = rec["hash"]
    return result