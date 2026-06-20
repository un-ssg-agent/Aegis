"""Unit tests for the child-safety classifier.

Run: uv run python mcp-servers/compliance-auditor/child_classifier/test_classifier.py
"""
from __future__ import annotations

import sys
import os
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "..", "..", "mcp-servers", "compliance-auditor"))

from child_classifier import classify_message, scoring


def test_safe_benign():
    r = classify_message("hi how are you? i like playing outside", "test_safe")
    assert r["risk_level"] == "SAFE"
    assert r["overall"] == 1.0


def test_figurative_language():
    r = classify_message("this homework is killing me lol", "test_fig")
    assert r["risk_level"] == "SAFE"
    assert r["overall"] == 1.0


def test_sensitive_distress():
    r = classify_message("i'm having a really bad day and i don't know what to do", "test_distress")
    assert r["risk_level"] in ("SENSITIVE", "CONCERNING", "HIGH_RISK")
    assert r["overall"] >= 5.0


def test_high_risk_self_harm():
    r = classify_message("i want to kill myself i have a plan with pills", "test_sh")
    assert r["risk_level"] == "HIGH_RISK"
    assert r["overall"] >= 9.0
    assert r["audit"] is not None


def test_high_risk_suicide_farewell():
    r = classify_message("this is goodbye i won't be here tomorrow i love you all", "test_farewell")
    assert r["risk_level"] == "HIGH_RISK"
    assert r["overall"] >= 9.0


def test_grooming_detected():
    r = classify_message("don't tell your parents let's talk on snapchat", "test_groom")
    assert r["overall"] >= 5.0
    assert r["by_measure"].get("grooming", 0) > 0


def test_bullying_detected():
    r = classify_message("you're a loser nobody likes you just go away", "test_bully")
    assert r["overall"] >= 4.0
    assert r["by_measure"].get("bullying", 0) > 0


def test_pii_exposure():
    r = classify_message("my email is test@example.com and my phone is 555-123-4567", "test_pii")
    assert r["by_measure"].get("pii_exposure", 0) >= 5.0


def test_violence_threat():
    r = classify_message("i'm going to bring a gun to school and shoot everyone", "test_violence")
    assert r["risk_level"] == "HIGH_RISK"
    assert r["by_measure"].get("violence", 0) >= 9.0


def test_risk_mapping():
    assert scoring.classify_risk(1.0) == "SAFE"
    assert scoring.classify_risk(4.9) == "SAFE"
    assert scoring.classify_risk(5.0) == "SENSITIVE"
    assert scoring.classify_risk(6.9) == "SENSITIVE"
    assert scoring.classify_risk(7.0) == "CONCERNING"
    assert scoring.classify_risk(8.9) == "CONCERNING"
    assert scoring.classify_risk(9.0) == "HIGH_RISK"
    assert scoring.classify_risk(10.0) == "HIGH_RISK"


def test_category_weights():
    for cat in scoring._patterns.PATTERNS:
        assert scoring._patterns.CATEGORY_WEIGHTS.get(cat, 0) > 0
        assert scoring._patterns.CATEGORY_DESCRIPTIONS.get(cat, "")
        assert len(scoring._patterns.PATTERNS[cat]) > 0


def test_all_categories_have_patterns():
    for cat, patterns in scoring._patterns.PATTERNS.items():
        for p in patterns:
            assert "id" in p
            assert "patterns" in p
            assert "type" in p
            assert p["type"] in ("keyword", "regex")
            assert "weight" in p
            assert 1.0 <= p["weight"] <= 10.0


def run():
    tests = [
        test_safe_benign,
        test_figurative_language,
        test_sensitive_distress,
        test_high_risk_self_harm,
        test_high_risk_suicide_farewell,
        test_grooming_detected,
        test_bullying_detected,
        test_pii_exposure,
        test_violence_threat,
        test_risk_mapping,
        test_category_weights,
        test_all_categories_have_patterns,
    ]
    passed = 0
    failed = 0
    for t in tests:
        try:
            t()
            print(f"  PASS  {t.__name__}")
            passed += 1
        except Exception as e:
            print(f"  FAIL  {t.__name__}: {e}")
            failed += 1
    print(f"\n{'=' * 40}")
    print(f"  {passed} passed, {failed} failed")
    print(f"{'=' * 40}")
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    sys.exit(run())
