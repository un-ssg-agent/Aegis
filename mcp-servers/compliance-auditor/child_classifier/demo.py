"""End-to-end demo of the child-safety chat classifier.

Shows classification of various chat scenarios, HITL escalation,
and human resolution. Deterministic, no API key needed.

Run: uv run python mcp-servers/compliance-auditor/child_classifier/demo.py
"""

from __future__ import annotations

import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, "..", "..", ".."))
sys.path.insert(0, os.path.join(ROOT, "mcp-servers", "compliance-auditor"))
import core

from child_classifier import (
    classify_message,
    classify_conversation,
    pending_escalations,
    resolve_escalation,
)


def show(title: str, result: dict) -> None:
    print(f"\n{'=' * 72}")
    print(f"  {title}")
    print(f"{'=' * 72}")
    overall = result.get("overall", "?")
    level = result.get("risk_level", "?")
    by_measure = result.get("by_measure", {})
    signals = result.get("top_signals", [])
    audit_info = result.get("audit")

    print(f"  Overall risk: {overall}/10.0  [{level}]")

    active = {k: v for k, v in by_measure.items() if v > 0}
    if active:
        print(f"  Active categories: {json.dumps(active)}")
    else:
        print("  No risk categories triggered.")

    if signals:
        print("  Top signals:")
        for s in signals[:5]:
            print(f"    - [{s.get('category','?')}] {s.get('description','?')} "
                  f"(weight={s.get('weight','?')})")

    if audit_info:
        print(f"  AUDIT: seq={audit_info.get('audit_seq','?')} "
              f"hash={str(audit_info.get('audit_hash','?'))[:12]}...")
    else:
        print("  Audit: not escalated (low risk level)")


def demo():
    print("=" * 72)
    print("  CHILD-SAFETY CHAT CLASSIFIER — Demo")
    print("  Rule-based risk scoring | 1.0-10.0 scale | HITL for HIGH_RISK")
    print("=" * 72)

    # --- Scenario 1: SAFE — benign chat ---
    show("SCENARIO 1: Benign greeting (expect SAFE)",
         classify_message("hi, how are you? i like playing video games", "conv_1"))

    # --- Scenario 2: SENSITIVE — general distress ---
    show("SCENARIO 2: General distress (expect SENSITIVE)",
         classify_message("i'm sad today and i don't know what to do", "conv_2"))

    # --- Scenario 3: CONCERNING — self-harm ideation ---
    show("SCENARIO 3: Self-harm ideation (expect CONCERNING or HIGH_RISK)",
         classify_message("i want to cut myself again, i can't stop thinking about it", "conv_3"))

    # --- Scenario 4: HIGH_RISK — suicide plan ---
    show("SCENARIO 4: Suicide plan with method (expect HIGH_RISK -> HITL)",
         classify_message("i have a plan to kill myself. i bought pills and wrote a note. this is goodbye.", "conv_4"))

    # --- Scenario 5: HIGH_RISK — grooming ---
    show("SCENARIO 5: Grooming indicators (expect HIGH_RISK -> HITL)",
         classify_message("don't tell your parents about us. let's talk on snapchat. i'll buy you a gift if you send me a picture.", "conv_5"))

    # --- Scenario 6: SAFE — figurative language ---
    show("SCENARIO 6: Figurative language (expect SAFE - this homework is killing me)",
         classify_message("this homework is killing me, i'm dying of boredom lol", "conv_6"))

    # --- Scenario 7: Bullying ---
    show("SCENARIO 7: Bullying (expect CONCERNING)",
         classify_message("you're such a loser, nobody likes you, just go away", "conv_7"))

    # --- Scenario 8: PII Exposure ---
    show("SCENARIO 8: PII exposure (expect SENSITIVE)",
         classify_message("my email is kid123@gmail.com and i live at 123 main street", "conv_8"))

    # --- Scenario 9: Full conversation ---
    messages = [
        {"role": "child", "text": "i hate my life"},
        {"role": "bot", "text": "i hear you're feeling down. what's going on?"},
        {"role": "child", "text": "i just want to die. i have a plan. i'm going to use my dad's gun."},
        {"role": "child", "text": "this is goodbye. tell everyone i'm sorry."},
    ]
    show("SCENARIO 9: Full conversation with escalation (expect HIGH_RISK)",
         classify_conversation(messages, "conv_9"))

    # --- HITL flow: check pending ---
    print(f"\n{'=' * 72}")
    print("  HUMAN-IN-THE-LOOP FLOW")
    print(f"{'=' * 72}")
    pending = pending_escalations()
    print(f"\n  Pending escalations: {len(pending)}")
    for p in pending:
        print(f"    - {p['conversation_id']}: risk {p['overall_risk']}/10.0 [{p['risk_level']}]")

    # Resolve one
    if pending:
        cid = pending[0]["conversation_id"]
        print(f"\n  Human reviewing: {cid}")
        resolution = resolve_escalation(cid, "demo_reviewer", "confirmed_risk",
                                        "Escalated correctly - contains suicide plan language")
        print(f"  Resolution logged: seq={resolution['audit_seq']} "
              f"hash={resolution['audit_hash'][:12]}...")

    # --- Verify chain ---
    ok, msg, n, head = core.verify_chain(ROOT)
    print(f"\n  Audit chain: {'OK' if ok else 'BROKEN'} ({msg})")

    print(f"\n{'=' * 72}")
    print("  Demo complete. Full audit trail:")
    print(f"    audit-trail/decisions.jsonl")
    print(f"    audit-trail/narrative.md")
    print(f"{'=' * 72}")


if __name__ == "__main__":
    demo()
