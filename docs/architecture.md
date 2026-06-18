# Architecture

## One sentence

A coding-agent extension that, on sensitive requests, makes the model **stop,
surface the known tensions, let the human choose, and record that choice in a
tamper-evident hash chain** — then generate code. It does **not** judge whether
code is fair or secure; it produces non-repudiable evidence of human oversight.

## Why this shape (the load-bearing design decision)

Bias and most security flaws are **not visible in the source code** — they live
in the data and only manifest at runtime. So a tool that "reads the code and
judges fairness" is impossible. We therefore split the system by capability:

| Concern | Who owns it | Can it be wrong? |
|---|---|---|
| Recognise a sensitive situation, present tradeoffs | the **LLM** (world knowledge + the rules in `AGENTS.md`) | yes — that's fine, it's advisory ("might") |
| Compute the hash, write the file, verify the chain | the **Python MCP server** (deterministic) | **no — must be exact** |
| Decide which tradeoff to accept | the **human developer** | it's a value judgement, by design |

The model is a chat process; it **cannot reliably compute SHA-256** and will
hallucinate a hash if asked to "write" a log line. So the model never writes
the audit log — it only calls a tool. The integrity guarantee lives entirely
in code, not in the model.

## Components

```
                      ┌─────────────────────────────────────────┐
   developer request  │  Coding agent (OpenCode / any MCP host)  │
  ───────────────────▶│   + AGENTS.md  (the compliance gate)     │
                      └───────────────┬──────────────────────────┘
                                      │ 1. sensitive signal?
                                      │    (intent / filename / schema keywords)
                                      ▼
                      ┌──────────────────────────────────────────┐
                      │  GATE (prompt-enforced, in AGENTS.md):    │
                      │  • don't generate code yet                │
                      │  • present ≥2 options + tradeoffs         │
                      │  • cite AI Act ref (verbatim, not recalled)│
                      │  • WAIT for the human to choose           │
                      └───────────────┬──────────────────────────┘
                                      │ 2. human chooses
                                      ▼
                      ┌──────────────────────────────────────────┐
                      │  MCP tool  log_decision(...)              │   ← model calls,
                      │  → compliance-auditor (Python, stdlib)    │     never writes
                      └───────────────┬──────────────────────────┘
                                      │ 3. deterministic
                                      ▼
        audit-trail/decisions.jsonl  ──  append-only SHA-256 hash chain
            seq N: { ..., prev_hash, hash = sha256(canonical(record)) }
                                      │
                  ┌───────────────────┼────────────────────┐
                  ▼                                          ▼
          verify_audit_trail()                      generate_compliance_report()
       recompute every link,                     deterministic Model Card,
       localise any tamper                        anchored to the chain head
```

After the tool returns success, the agent generates code consistent with the
chosen option (step 4).

## The hash chain

Each record stores `prev_hash` (the previous record's hash) and its own
`hash = SHA-256(canonical(record))`, where `canonical` is the record's fields
**excluding `hash`**, key-sorted, with fixed separators and UTF-8 preserved
(`core._canonical`). The genesis `prev_hash` is 64 zeros.

Properties:
- **Append-only**: new decisions extend the chain; nothing is rewritten.
- **Tamper-evident**: altering any field changes that record's hash, so every
  later `prev_hash` link no longer matches. `verify_chain` recomputes the whole
  chain and reports the first broken `seq` — distinguishing *content altered*
  (hash mismatch) from *inserted/removed/reordered* (prev_hash mismatch).
- **Independently checkable**: `python3 core.py verify` needs nothing but the
  file and stdlib — a reviewer (or regulator) can verify without trusting us.

This is the project's moat: not "smart judgement", but **court-grade evidence
that a human decision happened and has not been edited since**.

## Honest limitations (stated, because a regulator will ask)

1. **Prompt-enforced gate.** The chain proves logged entries are intact; it
   cannot prove completeness. A model that skips the gate leaves no record.
   Mitigation path: a deterministic pre-tool hook in the host agent, if
   available; until then this audits *disclosed* decisions — as any audit does.
2. **Keyword/pattern triggering.** Unnamed columns or requests with no domain
   words won't fire. Coverage of the trigger catalog is the ceiling.
3. **No fairness verdict.** Whether a model is actually biased is a data +
   runtime question (impossibility theorem); out of scope here.

## Cross-agent portability (an evaluation bonus)

The auditor is a **standard MCP server** plus a plain-Markdown rule file. The
integrity logic is provider-agnostic Python with zero dependencies. To move it
to Cline / Aider / Continue, point that agent's MCP config at the same
`server.py` and load `AGENTS.md` as its instructions — nothing is tied to
OpenCode or to any model vendor. `demo.py` proves the same flow runs against
DeepSeek / OpenAI / Gemini interchangeably.
