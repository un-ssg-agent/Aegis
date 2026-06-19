"""Child-safety demo — the UNICEF additional problem, governed end to end.

This is NOT a child chatbot. It shows what the *governance layer* does when a
developer asks the coding agent to build a child-safety classifier: the gate
fires, forces explicit choices on the three safeguarding axes (escalation /
retention / evaluation), and records them in the tamper-evident audit trail with
a UN CRC legal anchor — exactly the "Expected governance behavior" in the brief.

Deterministic, no API key needed.

Run: uv run python mcp-servers/compliance-auditor/child_safety_demo.py
"""
import os

import core

ROOT = os.environ.get(
    "COMPLIANCE_ROOT",
    os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))


def main() -> None:
    print("=" * 72)
    print("DEV REQUEST: build a classifier that flags children's chat messages "
          "for grooming / self-harm and escalates high-risk ones")
    print("=" * 72)

    print("\n[GATE] Child-safety signal — processes minors' conversations "
          "(UN CRC arts 3,12,16,19,34). Code paused. You MUST choose on 3 axes:")
    options = [
        "Escalation: A) human-in-the-loop review  vs  B) fully automated  "
        "(FN leaves a child unsupported; FP = unnecessary surveillance)",
        "Retention: A) full conversations  B) anonymised excerpts  "
        "C) metadata only  D) no content by default  (safety vs child privacy)",
        "Evaluation: A) disaggregated by age/language/disability  vs  "
        "B) average-only  (average-fine can still fail the children who need help)",
    ]
    for o in options:
        print(f"   - {o}")

    choice = ("Escalation=human-in-the-loop; Retention=metadata-only; "
              "Evaluation=disaggregated by age+language+disability")
    print(f"\n[DEV CHOICE] {choice}")

    rec = core.append_decision(
        ROOT, "child-safety",
        "build child-safety classifier over minors' chat (grooming/self-harm) "
        "with escalation",
        options,
        "Safety vs privacy (retention), false-negative vs false-positive "
        "(escalation), and inclusion across groups (evaluation) are safeguarding "
        "decisions, not technical defaults.",
        choice,
        rationale="minimise stored data while keeping a human accountable for "
                  "high-risk escalations; check the model works for the most "
                  "vulnerable children, not just on average",
        ai_act_ref="UN CRC Articles 3, 12, 16, 19, 34; EU AI Act (rights-sensitive)",
        model="child_safety_demo", session="child-safety-demo")
    print(f"\n[LOGGED] seq={rec['seq']} hash={rec['hash'][:12]}…")

    ok, msg, n, head = core.verify_chain(ROOT)
    print(f"[VERIFY] {'✅' if ok else '❌'} {msg}")
    print("\nThe report will now include a 'Child-safety safeguards' section "
          "(run: core.py report).")


if __name__ == "__main__":
    main()
