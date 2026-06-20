"""Audit trail integration and retention management for the child classifier.

Provides:
  - record_assessment(): store conversation + scores in the audit trail
  - escalate(): append HIGH_RISK escalation to the audit chain for HITL review
  - resolve(): record human reviewer's decision on an escalation
  - ConversationStore: in-memory store with TTL-based eviction (default 30 days)

Uses the existing core.py hash chain for tamper-evident logging.
"""

from __future__ import annotations

import json
import os
import sys
import threading
import time
from typing import Any

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, "..", "..", ".."))
sys.path.insert(0, os.path.join(ROOT, "mcp-servers", "compliance-auditor"))
import core

RETENTION_DAYS = 30
RETENTION_SECONDS = RETENTION_DAYS * 86400


class ConversationRecord:
    """A stored conversation with its assessment and metadata."""

    def __init__(
        self,
        conversation_id: str,
        messages: list[dict],
        assessment: dict,
        created_at: float | None = None,
    ):
        self.conversation_id = conversation_id
        self.messages = messages
        self.assessment = assessment
        self.created_at = created_at or time.time()
        self.resolved: dict | None = None

    @property
    def expired(self) -> bool:
        return (time.time() - self.created_at) > RETENTION_SECONDS

    def to_dict(self) -> dict:
        return {
            "conversation_id": self.conversation_id,
            "n_messages": len(self.messages),
            "overall_risk": self.assessment.get("overall"),
            "risk_level": self.assessment.get("risk_level"),
            "by_measure": self.assessment.get("by_measure"),
            "created_at": self.created_at,
            "resolved": self.resolved,
        }


class ConversationStore:
    """Thread-safe in-memory store for conversations with TTL eviction.

    Full conversations retained per developer choice: 30 days.
    """

    def __init__(self, ttl_seconds: int = RETENTION_SECONDS):
        self._lock = threading.Lock()
        self._records: dict[str, ConversationRecord] = {}
        self._ttl = ttl_seconds

    def put(self, record: ConversationRecord) -> None:
        self._evict()
        with self._lock:
            self._records[record.conversation_id] = record

    def get(self, conversation_id: str) -> ConversationRecord | None:
        self._evict()
        with self._lock:
            return self._records.get(conversation_id)

    def resolve(self, conversation_id: str, resolution: dict) -> None:
        with self._lock:
            rec = self._records.get(conversation_id)
            if rec:
                rec.resolved = resolution

    def list_active(self) -> list[dict]:
        self._evict()
        with self._lock:
            return [r.to_dict() for r in self._records.values()]

    def list_pending_escalations(self) -> list[dict]:
        self._evict()
        with self._lock:
            return [
                r.to_dict() for r in self._records.values()
                if r.assessment.get("risk_level") == "HIGH_RISK"
                and r.resolved is None
            ]

    def _evict(self) -> None:
        now = time.time()
        with self._lock:
            expired = [
                cid for cid, r in self._records.items()
                if (now - r.created_at) > self._ttl
            ]
            for cid in expired:
                del self._records[cid]

    @property
    def size(self) -> int:
        with self._lock:
            return len(self._records)


_store = ConversationStore()


def record_assessment(
    conversation_id: str,
    messages: list[dict],
    assessment: dict,
    actor: str = "child_classifier",
) -> dict:
    """Record a conversation and its assessment.

    If HIGH_RISK, an audit trail entry is created for HITL escalation.
    CONCERNING and SENSITIVE are also logged but at lower priority.
    SAFE assessments are not logged to the audit trail (privacy-preserving).

    Returns the audit record if logged, or a summary dict.
    """
    record = ConversationRecord(conversation_id, messages, assessment)
    _store.put(record)

    risk_level = assessment.get("risk_level", "SAFE")
    if risk_level in ("HIGH_RISK", "CONCERNING"):
        top_signals = assessment.get("top_signals", [])
        signal_summary = "; ".join(
            f"{s['category']}: {s['description']}" for s in top_signals
        ) or "no specific signals matched"
        rec = core.append_decision(
            ROOT,
            "child-safety",
            f"conversation {conversation_id}: risk_level={risk_level} "
            f"overall={assessment.get('overall')} signals=[{signal_summary}]",
            [
                "ESCALATE to human reviewer (HITL)",
                "allow without human review",
            ],
            f"overall risk {assessment.get('overall')}/10.0, "
            f"by-measure: {assessment.get('by_measure')}. "
            f"False negative misses harm; false positive causes unnecessary review burden.",
            "ESCALATED to human monitor",
            rationale=f"Risk level {risk_level} triggered HITL escalation protocol",
            test_results=json.dumps({
                "overall": assessment.get("overall"),
                "by_measure": assessment.get("by_measure"),
                "signals": top_signals,
            }),
            ai_act_ref="UN CRC Articles 3, 12, 16, 19, 34; EU AI Act (rights-sensitive)",
            model=actor,
            session=conversation_id,
        )
        return {"audit_seq": rec["seq"], "audit_hash": rec["hash"], "conversation_id": conversation_id,
                "risk_level": risk_level, "overall": assessment.get("overall")}

    return {"conversation_id": conversation_id, "risk_level": risk_level,
            "overall": assessment.get("overall"), "audit_logged": False}


def escalate(conversation_id: str, reviewer: str = "monitor") -> dict | None:
    """Force-escalate a conversation for human review (used for manual overrides)."""
    record = _store.get(conversation_id)
    if not record:
        return None
    return record_assessment(
        conversation_id, record.messages, record.assessment, actor=reviewer
    )


def resolve(
    conversation_id: str,
    reviewer: str,
    action: str,
    note: str = "",
) -> dict:
    """Record a human reviewer's resolution of an escalated conversation.

    action options: "confirmed_risk", "false_positive", "actioned", "no_action_needed"
    """
    resolution = {
        "reviewer": reviewer,
        "action": action,
        "note": note,
        "resolved_at": time.time(),
    }
    _store.resolve(conversation_id, resolution)

    rec = core.append_decision(
        ROOT,
        "human-review",
        f"human reviewed escalation for conversation {conversation_id}",
        ["confirmed_risk", "false_positive", "actioned"],
        "Human reviewer disposition closes the HITL loop for this escalation",
        f"REVIEWED by {reviewer}: {action}",
        rationale=note,
        model="human",
        session=conversation_id,
    )
    return {"audit_seq": rec["seq"], "audit_hash": rec["hash"],
            "conversation_id": conversation_id, "action": action}


def pending_escalations() -> list[dict]:
    """Return all un-resolved HIGH_RISK conversations awaiting human review."""
    return _store.list_pending_escalations()


def cleanup_expired() -> int:
    """Force cleanup of expired records. Returns number removed."""
    before = _store.size
    _store._evict()
    return before - _store.size
