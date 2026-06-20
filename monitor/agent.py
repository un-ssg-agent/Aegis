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