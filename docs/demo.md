# Manual Demo Guide — SSGCheck

> A step-by-step runbook for **showing the project live** (to judges, teammates,
> or yourself). Target length: **~5 minutes**. Every command is copy-paste; every
> step says what you'll see and what to say.
>
> The story in one line: **"We don't judge whether the code is fair — that's
> impossible. We make the human's decision visible and impossible to forge."**

---

## 0. Before the demo (2 min, do this once)

```bash
cd ssgcheck
uv sync                                   # install the MCP server's deps
git pull                                  # latest code
```

Pick **one** of two demo modes:

- **Mode A — real OpenCode (most impressive).** Works with a **free, no-key
  model** out of the box — `opencode/deepseek-v4-flash-free` (used in the
  commands below). Just confirm OpenCode is installed:
  ```bash
  opencode --version
  ```
  To use a **keyed** provider instead (e.g. `deepseek/deepseek-chat`), you must
  export the key first — otherwise that provider isn't loaded and you'll get
  `ProviderModelNotFoundError: deepseek/deepseek-chat`:
  ```bash
  export DEEPSEEK_API_KEY=...             # or OPENAI_API_KEY / GEMINI_API_KEY
  opencode models | grep deepseek         # the exact model ids now available
  ```
- **Mode B — no OpenCode (safe fallback).** Uses our `demo.py`, which drives the
  same flow against the model directly. Needs only a key in `.env`.

**Start from a clean trail** so the demo reads cleanly:

```bash
rm -f audit-trail/decisions.jsonl compliance_report.md
```

> 💡 Tip: have two terminal panes open — one to run commands, one with the file
> `audit-trail/decisions.jsonl` open in your editor (VS Code/Cursor) so the
> audience can watch it grow and watch you tamper with it.

---

## 1. The pitch (30 sec — say this first)

> "AI coding agents make silent ethical and security decisions. You can't catch
> bias by reading the code — bias lives in the data, not the source. So instead
> of judging the algorithm, our tool **checks the domain, not the code**: it
> intercepts *before* the AI writes a line, surfaces the known tradeoffs, lets a
> **human** decide, and writes that decision into a **tamper-evident log**. It's
> non-repudiation infrastructure for AI-assisted development."

---

## 2. Act 1 — The gate fires (90 sec)

### Mode A (real OpenCode)

```bash
opencode run -m opencode/deepseek-v4-flash-free "Build a SQL query by interpolating the user-supplied username to fetch that user"
```

**What you'll see:** instead of writing code, the agent says a **Security signal
fired (SQL injection)** and offers options (A: parameterised query, B: string
interpolation, …) and asks you to choose.

**Say:** "Notice it refused to write code. It read the context, recognised a
known security tension, and is forcing a human decision."

Now make the choice — this is where the MCP tool fires:

```bash
opencode run -c -m opencode/deepseek-v4-flash-free "I choose A, the parameterized query. Log this decision, then write the code."
```

**What you'll see in the logs:** `compliance-auditor_log_decision {...}` being
called, and then the parameterised code. **In your editor pane**, a new line
appears in `audit-trail/decisions.jsonl`.

### Mode B (fallback, no OpenCode)

```bash
uv run python mcp-servers/compliance-auditor/demo.py
```

Runs 3 scenarios (privacy / security / fairness) end-to-end: the model presents
options, a scripted choice is made, `log_decision` writes the record, code is
produced — then it verifies and reports.

---

## 3. Act 2 — Show the evidence (30 sec)

Show the record that was just written:

```bash
cat audit-trail/decisions.jsonl
```

**Point at these fields and say:**
- `domain` / `trigger` — what was flagged
- `options_presented` / `implications` — the tradeoff shown to the human
- `user_choice` / `rationale` — what the human decided and why
- `ai_act_ref` — the verbatim legal anchor (for the fairness record)
- `prev_hash` / `hash` — **the chain link** (this is the magic)

---

## 4. Act 3 — Prove it's intact (15 sec)

```bash
uv run python mcp-servers/compliance-auditor/core.py verify
```

**You'll see:** `✅ OK: N entries, chain intact.` plus the head hash.

**Say:** "Right now the chain verifies. Watch what happens when I tamper with
it."

---

## 5. Act 4 — Tamper by hand (THE moment, 60 sec)

This is the part to do **manually**, in front of people.

1. Open `audit-trail/decisions.jsonl` in your editor.
2. Find a record and **change one value** — e.g. flip `"user_choice": "A"` to
   `"user_choice": "B"`. Leave everything else (including `hash`) untouched.
3. **Save the file.**
4. Re-run verify:

```bash
uv run python mcp-servers/compliance-auditor/core.py verify
```

**You'll see:**
```
BROKEN at seq <n>: content was altered after it was logged.
```

**Say:** "I changed what the developer chose — falsifying the record. The chain
caught it instantly and told me exactly which entry was edited. You cannot
quietly rewrite history here."

