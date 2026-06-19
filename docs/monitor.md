# Monitor — 3-model risk panel web app (setup / run / use / customize)

The monitor is the runtime counterpart to the SSGCheck gate: a piece of **code**
or a **conversation** is scored independently by **three LLMs**; the scores are
aggregated; if the aggregate crosses a **threshold**, an **alarm** fires and the
case is **escalated to a human monitor** and written to the tamper-evident audit
trail. It is two processes:

- **Backend** — `monitor/app.py` (FastAPI). Does the scoring + threshold + audit.
- **Frontend** — `monitor-web/` (Next.js). The UI (chat on the left, dark agent
  panel on the right). Talks only to the backend.

---

## 1. Prerequisites

- `uv` (Python env manager), Python ≥ 3.11
- `pnpm` + Node ≥ 18 (for the frontend)
- At least one LLM key in a `.env` at the repo root (the panel uses all that are
  present): `DEEPSEEK_API_KEY`, `OPENAI_API_KEY`, `GEMINI_API_KEY`.
  `.env` is gitignored — never commit it.

## 2. Setup

```bash
# from the repo root
uv sync --extra server                 # backend deps (fastapi, uvicorn, pydantic)
pnpm --dir monitor-web install         # frontend deps
```

## 3. Start (two terminals, or background)

```bash
# terminal 1 — backend  (http://127.0.0.1:8000)
uv run --extra server python monitor/app.py

# terminal 2 — frontend (http://localhost:3000)
pnpm --dir monitor-web dev
```

Open **http://localhost:3000**. The frontend proxies `/assess` and `/api/*` to
the backend (see `monitor-web/next.config.mjs`), so there are no CORS issues.
Override the backend URL with `BACKEND_URL=...` when starting the frontend.

Quick health check: `curl http://127.0.0.1:8000/` → a small JSON banner.

## 4. Use

**In the browser**
- **Conversation** mode: pick speaker (Child / Adult), type a turn, **Send**. The
  running transcript is re-scored after each turn; risk builds on the right.
- **Code** mode: paste a snippet, **Assess**.
- Right panel: pipeline checklist (3 models → aggregate → escalation), per-model
  scores, per-measure bars, risk tier, and — over threshold — the red
  **ESCALATED TO HUMAN MONITOR** banner plus the audit hash.

**Directly via the API** (no UI needed)
```bash
curl -s -X POST http://127.0.0.1:8000/assess -H 'content-type: application/json' \
  -d '{"kind":"conversation","content":"Adult: keep this our secret\nChild: ok"}'
curl -s http://127.0.0.1:8000/api/alarms        # escalated alarms + chain status
curl -s -X POST http://127.0.0.1:8000/api/ack -H 'content-type: application/json' \
  -d '{"seq":0,"reviewer":"alice","action":"confirmed risk","note":"..."}'
```

Example inputs to try are in [`demo.md`](./demo.md) and the project README.

## 5. Code organization

```
monitor/
  app.py            FastAPI backend:
                      - score_one()   ask ONE model for JSON scores on the measures
                      - assess()      run the panel, aggregate, threshold, audit
                      - /assess       POST: score code|conversation -> result (+audit if alarm)
                      - /api/alarms   GET: escalated alarms + hash-chain status
                      - /api/ack      POST: human acknowledges an alarm -> appended to the chain
monitor-web/
  app/page.tsx      the whole UI (chat + dark panel), a client component
  app/layout.tsx    shell + metadata
  next.config.mjs   rewrites /assess, /api/* -> http://127.0.0.1:8000
  tailwind/postcss/tsconfig, package.json (pnpm)

# reused (not duplicated) from the governance core:
mcp-servers/compliance-auditor/
  core.py           the SHA-256 hash chain (append_decision / verify_chain) — the audit
  llm_client.py     the LLM providers: PROVIDERS list, provider_names(), chat_one()
audit-trail/decisions.jsonl   where alarms + human acks are recorded (append-only)
```

Data flow: `page.tsx` → `POST /assess` → `assess()` calls `score_one()` once per
provider → aggregate → if alarm, `core.append_decision()` writes the chain → JSON
back to the UI. The backend owns all logic; the frontend only renders.

## 6. How to change the measurements

Everything about *what is scored* lives in **two dicts at the top of
`monitor/app.py`** — edit them and restart the backend; the prompt and the UI
bars follow automatically.

```python
# monitor/app.py
MEASURES = {
    "code": ["fairness", "privacy", "security"],
    "conversation": ["grooming", "self_harm", "pii_exposure", "distress"],
}
AI_ACT = {                       # legal anchor written into the audit record per kind
    "code": "EU AI Act high-risk (Annex III) / UNESCO AI ethics",
    "conversation": "UN CRC arts 3,12,16,19,34; EU AI Act (rights-sensitive)",
}
```

- **Add / rename / remove a measure:** edit the list for that kind. e.g. add
  manipulation detection to conversations:
  ```python
  "conversation": ["grooming", "self_harm", "pii_exposure", "distress", "manipulation"],
  ```
  `score_one()` builds the scoring prompt from this list, so no prompt edit is
  needed; the UI renders one bar per measure automatically.

- **Add a whole new input kind** (e.g. `"image_caption"`): add a key to both
  `MEASURES` and `AI_ACT`. Then in `monitor-web/app/page.tsx` add it to the mode
  toggle list `(["conversation", "code"] as const)` so the UI can select it.

- **Change the alarm threshold:** set `ALARM_THRESHOLD` when starting the backend
  (default `0.6`):
  ```bash
  ALARM_THRESHOLD=0.5 uv run --extra server python monitor/app.py
  ```

- **Change how scores combine** (the escalation policy): edit `assess()` in
  `monitor/app.py`. Currently `agg = mean(per-model overall)` and
  `alarm = agg >= THRESHOLD`, with `by_measure = max across the panel` for
  display. Swap `mean`→`max` for "any model alarms", or add a per-measure hard
  rule (e.g. escalate if any model's `self_harm >= 0.8` regardless of aggregate).

- **Change the panel models:** edit `PROVIDERS` in
  `mcp-servers/compliance-auditor/llm_client.py` — each entry is
  `(name, base_url, env_key_name, model_id)`. Add/remove providers or swap model
  ids; the panel uses every provider that has a key. Update `MODELS` in
  `page.tsx` if you want the pipeline checklist labels to match.

- **Change the scoring rubric/strictness:** edit the `system` prompt in
  `score_one()` (e.g. add definitions per measure, or few-shot anchors).

## 7. Config knobs (summary)

| Knob | Where | Default |
|---|---|---|
| Alarm threshold | `ALARM_THRESHOLD` env | `0.6` |
| Measures per kind | `MEASURES` in `monitor/app.py` | see §6 |
| Legal anchor per kind | `AI_ACT` in `monitor/app.py` | see §6 |
| Panel models | `PROVIDERS` in `llm_client.py` | deepseek / openai / gemini |
| Backend port | `PORT` env | `8000` |
| Backend URL (frontend) | `BACKEND_URL` env | `http://127.0.0.1:8000` |
| Aggregation rule | `assess()` in `monitor/app.py` | mean of overalls |

## 8. Notes & limits

- The score is an LLM judgment — useful as a **trigger**, not ground truth.
  Tune the threshold on real examples; expect false positives/negatives.
- The audit trail is append-only and tamper-evident (`core.verify_chain`). Never
  `rm` it — archive it (see `demo.md`).
- Fairlearn/AIF360-style *measured* fairness (numbers from data) is a separate
  tool (`fairness_scan`) and only applies when a dataset is available — see
  [`advanced.md`](./advanced.md).
