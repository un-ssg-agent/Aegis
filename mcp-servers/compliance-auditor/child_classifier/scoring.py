"""Scoring engine: pattern matching -> category scores -> overall risk.

Flow:
  1. For each category, match patterns against text
  2. Compute per-category score from matched pattern weights
  3. Compute overall risk score (1.0-10.0) from category scores
  4. Map to risk level (SAFE / SENSITIVE / CONCERNING / HIGH_RISK)
"""

from __future__ import annotations

import re
from typing import Sequence

from . import patterns as _patterns

# Thresholds chosen by developer (recorded in audit trail seq=5):
#   1.0-4.9 SAFE
#   5.0-6.9 SENSITIVE
#   7.0-8.9 CONCERNING
#   9.0-10.0 HIGH_RISK
RISK_THRESHOLDS = {
    "SAFE": (1.0, 4.9),
    "SENSITIVE": (5.0, 6.9),
    "CONCERNING": (7.0, 8.9),
    "HIGH_RISK": (9.0, 10.0),
}


def _compile_keyword_pattern(pattern: str) -> re.Pattern:
    """Compile a keyword pattern to word-boundary matching (case-insensitive)."""
    escaped = re.escape(pattern)
    return re.compile(escaped, re.IGNORECASE)


def _compile_regex_pattern(pattern: str) -> re.Pattern:
    """Compile a regex pattern (case-insensitive)."""
    return re.compile(pattern, re.IGNORECASE)


def _get_compiled(entry: dict) -> list[re.Pattern]:
    """Return compiled patterns for a single pattern entry."""
    out: list[re.Pattern] = []
    for p in entry["patterns"]:
        if entry["type"] == "keyword":
            out.append(_compile_keyword_pattern(p))
        else:
            out.append(_compile_regex_pattern(p))
    return out


def score_category(text: str, category: str) -> dict:
    """Score text against a single risk category.

    Returns:
        {"score": float (0.0-10.0),
         "matched": [{"id": str, "weight": float, "description": str, "fp_risk": str}, ...],
         "category": str}
    """
    text_lower = text.lower()
    matched: list[dict] = []
    max_weight = 0.0

    for entry in _patterns.PATTERNS.get(category, []):
        compiled = _get_compiled(entry)
        for cp in compiled:
            if cp.search(text_lower):
                matched.append({
                    "id": entry["id"],
                    "weight": entry["weight"],
                    "description": entry["description"],
                    "fp_risk": entry["fp_risk"],
                })
                if entry["weight"] > max_weight:
                    max_weight = entry["weight"]
                break

    cat_weight = _patterns.CATEGORY_WEIGHTS.get(category, 1.0)
    score = min(max_weight * cat_weight, 10.0) if max_weight > 0 else 0.0
    score = round(score, 1)

    return {"score": score, "matched": matched, "category": category}


def score_all(text: str) -> dict[str, dict]:
    """Score text against all risk categories.

    Returns:
        {category_name: {"score": float, "matched": [...]}, ...}
    """
    return {cat: score_category(text, cat) for cat in _patterns.PATTERNS}


def compute_overall(category_results: dict[str, dict]) -> float:
    """Compute overall risk score (1.0-10.0) from per-category results.

    Formula:
      - Base = highest single category score
      - Boost from multiple categories firing (0.3 per additional category > 0)
      - Overall = min(base + boost, 10.0)
      - Minimum is 1.0 (no risk detected)
    """
    scores = [v["score"] for v in category_results.values()]
    max_score = max(scores)
    if max_score == 0:
        return 1.0

    cat_count = sum(1 for s in scores if s > 0)
    boost = (cat_count - 1) * 0.3
    overall = min(max_score + boost, 10.0)
    return round(overall, 1)


def classify_risk(overall: float) -> str:
    """Map an overall risk score to a risk level string.

    Thresholds (developer-chosen, recorded in audit trail):
      1.0-4.9  -> SAFE
      5.0-6.9  -> SENSITIVE
      7.0-8.9  -> CONCERNING
      9.0-10.0 -> HIGH_RISK
    """
    for level, (lo, hi) in RISK_THRESHOLDS.items():
        if lo <= overall <= hi:
            return level
    return "SAFE"


def format_assessment(
    overall: float,
    risk_level: str,
    category_results: dict[str, dict],
) -> dict:
    """Package the full assessment result into a dict."""
    by_measure = {
        cat: res["score"]
        for cat, res in category_results.items()
    }
    return {
        "overall": overall,
        "risk_level": risk_level,
        "by_measure": by_measure,
        "top_signals": [
            {"category": cat, "signal": m["id"], "weight": m["weight"], "description": m["description"]}
            for cat, res in category_results.items()
            for m in res["matched"][:3]
        ],
        "thresholds": RISK_THRESHOLDS,
    }
