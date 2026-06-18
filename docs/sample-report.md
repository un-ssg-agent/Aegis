# Compliance Model Card

_Auto-generated from the tamper-evident audit trail. Every claim below is traceable to `audit-trail/decisions.jsonl`._

## 1. System identification
- Generated at: `2026-06-18T20:40:16.157544+00:00`
- Audit chain status: **✅ INTACT**
- Chain head hash: `16afc727975784a84286139827c94374187068bf8003751bc4c911b4fe959bc3`
- Decisions recorded: **1**  (security: 1)

## 2. Purpose & scope
This record documents the fairness / privacy / cybersecurity tensions surfaced to the developer during AI-assisted code generation, and the human decisions made at each one. It does **not** certify that the resulting system is fair or secure — it certifies what was flagged, what choices were offered, and what the human decided.

## 3. Decisions log (human oversight)
| seq | time (UTC) | domain | trigger | choice | legal anchor |
|----:|------------|--------|---------|--------|--------------|
| 0 | 2026-06-18T20:39:49.083973+00:00 | security | SQL query built by string interpolation from user input (username) | **A. Parameterized query / prepared statement** |  |

### Decision details
#### seq 0 — security: SQL query built by string interpolation from user input (username)
- Options presented: ['A. Parameterized query / prepared statement', 'B. Keep string interpolation with manual sanitization', 'C. Use an ORM query builder']
- Implications / tradeoff: A: Safe against SQL injection, industry standard. B: Risk of incomplete escaping, injection possible. C: Safe with additional schema validation, but adds library dependency.
- **Developer chose:** A. Parameterized query / prepared statement
- Rationale: Developer chose the safest and most standard approach to prevent SQL injection.
- Record hash: `16afc727975784a84286139827c94374187068bf8003751bc4c911b4fe959bc3`

## 4. Known limitations
- The compliance gate is **prompt-enforced**: the chain proves that *what was logged* was not altered, but cannot prove that *everything that should have been logged* was logged. A model that skips the gate leaves no record — by design this tool audits disclosed decisions, like any audit.
- Detection is keyword/pattern based; concealed intent (unnamed columns, no domain words) will not trigger.
- This tool makes no fairness judgement; fairness outcomes are measurable only at runtime on real data.

## 5. Traceability
- Raw evidence: `audit-trail/decisions.jsonl` (append-only, SHA-256 hash chain).
- Verify independently: `python3 mcp-servers/compliance-auditor/core.py verify`

<!-- Optional: an LLM-written narrative MAY be appended below, clearly labelled as non-authoritative. The verifiable facts are those above, anchored to the chain head hash. -->
