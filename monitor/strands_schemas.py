"""Typed output contracts for the Strands rebuild of the coding-agent gate and
the child-facing chat. These mirror the existing JSON shapes the frontend
(monitor-web/app/page.tsx) already expects byte-for-byte — field names, types,
and optionality all match the `Gate` / `Code` / `Assessment` TS types there, so
the frontend needs zero changes when this backend swaps in.

Why structured_output_model instead of regex/markers:
The old agent.py parsed the model's raw text with a regex hunting for `{.*}`,
plus a custom <<<AEGIS_CODE>>> marker to dodge JSON-escaping issues with long
code bodies. Strands' `structured_output_model` constrains the model's output
to a schema directly (the SDK handles the tool-call-style enforcement under
the hood), so neither the regex nor the marker hack is needed: invalid output
is a validation error Strands surfaces, not a silent `None` from a failed
regex match.
"""
from __future__ import annotations

from pydantic import BaseModel, Field


# ───────────────────────── coding-agent gate (developer-facing) ─────────────────────────

class Opt(BaseModel):
    id: str
    label: str
    tradeoff: str


class Decision(BaseModel):
    id: str = Field(description="One of: escalation | retention | evaluation")
    question: str
    source: str = Field(description="Verbatim EU AI Act / UN CRC anchor")
    options: list[Opt]


class GateOutput(BaseModel):
    """CASE A — the child-safety gate fires; pause before writing code."""
    message: str = Field(description="<=2 sentences: what was detected and why")
    flagged: list[str]
    decisions: list[Decision]


class Citation(BaseModel):
    tag: str
    text: str


class AuditBlock(BaseModel):
    trigger: str
    options_presented: list[str]
    choice: str
    rationale: str
    ai_act_ref: str
    configured_review_policy: str = "later"
    choice_status: str = "approved"


class CodeOutput(BaseModel):
    """CASE B — ordinary dev work, or the developer has chosen gate options."""
    message: str = Field(description="<=2 sentences")
    language: str
    code: str = Field(description="The complete, runnable program. No placeholders, "
                                   "stubs, TODOs, or dummy return values — a real, "
                                   "working artifact per the IMPLEMENTATION STANDARD.")
    explanation: str
    citations: list[Citation] = Field(default_factory=list)
    audit: AuditBlock | None = Field(
        default=None,
        description="Include ONLY when the gate fired for this turn (child-directed "
                    "work); omit for ordinary code.")


# ───────────────────────── child-facing safeguarding chat ─────────────────────────

class Axis(BaseModel):
    score: int = Field(ge=0, le=9)
    reason: str


class ChildAssessment(BaseModel):
    bullying: Axis
    grooming: Axis
    abuse: Axis
    self_harm: Axis
    distress: Axis


class ChildChatOutput(BaseModel):
    reply: str = Field(description="The ONLY field the child ever sees. Never include "
                                    "scores, labels, or S-levels here.")
    assessment: ChildAssessment
    urgency: int = Field(ge=0, le=9, default=0)
    confidence: str = Field(default="Medium", description="Low|Medium|High")
    pattern: str = Field(default="Unknown",
                          description="Isolated|Repeated|Sustained|Escalating|Unknown")
    escalation: str = Field(default="S0", description="S0-S7")
    primary_concern: str = Field(
        default="None",
        description="Bullying|Grooming|Abuse|Self-Harm|Distress|Urgent Safety|None")
    secondary_concerns: list[str] = Field(default_factory=list)
    human_review: bool = False
    age_status: str = Field(
        default="possible_child",
        description="known_child|possible_child|known_adult|child_affected|unknown")
    requester_role: str = Field(
        default="child_self",
        description="child_self|worried_friend|parent_or_caregiver|teacher_or_educator|unknown")
    affected_person_role: str = Field(
        default="child_self",
        description="child_self|specific_child|group_of_children|unknown")
    response_decision: str = Field(
        default="",
        description="One short sentence: what was included/avoided in the reply")
    detected_language: str = Field(default="und", description="BCP-47 code, or 'und'")
    language_confidence: str = Field(default="high", description="high|medium|low")