# Design — SSGCheck / compliance-auditor

> Status: design, 2026-06-18. Author: team un-ssg-agent.
> Track: AESIA / SpainGov — *Safety, Supervision and Governance in the Agentic World.*
> Implements / pairs with: [`README.md`](../README.md), [`docs/architecture.md`](./architecture.md).

## 1. Overview & goal

SSGCheck extends a coding agent (OpenCode as reference, any MCP host in
principle) with a **compliance gate**: when a developer asks for code that
touches **privacy / security / fairness**, the agent stops *before writing the
first line*, surfaces the known tensions with ≥2 options, lets the **human**
decide, and writes that decision into an **append-only SHA-256 hash chain**.
A human-readable Model Card is rendered from the chain on request.

The load-bearing design decision: **we check the domain, not the code.** Bias is
not visible in source — it lives in the data and surfaces at runtime
(impossibility theorem). So the tool never reads or judges the algorithm. It
triggers on the **context entering the LLM** (the prompt, workspace filenames
like `compas_data.csv`, data schema/headers containing protected attributes),
presents the tradeoff, and audits the developer's **decision process** — not the
mathematical properties of the output.

Honest positioning: this is **non-repudiation infrastructure** — a
pre-construction disclaimer + a tamper-evident logger. It is *strongest* for
privacy/security (deterministic patterns) and *"surface + log"* for fairness
(no verdict, by design).

**Non-goals.**
- ❌ Judging whether code/model is fair or unbiased (impossible; out of scope).
- ❌ Static/dynamic analysis of model math, training data, or runtime outputs.
- ❌ Blocking the developer. The human may always choose "proceed"; we record it.
- ❌ Guaranteeing *completeness* of the log (the gate is prompt-enforced — see §12).
- ❌ Computing fairness metrics (Fairlearn/AIF360) — a possible future, not core.

## 2. Critical User Journeys (CUJs)

The core journey is one flow in four stages (CUJ-1→4), mirroring the four moving
parts: **AGENTS.md intercepts → OpenCode reminds → MCP records → report.**
CUJ-5/6 are the moat (tamper verification) and the portability bonus.

- **CUJ-1 — AGENTS.md intercepts on context (keywords / filenames / schema).**
  Actor: developer in OpenCode. Trigger: a request whose prompt, workspace
  filenames (`compas_data.csv`, `loan_applications.parquet`), or data schema
  contains a sensitive signal (`SELECT *`, protected columns `race/gender/age`,
  high-risk domain words). Steps: the AGENTS.md rules scan the incoming context →
  match the catalog → mark the domain and **do not write code yet**. Success: the
  gate fires on sensitive context and stays silent (no nagging) on benign work.

- **CUJ-2 — OpenCode shows the reminder + options.** Actor: developer. Trigger:
  CUJ-1 fired. Steps: the agent presents the domain, ≥2 options, and the explicit
  tradeoff — parameterised vs interpolation (security); whitelist vs `SELECT *`
  (privacy); the impossibility theorem with a **verbatim EU AI Act Annex III**
  reference (fairness) — then waits. Success: the developer sees the tensions and
  a choice prompt **before any code exists**.

- **CUJ-3 — MCP records the developer's choice.** Actor: developer (chooses) +
  MCP server. Trigger: the developer picks an option. Steps: the model calls the
  `log_decision` tool → the Python server computes the SHA-256 and appends to the
  hash chain → returns success → only then is code generated to match the choice.
  Success: a tamper-evident record exists carrying the human's choice (+ rationale
  + legal anchor); the code is consistent with it. *(Verified live in OpenCode:
  seq 0, hash `16afc727…`.)*

- **CUJ-4 — Generate the human-readable report.** Actor: reviewer / developer at
  session end. Trigger: requests a report (`generate_compliance_report`). Steps:
  render a deterministic Model Card from the chain, anchored to the verified head
  hash. Success: a Markdown report listing every decision, options, implications,
  choice, and legal anchor, plus the honest-limitations section.

