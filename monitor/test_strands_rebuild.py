"""Checklist tests for the Strands rebuild — run this BEFORE flipping app.py's
import, so you have real pass/fail evidence instead of eyeballing a demo.

Usage:
    cd monitor
    python3 test_strands_rebuild.py

Each test is independent and prints PASS/FAIL/SKIP with a one-line reason.
Tests that need a live model (Ollama or Bedrock) are clearly marked SKIP if
neither is reachable — that's expected in a sandbox with no model backend.

IMPORTANT: this redirects strands_tools.ROOT to a scratch directory so it
NEVER writes test data into the real repo's audit-trail/.
"""
from __future__ import annotations

import os
import shutil
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

PASS, FAIL, SKIP = "PASS", "FAIL", "SKIP"
_results: list[tuple[str, str, str]] = []


def report(name: str, status: str, detail: str = "") -> None:
    _results.append((name, status, detail))
    print(f"  [{status}] {name}" + (f" — {detail}" if detail else ""))


def section(title: str) -> None:
    print(f"\n{'=' * 70}\n  {title}\n{'=' * 70}")


# ───────────────────────── scratch isolation ─────────────────────────

_SCRATCH = tempfile.mkdtemp(prefix="aegis_strands_test_")


def _setup_scratch() -> None:
    """Point the audit chain at a throwaway directory for this whole run."""
    import strands_tools
    real_root = strands_tools.ROOT
    audit_src = os.path.join(real_root, "audit-trail")
    audit_dst = os.path.join(_SCRATCH, "audit-trail")
    if os.path.isdir(audit_src):
        shutil.copytree(audit_src, audit_dst)
    else:
        os.makedirs(audit_dst, exist_ok=True)
    strands_tools.ROOT = _SCRATCH
    import strands_agent
    strands_agent.ROOT = _SCRATCH


def _teardown_scratch() -> None:
    shutil.rmtree(_SCRATCH, ignore_errors=True)


# ───────────────────────── test 1: schema validation is real ─────────────────────────

def test_schema_validation_rejects_bad_output() -> None:
    """Confirm a malformed dict actually fails Pydantic validation — i.e. the
    schema is load-bearing, not decorative. This is the core claim behind
    dropping the old regex/marker hack.
    """
    section("TEST 1 — Schema validation is real (not decorative)")
    from pydantic import ValidationError
    from strands_schemas import GateOutput, ChildChatOutput

    # Missing required fields -> must raise, not silently produce a half-object
    try:
        GateOutput(message="ok")  # missing flagged, decisions
        report("GateOutput rejects missing required fields", FAIL,
               "construction succeeded with missing fields — schema is not enforcing")
    except ValidationError:
        report("GateOutput rejects missing required fields", PASS)

    # Score out of the declared 0-9 range -> must raise (ge=0, le=9 constraint)
    try:
        ChildChatOutput(
            reply="hi",
            assessment={
                "bullying": {"score": 0, "reason": "x"},
                "grooming": {"score": 0, "reason": "x"},
                "abuse": {"score": 0, "reason": "x"},
                "self_harm": {"score": 99, "reason": "out of range"},  # invalid
                "distress": {"score": 0, "reason": "x"},
            },
        )
        report("ChildChatOutput rejects out-of-range score", FAIL,
               "score=99 was accepted despite ge=0,le=9 constraint")
    except ValidationError:
        report("ChildChatOutput rejects out-of-range score", PASS)

    # Valid object should construct cleanly (sanity check the schema isn't
    # ALSO too strict in the other direction)
    try:
        g = GateOutput(
            message="ok", flagged=["x"],
            decisions=[{"id": "escalation", "question": "q", "source": "s",
                       "options": [{"id": "a", "label": "l", "tradeoff": "t"},
                                   {"id": "b", "label": "l2", "tradeoff": "t2"}]}],
        )
        report("GateOutput accepts well-formed input", PASS)
    except Exception as e:
        report("GateOutput accepts well-formed input", FAIL, str(e)[:150])


# ───────────────────────── test 2: crisis resource lookup fires correctly ─────────────────────────

def test_crisis_resource_lookup() -> None:
    section("TEST 2 — lookup_crisis_resource gates correctly, never invents data")
    from strands_tools import lookup_crisis_resource, RESOURCES

    # Eligible category + known region -> real resource, not invented
    r = lookup_crisis_resource("self_harm", region_hint="en-US")
    if r and r.get("phone") == "988" and r.get("name") == "988 Suicide & Crisis Lifeline":
        report("Eligible category + known region returns verified resource", PASS)
    else:
        report("Eligible category + known region returns verified resource", FAIL, str(r))

    # Eligible category + unknown region -> falls back to international directory,
    # not a guessed/invented number
    r2 = lookup_crisis_resource("distress", region_hint="zz-NOWHERE")
    if r2 and r2.get("region_used") == "default_international":
        report("Unknown region falls back to international directory (no invention)", PASS)
    else:
        report("Unknown region falls back to international directory (no invention)", FAIL, str(r2))

    # Non-eligible category -> must return None (don't surface a hotline for
    # e.g. plain bullying that hasn't escalated)
    r3 = lookup_crisis_resource("bullying")
    if r3 is None:
        report("Non-eligible category returns None (no over-surfacing)", PASS)
    else:
        report("Non-eligible category returns None (no over-surfacing)", FAIL, str(r3))

    # Sanity: every entry in the table is a real, distinct service (no
    # placeholder/duplicate entries left behind by accident)
    names = [v.get("name") for v in RESOURCES.values()]
    if len(names) == len(set(names)):
        report("RESOURCES table has no duplicate/placeholder entries", PASS)
    else:
        report("RESOURCES table has no duplicate/placeholder entries", FAIL, str(names))


