# Advanced Topics & Things to Explore

> This doc goes one layer below the core thesis. The MVP is deliberately
> simple — a gate + a tamper-evident log. But several of its design choices sit
> on top of genuinely hard problems, and there is a lot of room to push further.
> If you're looking for where to take this next, start here.

---

## 1. The two layers of "fairness" handling

The tool treats fairness at two levels, and it's important to know which is which.

**Level 1 — surface + log (default, always on).** The gate recognises a
high-risk *domain* from context, presents the known tension (the impossibility
theorem), and records the human's choice. It makes **no measurement and no
verdict**. This is what runs for every fairness request, with or without data.

**Level 2 — measure the facts (`fairness_scan`, optional).** When an actual
dataset + protected column are available, the `fairness_scan` tool uses
**Fairlearn** to compute group-disaggregated *facts*:

- **Base-rate disparity** — the difference in the positive-label rate across
  groups. This is the number that makes the impossibility theorem *bite*: when
  base rates differ, you mathematically cannot equalise calibration and error
  rates simultaneously (Chouldechova 2017).
- **FPR / FNR disparity** — if a prediction column exists, the difference in
  false-positive and false-negative rates across groups. This is the exact shape
  of the ProPublica COMPAS finding (one group falsely flagged at a higher rate).
- **Group sizes** — because a tiny group makes its metrics unreliable, which is
  itself a caveat worth recording.

The scan reports these as **facts the human decided against**, recorded in the
audit trail's `test_results` field — never as a "fair / unfair" judgment.

> Why this distinction matters: it is the line between *auditable evidence* and
> *automated moralising*. The whole project's credibility rests on staying on the
> evidence side of it.

---

## 2. Why we stop where we stop (the honest boundary)

It's tempting to make the tool "smarter" — to have it *decide* whether code is
fair. It can't, and neither can anything else, for reasons worth internalising:

- **Bias lives in the data and at runtime, not in the source code.** The same
  `model.fit(X, y)` is fair on one dataset and discriminatory on another. Reading
  the program tells you nothing about the outcome.
- **Fairness is mutually-exclusive by construction.** Calibration, equal FPR, and
  equal FNR cannot all hold when base rates differ. *Which* one to prioritise is
  a value judgment — a legislative/judicial question, not a function call.
- **The trigger is the same hard problem in disguise.** Deciding "is this request
  high-risk?" ultimately requires understanding what the data *means* and how it
  will be *used* — which a keyword scan only approximates. We accept this and log
  what the catalog does *not* cover rather than pretend completeness.

So the tool audits the **decision process**, not the **mathematics of the
output**. That's not a limitation to apologise for — it's the only defensible
position, and it's exactly what the EU AI Act regulates (process, oversight,
record-keeping), not outcome-correctness.

---

## 3. The tamper-evidence frontier

`tamper_demo.py` shows the one edit the hash chain can't catch on its own:
recomputing the **head** record's own hash. The chain proves *internal*
consistency; it can't prove the head wasn't rewritten. Ways to close that gap:

- **Sign the head hash** (e.g. Ed25519) so only a key-holder can advance it.
- **External anchoring** — publish each head hash to an append-only transparency
  log (Sigstore Rekor, a Git tag, even a tweet), or an RFC 3161 timestamp
  authority, so the head is witnessed off-machine.
- **Co-signing** — have a second party (CI, a reviewer's machine) counter-sign
  decisions, so a single file-holder can't forge the whole history.

None of these change the core; they're a thin layer on top of the existing
`prev_hash` chain.

---

## 4. Things to explore (a menu, not a checklist)

Pick by interest — each is a self-contained direction.

**Strengthen the trigger (move beyond keywords).**
- **Deterministic static detectors** — real source→sink taint analysis for the
  *security/privacy* domains (e.g. user input flowing into a SQL string, PII into
  a log sink). These have determinate answers and would make the gate fire on
  *behaviour*, not just vocabulary.
- **Data profiling on load** — the moment a dataset is opened, compute protected-
  attribute presence and **proxy correlations** (which innocuous columns predict
  race/sex). This catches the FairJob case where there's no protected column at
  all, only proxies.
- **Coverage measurement** — quantify what fraction of sensitive requests the
  catalog actually catches, and surface the gap honestly instead of hiding it.

**Close the completeness gap.**
- The gate is *prompt-enforced*: a model can skip it. A **deterministic pre-tool
  hook** in the host agent (intercepting code-writing tool calls) would make the
  gate non-bypassable. Worth prototyping against OpenCode's tool pipeline.

**Go deeper on fairness measurement.**
- **AIF360 integration** — beyond Fairlearn's metrics, AIF360 offers
  pre-/in-/post-processing *mitigations*. Show the **accuracy↔fairness tradeoff
  curve** so the human chooses a point on it, and log the chosen point.
- **Runtime monitoring** — the layer where bias is actually observable. Tie the
  audit trail to deployed-model metrics (Evidently / Arize style) so a design-time
  decision links to its runtime consequences.

**Harden the legal grounding.**
- Replace the hand-written legal references with **RAG over the actual EU AI Act
  / UNESCO text**, retrieving verbatim article passages (never model-recalled) so
  citations are both exact and broader-coverage. (See the Trust/QA framing.)

**Broaden the reach.**
- **Cross-agent adapters** — ship Cline / Aider / Continue configs so the same
  auditor drops into any agent (the portability bonus, made concrete).
- **Policy-as-code** — express the gate catalog as OPA/Rego policies so rules are
  versioned, testable, and shareable across teams.
- **Signed, anchored audit** — implement §3 (Sigstore / transparency log).

**Push the agentic frontier.**
- **Multi-agent review** — a second, adversarial agent that checks whether the
  primary agent *should* have triggered the gate but didn't — a meta-supervisor.
- **Cost-aware orchestration** — measure tokens/latency per gated decision and
  show the overhead is negligible (a challenge bonus: cost consciousness).

---

## 5. What this is, and isn't

It **is**: non-repudiation infrastructure for AI-assisted development — a gate
that forces a documented, human-owned decision at sensitive moments, and a
tamper-evident record of it. Strongest for privacy/security (deterministic
patterns); "surface + log (+ optionally measure)" for fairness.

It **isn't**: a bias detector, a fairness certifier, or a guarantee that the
generated code is safe. Those are out of reach by design, and saying so plainly
is part of the point.

For the full design and traceability, see [`design.md`](./design.md); for the
architecture and threat model, [`architecture.md`](./architecture.md).

> There is a lot more to explore here than one hackathon can hold. The MVP draws
> a clean, honest line; everything in §4 is an invitation to push it further.
