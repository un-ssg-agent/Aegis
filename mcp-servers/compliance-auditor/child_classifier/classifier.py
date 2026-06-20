"""Main public API for the child-safety chat classifier.

Usage:
    from child_classifier import classify_message, classify_conversation

    # Single message
    result = classify_message("i want to die", "conv_123")

    # Conversation (multiple turns)
    messages = [
        {"role": "child", "text": "i hate myself"},
        {"role": "child", "text": "i want to kill myself"},
    ]
    result = classify_conversation(messages, "conv_456")

    # Check pending HITL escalations
    from child_classifier import pending_escalations
    pending = pending_escalations()

    # Human resolves
    from child_classifier import resolve_escalation
    resolve_escalation("conv_456", "reviewer_name", "confirmed_risk", "noted")
"""

from __future__ import annotations

import time
from typing import Any, Sequence

from . import scoring
from . import audit


def classify_message(
    text: str,
    conversation_id: str | None = None,
    metadata: dict | None = None,
) -> dict:
    """Classify a single chat message from a minor for safety risk.

    Args:
        text: Message text to classify.
        conversation_id: Optional conversation identifier. Auto-generated if None.
        metadata: Optional dict with additional context (e.g., {"age_group": "13-17"}).

    Returns:
        Assessment dict with keys:
            overall: float (1.0-10.0)
            risk_level: str (SAFE|SENSITIVE|CONCERNING|HIGH_RISK)
            by_measure: dict of per-category scores
            top_signals: list of matched signal descriptions
            conversation_id: str
            audit: dict if escalated, else None
    """
    cid = conversation_id or f"msg_{int(time.time() * 1000)}_{hash(text) % 10000}"
    category_results = scoring.score_all(text)
    overall = scoring.compute_overall(category_results)
    risk_level = scoring.classify_risk(overall)
    assessment = scoring.format_assessment(overall, risk_level, category_results)
    assessment["conversation_id"] = cid
    assessment["timestamp"] = time.time()
    assessment["metadata"] = metadata or {}

    messages_data = [{"role": "child", "text": text, "metadata": metadata}] if conversation_id else []

    if risk_level in ("HIGH_RISK", "CONCERNING"):
        audit_rec = audit.record_assessment(cid, messages_data, assessment)
        assessment["audit"] = audit_rec
    else:
        assessment["audit"] = None

    return assessment


def classify_conversation(
    messages: list[dict],
    conversation_id: str | None = None,
    metadata: dict | None = None,
) -> dict:
    """Classify a full conversation (multiple turns) for safety risk.

    Args:
        messages: List of dicts with at minimum {"text": str}.
                  May include {"role": str, "text": str, "timestamp": float}.
        conversation_id: Optional identifier. Auto-generated if None.
        metadata: Optional context dict.

    Returns:
        Assessment dict with:
            overall: float (1.0-10.0) — max of per-message scores with boost
            risk_level: str
            by_measure: dict of max per-category scores across all messages
            per_message: list of individual message assessments
            message_count: int
            top_signals: consolidated top signals
            conversation_id: str
            audit: dict if escalated
    """
    cid = conversation_id or f"conv_{int(time.time() * 1000)}_{hash(str(messages)) % 10000}"

    per_message: list[dict] = []
    aggregated: dict[str, list[float]] = {}
    all_signals: list[dict] = []

    for msg in messages:
        text = msg.get("text", msg.get("content", ""))
        if not text:
            continue
        cat_results = scoring.score_all(text)
        overall = scoring.compute_overall(cat_results)
        risk_level = scoring.classify_risk(overall)
        assessment = scoring.format_assessment(overall, risk_level, cat_results)
        assessment["role"] = msg.get("role", "unknown")
        per_message.append(assessment)

        for cat, res in cat_results.items():
            aggregated.setdefault(cat, []).append(res["score"])
            for m in res["matched"]:
                all_signals.append({"category": cat, **m})

    by_measure = {
        cat: round(max(scores), 1) for cat, scores in aggregated.items()
    }
    max_cat_score = max(by_measure.values()) if by_measure else 0.0
    active_categories = sum(1 for v in by_measure.values() if v > 0)
    overall = min(max_cat_score + (active_categories - 1) * 0.3, 10.0) if max_cat_score > 0 else 1.0
    overall = round(max(s["overall"] for s in per_message), 1) if per_message else 1.0
    risk_level = scoring.classify_risk(overall)

    seen = set()
    deduped_signals = []
    for s in all_signals:
        key = s.get("id", s.get("signal", ""))
        if key not in seen:
            seen.add(key)
            deduped_signals.append(s)

    assessment = {
        "overall": overall,
        "risk_level": risk_level,
        "by_measure": by_measure,
        "per_message": per_message,
        "message_count": len(messages),
        "top_signals": deduped_signals[:10],
        "conversation_id": cid,
        "timestamp": time.time(),
        "metadata": metadata or {},
        "thresholds": scoring.RISK_THRESHOLDS,
    }

    if risk_level in ("HIGH_RISK", "CONCERNING"):
        messages_data = [
            {"role": m.get("role", "unknown"), "text": m.get("text", m.get("content", ""))}
            for m in messages
        ]
        audit_rec = audit.record_assessment(cid, messages_data, assessment)
        assessment["audit"] = audit_rec
    else:
        assessment["audit"] = None

    return assessment


def pending_escalations() -> list[dict]:
    """Return all un-resolved HIGH_RISK conversations awaiting human review (HITL)."""
    return audit.pending_escalations()


def resolve_escalation(
    conversation_id: str,
    reviewer: str,
    action: str,
    note: str = "",
) -> dict:
    """Record a human reviewer's decision, closing the HITL loop.

    Args:
        conversation_id: Which conversation to resolve.
        reviewer: Name or ID of the human reviewer.
        action: One of "confirmed_risk", "false_positive", "actioned", "no_action_needed".
        note: Optional free-text note.

    Returns:
        Resolution dict with audit_seq and audit_hash.
    """
    return audit.resolve(conversation_id, reviewer, action, note)