- **CUJ-5 — Independent tamper verification (the moat).** Actor: auditor /
  regulator / judge. Trigger: receives `decisions.jsonl` and wants to trust it.
  Steps: runs `core.py verify` (or `tamper_demo.py`) → walks the chain → reports
  intact, or localises the first altered/inserted/removed record by `seq`.
  Success: any hand-edit is caught and pinpointed offline with stdlib only —
  including a "smart" forger who recomputes a *middle* record's own hash (caught
  at the next link). The one residual gap (recomputing the *head's* hash) is the
  documented reason to anchor the head externally (§13, M6).

- **CUJ-6 — Cross-agent portability (bonus).** Actor: a team using Cline/Aider
  instead of OpenCode. Trigger: points their MCP config at the same `server.py`
  and loads `AGENTS.md` as instructions. Success: the same gate + record + report
  behaviour with the auditor unchanged — not tied to one agent or model vendor.

## 3. Feature list

| Feature | Serves | Notes |
|---|---|---|
| F1 — Context-trigger gate rules (keyword/intent/schema catalog) | CUJ-1 | Lives in `AGENTS.md`, injected every call |
| F2 — `log_decision` tool → append-only hash chain | CUJ-3 | Model calls; Python computes the hash |
| F3 — Tamper-evident chain + independent verifier | CUJ-5 | SHA-256 prev-hash links |
| F4 — Deterministic Model Card renderer | CUJ-4 | Built from the chain, no LLM |
| F5 — MCP server exposing 3 tools | CUJ-3,4,5 | `log_decision`, `verify_audit_trail`, `generate_compliance_report` |
| F6 — OpenCode mounting (config + uv launch) | CUJ-1,2,6 | `opencode.json` |
| F7 — Cross-agent portability (MCP + plain Markdown) | CUJ-6 | No vendor lock-in |
| F8 — Verifiable demo harness (no OpenCode needed) | CUJ-2,3 | `demo.py` + `llm_client.py` |
| F9 — Self-test + tamper demo proving detection | CUJ-5 | `selftest.py`, `tamper_demo.py` |
| F10 — Verbatim legal-citation table (planned) | CUJ-2 | Make every domain cite a real article, not model memory |

## 4. Requirements

**Functional**

| # | Requirement | Feature |
|---|---|---|
| FR-1 | On a sensitive request, the agent presents ≥2 options with explicit tradeoffs *before* generating code | F1 |
| FR-2 | The decision (domain, trigger, options, implications, choice, rationale, ai_act_ref) is written as one JSONL record | F2 |
| FR-3 | Each record stores `prev_hash` and `hash = SHA-256(canonical(record\hash))`; genesis = 64 zeros | F2,F3 |
| FR-4 | A verifier recomputes the whole chain and reports the first broken `seq`, distinguishing *content altered* from *inserted/removed/reordered* | F3 |
| FR-5 | The model never writes the log nor computes a hash; only the tool may | F2,F5 |
| FR-6 | A report renders the chain into a Model Card with system id, decisions log, known limitations, traceability | F4 |
| FR-7 | The three capabilities are exposed as MCP tools usable by any MCP host | F5,F7 |
| FR-8 | The MCP server launches from `opencode.json` and loads `AGENTS.md` as instructions | F6 |
| FR-9 | If `log_decision` fails, the agent must not proceed to code generation (fail-closed) | F2 |

**Non-functional** (measurable)

| # | Requirement | Threshold | Feature |
|---|---|---|---|
| NFR-1 | Append latency (in-process) | < 50 ms for chains ≤ 10k entries | F2 |
| NFR-2 | Verify latency | < 1 s for ≤ 10k entries | F3 |
| NFR-3 | Core has zero third-party deps | `core.py` imports stdlib only | F3,F4 |
| NFR-4 | Verifier is reproducible offline | no network, no key, stdlib `python3` | F3 |
| NFR-5 | Demo provider resilience | succeeds if ≥1 of DeepSeek/OpenAI/Gemini is reachable | F8 |
| NFR-6 | Secrets never committed/echoed | `.env` gitignored; tool refuses to read `.env` | F1 |

## 5. Infra

| Need | Exists? | Where / new |
|---|---|---|
| Python ≥3.11 runtime, uv project | ✅ | `pyproject.toml`, `uv.lock` |
| MCP server framework | ✅ | `mcp` dep; `server.py` uses `FastMCP` |
| Append-only storage | ✅ | `audit-trail/decisions.jsonl` (plain file) |
| LLM access for demo | ✅ | `llm_client.py` (OpenAI-compatible, keys in `.env`) |
| OpenCode host | ✅ (external) | installed via brew/npm; reads `opencode.json` |
| Legal reference table | ➕ new | planned `instructions/legal.md` or in-catalog (F10) |
| Cross-agent adapters | ➕ new | Cline/Aider config snippets (M5) |

## 6. Components

### C1 — Compliance gate (rules)
- **Responsibility:** detect sensitive context and force the present→choose→log
  sequence before code generation.
- **Reuses:** `AGENTS.md:8` (when the gate fires), `AGENTS.md:14` (protected
  columns), `AGENTS.md:19` (cybersecurity signals), `AGENTS.md:24` (fairness /
  AI Act Annex III), `AGENTS.md:29` (the CRITICAL must-do sequence), `AGENTS.md:48`
  (hard rules — never read `.env`, never compute a hash).
- **New:** F10 verbatim legal table; expanded keyword catalog.
- **Interface:** Markdown injected via `opencode.json:3` `instructions`.

### C2 — Audit core (hash chain)
- **Responsibility:** deterministic append + canonicalisation; the integrity guarantee.
- **Reuses:** `core.py:27` `GENESIS`, `core.py:34` `_canonical` (the pre-image
  contract), `core.py:42` `_read_all`, `core.py:54` `append_decision`.
- **New:** —. (Stable; only field additions if FR-2 grows.)
- **Interface:**
  ```python
  def append_decision(root, domain, trigger, options, implications,
                      user_choice, rationale="", test_results="",
                      ai_act_ref="", model="", session="") -> dict   # core.py:54
  def _canonical(record: dict) -> str                                # core.py:34
  ```

### C3 — MCP server (tool surface)
- **Responsibility:** expose core to any MCP host as 3 tools.
- **Reuses:** `server.py:23` `log_decision`, `server.py:50` `verify_audit_trail`,
  `server.py:58` `generate_compliance_report`; each delegates to C2/C4/C5.
- **New:** —.
- **Interface (MCP tool):**
  ```python
  log_decision(domain, trigger, options_presented: list, implications,
               user_choice, rationale="", test_results="", ai_act_ref="",
               model="", session="") -> str        # server.py:23
  ```

### C4 — Report renderer (Model Card)
- **Responsibility:** project the chain into a human-readable, traceable report.
- **Reuses:** `core.py:117` `render_model_card` (sections: system id, decisions
  log, known limitations, traceability); anchors to `verify_chain` head hash.
- **New:** richer Model Card sections (training-data/purpose/risks) per challenge
  template (M4); optional clearly-labelled LLM narrative (non-authoritative).
- **Interface:** `render_model_card(root: str) -> str`  # core.py:117

### C5 — Verifier
- **Responsibility:** independent tamper check + localisation.
- **Reuses:** `core.py:96` `verify_chain`, `core.py:199` `_cli` (`verify`/`report`
  CLI entry).
- **New:** —.
- **Interface:** `verify_chain(root) -> (ok: bool, msg: str, count: int, head: str)`  # core.py:96

### C6 — Demo / portability harness
- **Responsibility:** prove the full gate flow without OpenCode; exercise providers.
- **Reuses:** `demo.py:30` `LOG_TOOL`, `demo.py:53` `SCENARIOS`, `demo.py:60`
  `run_scenario`, `demo.py:103` `main`; `llm_client.py:37` `PROVIDERS`,
  `llm_client.py:60` `chat`, `llm_client.py:22` `load_env`.
- **New:** Cline/Aider config snippets (M5).
- **Interface:** `chat(messages, tools=None, temperature=0.0) -> (msg, provider)`  # llm_client.py:60

### C7 — Self-test & tamper demo
- **Responsibility:** CI-grade proof that honest chains verify and forgeries are caught (CUJ-5).
- **Reuses:** `selftest.py` (writes 3 decisions, verifies, tampers `seq 0`, re-verifies);
  `tamper_demo.py` (flip / garble / delete / smart-forge / head-recompute caveat — all narrated).
- **New:** wire both into a `uv run` test target (M3).

## 7. Interfaces with other modules

| Direction | Module | Symbol / signature | Purpose |
|---|---|---|---|
| ← called by | OpenCode host | `opencode.json:4` `mcp.compliance-auditor` → `command: ["uv","run","python",".../server.py"]` (`opencode.json:7`) | host launches the MCP server |
| ← called by | OpenCode host | `opencode.json:3` `instructions: ["AGENTS.md"]` | host injects gate rules |
| calls → | MCP / model | tool schema `log_decision(...)` (`server.py:23`, mirrored in `demo.py:30`) | model records the decision |
| internal | C3 → C2 | `core.append_decision(...)` (`core.py:54`) | tool persists to chain |
| internal | C3 → C5 | `core.verify_chain(...)` (`core.py:96`) | tool/CLI verifies |
| internal | C3 → C4 | `core.render_model_card(...)` (`core.py:117`) | tool/CLI renders report |
| calls → | provider HTTP | `llm_client.chat` → `POST {base}/chat/completions` (`llm_client.py:49,60`) | demo only |

**Canonicalisation contract (the one that prevents integration bugs).**
`append_decision` and `verify_chain` MUST both hash via `_canonical` (`core.py:34`):
record minus its own `hash`, `json.dumps(sort_keys=True, separators=(",",":"),
ensure_ascii=False)`, UTF-8. Any divergence → every verify fails.

## 8. Main algorithms

### Append (core.py:54)
```
1. entries = _read_all(root)
2. prev_hash = entries[-1].hash if entries else GENESIS;  seq = prev.seq+1 or 0
3. record = {seq, ts(UTC iso), domain, trigger, options_presented,
             implications, user_choice, rationale, test_results,
             ai_act_ref, model, session, prev_hash}
4. record.hash = sha256(_canonical(record)).hexdigest()
5. append json line (ensure_ascii=False) to decisions.jsonl
```
Invariants: file is only ever appended; `seq` is dense and monotonic; `hash`
excluded from its own pre-image. Edge cases: empty file → genesis; non-ASCII
preserved identically in hash and on disk.

### Verify (core.py:96)
```
prev = GENESIS
for rec in entries (in file order):
    if rec.prev_hash != prev:      -> BROKEN (inserted/removed/reordered) at rec.seq
    if rec.hash != sha256(_canonical(rec)): -> BROKEN (content altered) at rec.seq
    prev = rec.hash
return OK, count, head=prev
```
Invariants: a single edit breaks the local hash AND every downstream link.
Edge cases: empty → OK/genesis; trailing blank lines ignored (`_read_all`).

### Gate decision flow (AGENTS.md:29, enforced in prompt; mirrored in demo.py:60)
```
on user request:
  scan prompt + workspace filenames + schema for catalog signals (privacy/security/fairness)
  if no signal: behave normally (no nagging)
  else:
    do NOT generate code
    present >=2 options + implications (+ verbatim ai_act_ref for fairness)
    wait for human choice
    call log_decision(...)            # tool computes hash
    only on success -> generate code consistent with the choice
```
Invariant: code generation is gated behind a successful `log_decision`. Edge
case: concealed intent (no signal) → no trigger (accepted non-goal, §1/§12).

## 9. Integration / E2E tests

| Test | CUJ | Setup → Action → Assertion |
|---|---|---|
| E2E-1 | CUJ-1 | benign request → no gate; a request mentioning `compas_data.csv` / `SELECT *` / a `race` column → gate fires, **no code written yet** |
| E2E-2 | CUJ-2 | SQL-interpolation request → OpenCode presents ≥2 options + the SQL-injection tradeoff **before** any code *(verified live)* |
| E2E-3 | CUJ-3 | choose an option → `log_decision` appends a record; `verify` OK *(verified live: seq 0 hash `16afc727…`)*; fairness variant carries `ai_act_ref`, no verdict asserted |
| E2E-4 | CUJ-4 | populated trail → `core.py report` → Model Card lists every decision + head hash + limitations section |
| E2E-5 | CUJ-5 | `selftest.py` + `tamper_demo.py`: flip / garble / delete / smart-forge each caught at the exact `seq`; head-recompute caveat shown *(all passing today)* |
| E2E-6 | CUJ-6 | point a second MCP host (Cline/Aider config) at `server.py` + `AGENTS.md` → same gate+record behaviour, auditor unchanged |

## 10. Success criteria
- [ ] All FR-1…FR-9 met.
- [ ] NFR-1…NFR-6 thresholds hit (§4) — esp. core stdlib-only + offline verify.
- [ ] Every CUJ has a passing E2E test (§9); E2E-2, E2E-3 and E2E-5 already pass.
- [ ] Six required deliverables present: `AGENTS.md`, `opencode.json`, `README.md`,
      `docs/architecture.md`, `audit-trail/decisions.jsonl`, human-readable report.
- [ ] Bonuses demonstrated: hash chain (✅) + cross-agent portability (E2E-6).

## 11. Performance considerations
Hot path: `append_decision` reads the whole file to get the tail
(`_read_all`, core.py:42) — O(n) per append. Budget NFR-1 (<50 ms at 10k) holds
for hackathon scale; if a trail ever exceeds ~10⁵ entries, read only the last
line for `prev_hash` instead of all. Verify is O(n) SHA-256 — measure with a
10k-entry fixture. Report is O(n) string build. No network on any audited path
(only `demo.py`).

## 12. Reliability considerations
Failure modes: (a) `log_decision` write fails → **fail-closed**: agent must not
generate code (FR-9). (b) Concurrent appends could race on `prev_hash`
(single-developer assumption holds; if multi-writer needed, add an OS file lock
around read+append). (c) Model skips the gate → **no record** — the chain proves
integrity of what's logged, **not completeness**; this is a stated non-goal and
the report's limitations section says so. Recovery: the trail is plain
append-only JSONL — partial/last-line corruption is isolated; `verify` localises
it. Idempotency: appends are not idempotent (each is a new `seq`); duplicate
decisions are visible, not merged.

## 13. Security considerations
Trust boundaries: the model is **untrusted** for integrity — it never writes the
log or a hash (FR-5); the Python server is the only writer. Inputs to validate:
tool args are persisted verbatim (treated as data, not executed); `domain`
constrained to privacy|security|fairness in the tool schema (`demo.py:30`).
Secrets: `AGENTS.md:48` forbids reading `.env`; `.env` is gitignored and never
echoed (NFR-6). Tamper resistance: SHA-256 prev-hash chain detects edits but is
not signed — a holder of the whole file could recompute a consistent forged
chain; future hardening = sign the head hash or anchor it externally (M6, noted
honestly). Sandboxing: server is a local subprocess launched via `uv run`
(`opencode.json:7`).

## 14. Abstraction & reuse

**Approach.** Three thin layers with a hard trust boundary: (1) *rules* in plain
Markdown (`AGENTS.md`) so any agent can ingest them; (2) a *deterministic core*
(`core.py`, stdlib-only) that owns all integrity-critical logic; (3) a *thin MCP
adapter* (`server.py`) that exposes the core. The model orchestrates; it never
holds integrity. Everything reusable already exists — the design is mostly
*assembling and hardening*, not inventing.

**Reuse map (existing code to call):**

| Symbol | Location | How we use it |
|---|---|---|
| `_canonical` | `core.py:34` | single source of truth for the hash pre-image (append + verify) |
| `append_decision` | `core.py:54` | the only writer of the chain |
| `verify_chain` | `core.py:96` | tamper check + localisation (CUJ-4) |
| `render_model_card` | `core.py:117` | report renderer (CUJ-5) |
| `_cli` | `core.py:199` | offline `verify`/`report` entry for reviewers |
| `log_decision` (tool) | `server.py:23` | model-facing record API |
| `verify_audit_trail` / `generate_compliance_report` | `server.py:50,58` | tool-facing verify/report |
| gate rules + catalog | `AGENTS.md:8,14,19,24,29,48` | trigger + sequence + hard rules |
| `mcp` + `instructions` | `opencode.json:4,3` | host mounts server + injects rules |
| `chat` / `PROVIDERS` / `load_env` | `llm_client.py:60,37,22` | demo + portability harness |
| `LOG_TOOL` / `run_scenario` | `demo.py:30,60` | OpenCode-free E2E driver |

**New abstractions (justified):**
- *Legal-citation table* (F10) — verbatim article text keyed by domain, so
  citations are retrieved, not recalled by the model (prevents hallucinated
  article numbers). Justified by FR-1 + CUJ-3 credibility.
- *Cross-agent config snippets* (M5) — Cline/Aider equivalents of
  `opencode.json` + instructions. Justified by CUJ-6 / the portability bonus.
- (Deferred) *deterministic security/privacy detectors* — real pattern/taint
  checks to strengthen triggers beyond keywords (M6). Justified only if time
  allows; not required for the core thesis.

---

## Roadmap

Risk-up-front: the integrity core (the only hard part) is already built and
verified, so the remaining milestones are additive and independently shippable.

- **M0 — Audit core + tamper-evidence.** ✅ DONE. Delivers C2, C5, F2, F3 (FR-2..5).
  Depends: —. Verified by **E2E-5** (`selftest.py` + `tamper_demo.py`: honest
  verifies; flip/garble/delete/smart-forge each caught at the exact `seq`).
- **M1 — MCP server + gate.** ✅ DONE. Delivers C1, C3, F1, F5, F6 (FR-1,6,7,8).
  Depends: M0. Verified by **E2E-1** (gate fires) + **E2E-4** (report renders) +
  tool registration.
- **M2 — Live OpenCode run.** ✅ DONE. Delivers F6 end-to-end + F8 (CUJ-1,2,3).
  Depends: M1. Verified by **E2E-2** + **E2E-3** (live: reminder shown,
  `domain=security` record, hash `16afc727…`).
- **M3 — Verbatim legal table + catalog hardening.** Delivers F10, expanded C1,
  CI test target. Depends: M1. Verified by **E2E-3** (every record carries a real
  `ai_act_ref`). *Risk: keyword coverage — log what the catalog does NOT cover
  (honesty over silent gaps).*
- **M4 — Model Card completeness.** Delivers richer C4 (purpose / training-data /
  foreseeable-risks / human-oversight sections per challenge template), optional
  labelled LLM narrative. Depends: M0. Verified by **E2E-4** (all template
  sections present, anchored to head hash).
- **M5 — Cross-agent portability.** Delivers F7 + Cline/Aider config snippets +
  docs. Depends: M1. Verified by **E2E-6** (second host, auditor unchanged) —
  secures the portability bonus.
- **M6 — (Stretch) hardening + detectors.** Sign/anchor the head hash (closes the
  `tamper_demo.py` case 5 gap); optional deterministic security/privacy taint
  detectors to strengthen triggers. Depends: M0/M3. Verified by extended **E2E-5**
  (signature check) + new detector unit tests. *Optional — the thesis stands without it.*
- **M7 — Submission polish.** README/architecture cross-links, demo recording,
  final `verify` + report artifacts committed. Depends: M3–M5. Verified by the
  §10 deliverables checklist.
