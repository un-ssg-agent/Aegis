# monitor-web — Aegis monitor UI (Next.js)

A Next.js front-end for the 3-model risk panel, styled like the reference video:
a light chat on the left, a dark "agent panel" on the right (pipeline checklist →
numbered cards with SHAP-style score bars → red **ESCALATED TO HUMAN MONITOR**
banner). It only calls the FastAPI backend (`/assess`, `/api/*`) via Next
rewrites — no business logic lives here.

## Run

1. Start the backend (from the repo root):
   ```bash
   uv sync --extra server
   uv run --extra server python monitor/app.py        # http://127.0.0.1:8000
   ```
2. Start this UI:
   ```bash
   cd monitor-web
   pnpm install
   pnpm dev                                            # http://localhost:3000
   ```

`next.config.mjs` proxies `/assess` and `/api/*` to `http://127.0.0.1:8000`
(override with `BACKEND_URL`).

## What it shows

- **Left** — Conversation mode (type turns as Child / Adult; the running
  transcript is scored after each turn) or Code mode (paste a snippet).
- **Right** — the panel updates live: pipeline checklist (3 models → aggregate →
  escalation), per-model scores, per-measure bars, the risk tier, and — when the
  aggregate crosses the threshold — the escalation banner + the audit hash of the
  record written to the tamper-evident chain.