# ───────────────────────── test 3: audit chain wiring is correct ─────────────────────────

def test_audit_chain_wiring() -> None:
    section("TEST 3 — log_decision writes to the real hash chain correctly")
    import core
    from strands_tools import _log_decision_impl

    ok_before, _, n_before, head_before = core.verify_chain(_SCRATCH)

    rec = _log_decision_impl(
        domain="child-safety",
        trigger="TEST chat conv_test risk_level=HIGH_RISK overall=9.5",
        options_presented=["Self-Harm", "Distress"],
        implications="test entry from test_strands_rebuild.py",
        user_choice="ESCALATED to authorized human reviewer",
        rationale="automated test",
        ai_act_ref="UN CRC arts 3,12,16,19,34",
        session="test-session",
        model="strands-test",
    )

    ok_after, msg_after, n_after, head_after = core.verify_chain(_SCRATCH)

    if rec.get("audit_seq") == n_before:
        report("New entry's seq follows the prior chain length", PASS,
               f"seq is 0-indexed in core.py, so seq={n_before} is correct for entry #{n_before + 1}")
    else:
        report("New entry's seq follows the prior chain length", FAIL,
               f"expected seq {n_before} (0-indexed), got {rec.get('audit_seq')}")

    if ok_after and head_after == rec.get("audit_hash"):
        report("Chain verifies intact and head matches the new entry's hash", PASS)
    else:
        report("Chain verifies intact and head matches the new entry's hash", FAIL,
               f"verify_chain ok={ok_after} msg={msg_after}; head={head_after} vs rec={rec.get('audit_hash')}")

    # Tamper test: flip one character INSIDE the last JSON record's content
    # (not trailing whitespace/newline, which wouldn't affect the hash at all)
    # and confirm verification actually fails — this is the "show it fail"
    # live-demo moment from the planning doc.
    decisions_path = os.path.join(_SCRATCH, "audit-trail", "decisions.jsonl")
    with open(decisions_path, "r", encoding="utf-8") as f:
        content = f.read()
    lines = content.splitlines(keepends=True)
    last_line = lines[-1] if lines[-1].strip() else lines[-2]
    # flip a character inside the trigger text, well away from line edges
    idx = last_line.find('"trigger"')
    target_pos = idx + 20  # land inside the trigger string's value, not the key
    chars = list(last_line)
    chars[target_pos] = "X" if chars[target_pos] != "X" else "Y"
    tampered_line = "".join(chars)
    tampered = content.replace(last_line, tampered_line)
    with open(decisions_path, "w", encoding="utf-8") as f:
        f.write(tampered)

    ok_tampered, msg_tampered, _, _ = core.verify_chain(_SCRATCH)
    if not ok_tampered:
        report("Tampering one byte is detected by verify_chain", PASS, msg_tampered)
    else:
        report("Tampering one byte is detected by verify_chain", FAIL,
               "verify_chain still reported OK after a byte was flipped")

    # restore for any later tests in this run
    with open(decisions_path, "w", encoding="utf-8") as f:
        f.write(content)


# ───────────────────────── test 4: category mismatch status (informational) ─────────────────────────

def test_category_mismatch_status() -> None:
    section("TEST 4 — 8-category classifier vs 5-axis chat UI (status check, not pass/fail)")
    from strands_tools import classify_risk
    import strands_agent

    classifier_categories = set(classify_risk("test")["by_measure"].keys())
    chat_axes = set(strands_agent._DOMAINS)

    overlap = classifier_categories & chat_axes
    classifier_only = classifier_categories - chat_axes
    chat_only = chat_axes - classifier_categories

    report("Classifier categories vs chat UI axes", SKIP,
           f"overlap={sorted(overlap)} | classifier-only={sorted(classifier_only)} | "
           f"chat-only={sorted(chat_only)} — UNRESOLVED, classify_risk is not yet "
           f"wired into child_chat's decision flow (see planning doc §4.2)")


# ───────────────────────── test 5: model backend reachability (informational) ─────────────────────────

def test_model_backend_status() -> None:
    section("TEST 5 — Which model backend is actually reachable right now")
    import strands_agent
    if strands_agent._MODEL_PROVIDER == "ollama":
        report("Model backend", PASS, "Ollama reachable locally")
    elif strands_agent._MODEL_PROVIDER == "bedrock":
        report("Model backend", SKIP,
               "Ollama unreachable, fell back to Bedrock object construction "
               "(this does NOT confirm AWS credentials actually work — that "
               "only happens on a real generate()/child_chat() call)")
    else:
        report("Model backend", FAIL, "neither Ollama nor Bedrock available")


def main() -> int:
    _setup_scratch()
    try:
        test_schema_validation_rejects_bad_output()
        test_crisis_resource_lookup()
        test_audit_chain_wiring()
        test_category_mismatch_status()
        test_model_backend_status()
    finally:
        _teardown_scratch()

    print(f"\n{'=' * 70}")
    n_pass = sum(1 for _, s, _ in _results if s == PASS)
    n_fail = sum(1 for _, s, _ in _results if s == FAIL)
    n_skip = sum(1 for _, s, _ in _results if s == SKIP)
    print(f"  {n_pass} passed, {n_fail} failed, {n_skip} informational/skip")
    print(f"{'=' * 70}")
    return 1 if n_fail else 0


if __name__ == "__main__":
    sys.exit(main())