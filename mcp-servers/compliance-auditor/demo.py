"""End-to-end demo: drive a real model through the compliance gate.

Simulates exactly what OpenCode does, but standalone (no OpenCode needed):
  - system prompt   = AGENTS.md (the gate rules)
  - user request    = a developer asking for sensitive code
  - tool exposed    = log_decision (backed by the real hash chain in core.py)

The model presents options and waits; we supply the developer's choice; the
model then calls log_decision; we execute it against the tamper-evident chain;
the model emits the final code. Finally we verify the chain and render the
Model Card — the artifacts the user wakes up to.

Usage:
  python3 demo.py                       # runs the 3 built-in scenarios
  python3 demo.py "<request>" "<choice>"  # one custom scenario
"""
from __future__ import annotations

import json
import os
import sys

import core
import llm_client

ROOT = os.environ.get("COMPLIANCE_ROOT", os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))

SYSTEM = open(os.path.join(ROOT, "AGENTS.md"), encoding="utf-8").read()

LOG_TOOL = [{
    "type": "function",
    "function": {
        "name": "log_decision",
        "description": ("Append a tamper-evident decision to the audit trail. "
                        "Call AFTER the developer chooses and BEFORE generating final code. "
                        "Never invent a hash — this tool computes it."),
        "parameters": {
            "type": "object",
            "properties": {
                "domain": {"type": "string", "enum": ["privacy", "security", "fairness"]},
                "trigger": {"type": "string", "description": "why the gate fired"},
                "options_presented": {"type": "array", "items": {"type": "string"}},
                "implications": {"type": "string", "description": "the tradeoff each option carries"},
                "user_choice": {"type": "string"},
                "rationale": {"type": "string"},
                "ai_act_ref": {"type": "string", "description": "verbatim legal anchor if known"},
            },
            "required": ["domain", "trigger", "options_presented", "implications", "user_choice"],
        },
    },
}]

SCENARIOS = [
    ("写个接口把 user_profile 表所有字段查出来直接返回给前端", "A"),
    ("根据用户传入的 username 拼个 SQL 查询查出这个用户", "A"),
    ("用 compas.csv（含 race、age 列）训练一个累犯风险预测分类器", "B"),
]


def run_scenario(request: str, choice: str) -> None:
    print("\n" + "=" * 72)
    print(f"DEV REQUEST: {request}")
    print("=" * 72)
    messages = [{"role": "system", "content": SYSTEM},
                {"role": "user", "content": request}]

    # Phase 1 — present options. No tool exposed yet, so the model MUST stop
    # and present alternatives in text rather than logging a guessed choice.
    msg, provider = llm_client.chat(messages, tools=None)
    messages.append(msg)
    print(f"\n[AGENT via {provider}]\n{(msg.get('content') or '').strip()}")

    # Phase 2 — developer chooses; now expose log_decision so the model
    # records the REAL choice, then generates code.
    print(f"\n[DEV CHOICE] {choice}")
    messages.append({"role": "user",
                     "content": f"我选方案 {choice}。请先调用 log_decision 记录这个决策，再据此生成代码，不要再追问。"})
    for _ in range(5):
        msg, provider = llm_client.chat(messages, tools=LOG_TOOL)
        messages.append(msg)
        tool_calls = msg.get("tool_calls") or []
        if tool_calls:
            for tc in tool_calls:
                args = json.loads(tc["function"]["arguments"] or "{}")
                if tc["function"]["name"] == "log_decision":
                    rec = core.append_decision(
                        ROOT,
                        args.get("domain", ""), args.get("trigger", ""),
                        args.get("options_presented", []), args.get("implications", ""),
                        args.get("user_choice", ""), args.get("rationale", ""),
                        ai_act_ref=args.get("ai_act_ref", ""), model=provider, session="demo",
                    )
                    result = f"Logged seq={rec['seq']} hash={rec['hash'][:12]}… (chain extended)"
                    print(f"\n  >> [TOOL] log_decision -> {result}")
                    messages.append({"role": "tool", "tool_call_id": tc["id"], "content": result})
            continue
        content = (msg.get("content") or "").strip()
        if content:
            print(f"\n[AGENT via {provider}]\n{content}")
        break


def main() -> int:
    if len(sys.argv) >= 3:
        scenarios = [(sys.argv[1], sys.argv[2])]
    else:
        scenarios = SCENARIOS
    try:
        for req, ch in scenarios:
            run_scenario(req, ch)
    except llm_client.LLMError as e:
        print(f"\n[!] LLM unavailable, gate demo skipped:\n{e}", file=sys.stderr)
        print("    (The hash-chain backend is independent — run selftest.py.)", file=sys.stderr)
        return 1
    print("\n" + "=" * 72)
    print("VERIFY + REPORT")
    print("=" * 72)
    ok, msg, n, head = core.verify_chain(ROOT)
    print(("✅ " if ok else "❌ ") + msg + (f"  head={head[:12]}…" if n else ""))
    with open(os.path.join(ROOT, "compliance_report.md"), "w", encoding="utf-8") as f:
        f.write(core.render_model_card(ROOT))
    print(f"✅ wrote compliance_report.md  ({n} decisions)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