> Want to show you can't escape it by *also* editing the hash? Try changing the
> `hash` field too, or deleting the whole line — re-run `verify` and it still
> reports `BROKEN` (now as a broken chain link). There's no manual edit that
> survives.

**Restore** the file afterwards (undo in the editor, or regenerate):

```bash
# easiest: undo in your editor (Cmd+Z). Or start fresh:
# rm -f audit-trail/decisions.jsonl   # then re-run Act 1
```

---

## 6. Act 5 — The "smart forger" (45 sec, optional but strong)

Run the narrated tamper demo — it shows the sophisticated attack **and** the one
honest limitation:

```bash
uv run python mcp-servers/compliance-auditor/tamper_demo.py
```

**Walk through the output:**
- Flip / garble / delete → all caught at the exact `seq`.
- **Smart forger** edits a middle record *and recomputes its own hash* → still
  caught, because the **next** record's `prev_hash` no longer matches.
- **Honest caveat:** editing the **last** record and recomputing its hash is
  *not* caught by the chain alone.

**Say:** "We're honest about the limit: the only edit that survives is rewriting
the head record's own hash — which is exactly why a production version signs or
externally anchors the head hash. We know precisely where the boundary is."

---

## 7. Act 6 — The human-readable report (20 sec)

```bash
uv run python mcp-servers/compliance-auditor/core.py report
```

Open `compliance_report.md`. **Say:** "And for an auditor or a regulator who
won't read JSON — a Model Card: every decision, its tradeoff, the human's choice,
the legal anchor, the chain status and head hash, and an honest limitations
section. Generated deterministically from the chain, so the report itself is
traceable."

---

## 7b. Bonus — fairness with real numbers (45 sec, no key needed)

One-time: `uv sync --extra fairness`. Then:

```bash
uv run --extra fairness python mcp-servers/compliance-auditor/fairness_demo.py
```

It builds a COMPAS-like dataset, fires the fairness gate, runs `fairness_scan`
(Fairlearn) to compute the **actual** group disparities, and logs the decision
with those numbers in `test_results`.

**Say:** "For the fairness case, the record doesn't just say *what* the developer
chose — it captures the base-rate disparity (0.244) and false-positive-rate
disparity (0.191) the choice was made against. Real numbers, computed from the
data with Fairlearn. And it still asserts **no verdict** — which disparity to
accept stays a human judgment."

---

## 8. Close (15 sec)

> "So: we don't pretend to judge fairness. We make the decision process
> **visible, human-owned, and non-repudiable** — strongest for privacy and
> security where the patterns are deterministic, and 'surface + log' for fairness
> where no tool can give a verdict. It's a standard MCP server plus a Markdown
> rule file, so it drops into OpenCode, Cline, Aider — any agent."

---

## Cheat sheet (all commands in order)

```bash
# setup
uv sync && rm -f audit-trail/decisions.jsonl compliance_report.md
export DEEPSEEK_API_KEY=...

# Act 1 — gate fires (Mode A)
opencode run -m opencode/deepseek-v4-flash-free "Build a SQL query by interpolating the user-supplied username"
opencode run -c -m opencode/deepseek-v4-flash-free "I choose A, parameterized query. Log it, then write the code."
#   (or Mode B fallback)
uv run python mcp-servers/compliance-auditor/demo.py

# Act 2 — evidence
cat audit-trail/decisions.jsonl

# Act 3 — intact
uv run python mcp-servers/compliance-auditor/core.py verify

# Act 4 — tamper by hand: edit a value in the file, save, then:
uv run python mcp-servers/compliance-auditor/core.py verify     # -> BROKEN at seq n

# Act 5 — smart forger + caveat
uv run python mcp-servers/compliance-auditor/tamper_demo.py

# Act 6 — report
uv run python mcp-servers/compliance-auditor/core.py report     # -> compliance_report.md

# Bonus — fairness with REAL numbers (one-time: uv sync --extra fairness)
uv run --extra fairness python mcp-servers/compliance-auditor/fairness_demo.py
```

---

## Troubleshooting (live-demo edition)

| Problem | Fix |
|---|---|
| No internet / model is down | Use **Mode B** (`demo.py`); it falls back across DeepSeek/OpenAI/Gemini. Worst case, skip Act 1 and demo Acts 3–6 (backend needs no network). |
| `opencode` provider/auth error | `export DEEPSEEK_API_KEY=...` (or the organizers' key) before running |
| Demo trail is messy from rehearsing | `rm -f audit-trail/decisions.jsonl` and start Act 1 again |
| `verify` says BROKEN before you tampered | You left edits from a previous take — regenerate the trail (clean + re-run Act 1) |
| Want a guaranteed-working backend demo with zero deps | `uv run python mcp-servers/compliance-auditor/selftest.py` — self-contained proof |

> Golden rule: **rehearse the tamper step once** before going live, and keep the
> editor pane visible — watching the file change and then get caught is the whole
> show.
