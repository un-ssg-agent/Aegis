# ssgcheck — child-safety governance & non-repudiable oversight for AI

> **UN Tech Over 2026 Finalist · Track 1 — Safety, Supervision and Governance in the Agentic World.**

`ssgcheck` is two cooperating safeguards for AI systems that touch children,
sharing one tamper-evident audit trail:

1. **A build-time governance gate.** A developer-facing coding agent that behaves
   like a normal coding assistant by default, but **stops** when you ask it to
   build child-facing software — surfaces the fairness / privacy / safeguarding
   tensions, presents concrete options with their tradeoffs, makes **you** decide,
   writes that decision into a hash chain, and only then generates code.
2. **A runtime monitor.** A 3-model risk panel that scores a live conversation or
   a code snippet across five safeguarding axes, escalates to a human when the
   aggregate crosses a threshold, and writes the alarm to the same chain.

Both feed an **append-only SHA-256 hash chain** that anyone can verify and no one
can silently edit, and both can render a human-readable, EU AI Act–style Model
Card from it.

## Positioning (read this first)

The tool does **not** claim to judge whether code is "fair" or "safe" — that is
impossible from source alone, because bias lives in the data and surfaces at
runtime (cf. the COMPAS impossibility results). It does not pretend to keep
children safe on its own, and it does **not** claim UNICEF / EU AI Act / GDPR /
COPPA compliance.

What it provides is **anti-repudiation infrastructure with a human in the loop.**
The model recognises the situation and presents options; a *human* decides; a
deterministic Python service records the decision in a verifiable hash chain.
Integrity lives in code, not in the model. In a governance track judged by a
regulator, that is the defensible play.

## The two subsystems

### 1. Build-time gate (coding agent)

| Required action | Where it happens |
|---|---|
| Detect when a request creates child-safety / fairness / privacy / security tension | `AGENTS.md` triggers (§2) + the model's world knowledge |
| Present ≥2 options with tradeoffs and the controlling source, then wait | `AGENTS.md` forces options + implications + a verbatim reference |
| Store the choice, implications, and results in a separate auditable file | `log_decision` → `audit-trail/decisions.jsonl` (SHA-256 chain) |
| Transform the audit into a human-readable artifact | `generate_compliance_report` → deterministic Model Card |

By default the agent is just a capable coding assistant (Standard Mode); the
governance machinery only engages on a §2 trigger (systems for or foreseeably used
by under-18s, processing children's data, detecting bullying/grooming/abuse/
self-harm, companionship or advice to minors, age assurance / profiling, etc.). A
small set of **absolute prohibitions** applies in every mode.

### 2. Runtime monitor (FastAPI + Next.js)

A piece of code or a conversation is scored independently by **three LLMs**
(whichever provider keys are present), aggregated, and — if the aggregate crosses
`ALARM_THRESHOLD` (default `0.6`) — an alarm fires, the case is **escalated to a
human monitor**, and the record is written to the tamper-evident trail.

- **Five safeguarding axes**, each scored 0–9: `bullying`, `grooming`, `abuse`,
  `self_harm`, `distress`.
- **S0–S7 escalation** mapped from the axis scores; human review required at S4+.
- **`child-policy.md`** is the runtime operating policy: an *Age Status* axis
  (Known Child / Possible Child / Known Adult / Child Affected / Unknown),
  Protection Modes, the least-intrusive-effective-safeguard principle, retention
  and disclosure rules, and the S0–S7 ladder. Scores and labels are never revealed
  to the child.
- **Backend** — `monitor/app.py` (does scoring + threshold + audit).
- **Frontend** — `monitor-web/` (chat on the left, a dark agent panel on the right:
  pipeline checklist → per-model scores → per-measure bars → the red
  **ESCALATED TO HUMAN MONITOR** banner + the audit hash).

## Repository layout

