"""Child-safety chat classifier — rule-based risk assessment for minor-to-chatbot conversations.

Provides:
  - classify_message(text, conversation_id=None, metadata=None) -> dict
  - classify_conversation(messages, conversation_id=None, metadata=None) -> dict
  - pending_escalations() -> list[dict]
  - resolve_escalation(conversation_id, reviewer, action, note) -> dict
  - patterns module (for inspection/extension)
  - scoring module (low-level scoring functions)
  - audit module (audit trail integration)

Risk scale: 1.0 (safe) to 10.0 (severe imminent risk)
  SAFE:       1.0-4.9
  SENSITIVE:  5.0-6.9
  CONCERNING: 7.0-8.9
  HIGH_RISK:  9.0-10.0  (-> HITL escalation)

Categories: self_harm, grooming, bullying, sexual_exploitation,
            violence, pii_exposure, discrimination, distress
"""

from .classifier import (
    classify_message,
    classify_conversation,
    pending_escalations,
    resolve_escalation,
)
from . import patterns
from . import scoring
from . import audit

__all__ = [
    "classify_message",
    "classify_conversation",
    "pending_escalations",
    "resolve_escalation",
    "patterns",
    "scoring",
    "audit",
]