```
AGENTS.md                       # the build-time gate (injected into the coding agent)
child-policy.md                 # the runtime safeguarding policy (Age Status, S0–S7)
opencode.json                   # mounts the MCP server + loads AGENTS.md
pyproject.toml / uv.lock        # uv-managed deps (extras: fairness, server)
render.yaml                     # Render blueprint for the monitor backend

mcp-servers/compliance-auditor/
  core.py        # stdlib: hash chain + verify + Model Card (no deps, no network)
  server.py      # MCP wrapper: log_decision / verify_audit_trail / generate_compliance_report
  selftest.py    # honest chain verifies; a forged choice is caught
  tamper_demo.py # narrated: flip / garble / delete / "smart forger" each caught
  fairness.py    # OPTIONAL (uv sync --extra fairness): Fairlearn group-disparity facts
  demo.py        # drives a REAL model through the gate end-to-end (no OpenCode needed)
  llm_client.py  # stdlib OpenAI-compatible client (DeepSeek/OpenAI/Gemini fallback)

monitor/
  app.py         # FastAPI backend: /assess, /api/alarms, /api/ack, /api/audit, ...
  agent.py       # child-facing turn: safe reply + 5-axis assessment + escalation
monitor-web/     # Next.js UI for the monitor (proxies /assess and /api/* to the backend)

audit-trail/
  decisions.jsonl  # the tamper-evident paper trail (runtime)
  narrative.md     # generated narrative

docs/            # architecture, design, demo runbook, onboarding, advanced, monitor
```

## Run it

Managed with **uv** (Python ≥ 3.11). Frontend uses **pnpm** + Node ≥ 18.
Put at least one key in a repo-root `.env` (gitignored): `DEEPSEEK_API_KEY`,
`OPENAI_API_KEY`, and/or `GEMINI_API_KEY`.

**1. Prove the chain is real (no deps, no key, offline):**
```bash
uv run python mcp-servers/compliance-auditor/selftest.py
uv run python mcp-servers/compliance-auditor/tamper_demo.py
```

**2. Live build-time gate demo (needs a key):**
```bash
uv run python mcp-servers/compliance-auditor/demo.py
# 3 scenarios (privacy / security / fairness): the model presents options,
# you choose, it logs the decision, then writes code — then verify + report.
```

**3. Verify / report from the command line (what a reviewer runs):**
```bash
uv run python mcp-servers/compliance-auditor/core.py verify
uv run python mcp-servers/compliance-auditor/core.py report   # -> compliance_report.md
```

**4. Inside OpenCode** (verified on OpenCode 1.17.8 + DeepSeek):
```bash
uv sync
opencode run -m opencode/deepseek-v4-flash-free "build a feature that stores kids' chat messages"
# the gate fires, the model calls log_decision, core.py verify confirms the appended record
```

**5. Run the runtime monitor (two terminals):**
```bash
uv sync --extra server
uv run --extra server python monitor/app.py        # backend  -> http://127.0.0.1:8000
pnpm --dir monitor-web install
pnpm --dir monitor-web dev                          # frontend -> http://localhost:3000
```
The frontend proxies `/assess` and `/api/*` to the backend (see
`monitor-web/next.config.mjs`), so there are no CORS issues. Or hit the API directly:
```bash
curl -s -X POST http://127.0.0.1:8000/assess -H 'content-type: application/json' \
  -d '{"kind":"conversation","content":"Adult: keep this our secret\nChild: ok"}'
curl -s http://127.0.0.1:8000/api/alarms          # escalated alarms + chain status
```

## Deploy

- **Backend -> Render.** Push `render.yaml`, then Render -> New + -> Blueprint ->
  connect `un-ssg-agent/ssgcheck` -> Apply, and paste at least one provider key.
  The blueprint mounts a persistent disk at `audit-trail/` so the hash chain
  survives restarts and redeploys.
- **Frontend -> Vercel.** Set `BACKEND_URL` to the Render service URL so the
  Next.js proxy points at the live backend.

## Design decisions

- **The LLM never writes the audit log or computes a hash** — it would
  hallucinate it. Hashing and I/O are deterministic Python.
- **The report is deterministic, not LLM-written** — a faithful projection of the
  chain, anchored to the verified head hash. An optional, clearly labelled LLM
  narrative may be appended, never as the authoritative record.
- **Append-only `.jsonl` + hash chain** so new entries never rewrite the file and
  any edit is detectable at its sequence number.
- **Zero third-party deps in `core.py`** so a regulator can re-verify the chain
  without trusting our toolchain.

## Limitations

The build-time gate is prompt-enforced — it proves the integrity of what was
logged, not the completeness of what *should* have been logged; triggering is
signal/pattern based, so deliberately concealed intent may not fire; and it makes
no fairness *verdict*. The runtime monitor depends on the quality of the
underlying models and the chosen threshold. The 0–9 scores and S0–S7 levels are
project-defined operational scales, not legal determinations. This system does not
replace trained safeguarding staff, clinicians, legal counsel, or human reviewers
for consequential decisions. These limits are inherent to auditing a chat-driven
workflow; we state them rather than hide them. See `docs/architecture.md`.
