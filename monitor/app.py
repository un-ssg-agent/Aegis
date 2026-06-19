"""Demo monitor server — 3-model risk panel with threshold escalation.

A piece of code OR a set of conversation turns is scored independently by THREE
models (the DeepSeek / OpenAI / Gemini providers). Their scores are aggregated;
if the aggregate crosses the threshold, an ALARM is raised and escalated to a
human monitor — recorded in the tamper-evident audit trail (core.py). A human
reviewer acknowledges it in the dashboard, which appends a human-review entry to
the same chain (closing the human-in-the-loop).

Reuses the SSGCheck spine: panel of judges -> threshold -> human-in-the-loop ->
non-repudiable log. Governs two input kinds:
  - code         : fairness / privacy / security risk (the AESIA coding case)
  - conversation : grooming / self-harm / PII / distress (the UNICEF child case)

Endpoints:
  GET  /              assessment UI            (static/index.html)
  POST /assess        score content -> result + (if alarm) audit record
  GET  /monitor       human-monitor dashboard  (static/monitor.html)
  GET  /api/alarms    escalated alarms + chain status (JSON)
  POST /api/ack       human acknowledges an alarm -> appended to the chain

Run:
  uv run --extra server python monitor/app.py            # http://127.0.0.1:8000
Needs at least one provider key in .env (DEEPSEEK/OPENAI/GEMINI_API_KEY).
"""
from __future__ import annotations

import json
import os
import re
import sys

from fastapi import FastAPI
from fastapi.responses import JSONResponse
from pydantic import BaseModel

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, ".."))
sys.path.insert(0, os.path.join(ROOT, "mcp-servers", "compliance-auditor"))
import core          # noqa: E402  (audit hash chain)
import llm_client    # noqa: E402  (the 3 providers)

THRESHOLD = float(os.environ.get("ALARM_THRESHOLD", "0.6"))

MEASURES = {
    "code": ["fairness", "privacy", "security"],
    "conversation": ["grooming", "self_harm", "pii_exposure", "distress"],
}
AI_ACT = {
    "code": "EU AI Act high-risk (Annex III) / UNESCO AI ethics",
    "conversation": "UN CRC arts 3,12,16,19,34; EU AI Act (rights-sensitive)",
}


def _extract_json(text: str) -> dict:
    m = re.search(r"\{.*\}", text or "", re.DOTALL)
    return json.loads(m.group(0)) if m else {}


def score_one(provider: str, kind: str, content: str) -> dict:
    """Ask one model to score the content; returns {provider, scores, overall, reason}."""
    measures = MEASURES[kind]
    system = ("You are a strict AI-risk auditor. Score the given "
              f"{kind} for risk on each measure from 0.0 (none) to 1.0 (severe). "
              'Reply with ONLY JSON: {"scores": {<measure>: <float>}, '
              '"overall": <float>, "reason": "<one sentence>"}.')
    user = f"Measures: {measures}\n\n{kind.upper()}:\n```\n{content}\n```"
    msg, label = llm_client.chat_one(
        provider, [{"role": "system", "content": system},
                   {"role": "user", "content": user}])
    data = _extract_json(msg.get("content", ""))
    scores = {m: float(data.get("scores", {}).get(m, 0.0)) for m in measures}
    overall = float(data.get("overall", max(scores.values()) if scores else 0.0))
    return {"provider": label, "scores": scores,
            "overall": round(overall, 3), "reason": data.get("reason", "")}


def assess(kind: str, content: str) -> dict:
    panel, errors = [], []
    for name in llm_client.provider_names():
        try:
            panel.append(score_one(name, kind, content))
        except Exception as e:  # one model down -> panel of the rest
            errors.append(f"{name}: {type(e).__name__}")
    agg = round(sum(p["overall"] for p in panel) / len(panel), 3) if panel else 0.0
    by_measure = {m: round(max((p["scores"].get(m, 0.0) for p in panel), default=0.0), 3)
                  for m in MEASURES[kind]}
    alarm = bool(panel) and agg >= THRESHOLD
    result = {"kind": kind, "n_models": len(panel), "panel": panel,
              "by_measure": by_measure, "aggregate": agg,
              "threshold": THRESHOLD, "alarm": alarm, "errors": errors}
    if alarm:
        rec = core.append_decision(
            ROOT, kind,
            f"{kind} risk panel: {len(panel)} models, aggregate {agg} >= {THRESHOLD}",
            ["ESCALATE to a human monitor", "allow without review"],
            f"per-measure worst-case {by_measure}",
            "ESCALATED to human monitor",
            rationale="; ".join(f"{p['provider']}={p['overall']}" for p in panel),
            test_results=json.dumps(by_measure), ai_act_ref=AI_ACT[kind],
            model="monitor-panel", session="monitor")
        result["audit_seq"] = rec["seq"]
        result["audit_hash"] = rec["hash"]
    return result


app = FastAPI(title="SSGCheck monitor")


class AssessIn(BaseModel):
    kind: str            # "code" | "conversation"
    content: str


class AckIn(BaseModel):
    seq: int             # the escalated alarm's seq
    reviewer: str        # who reviewed
    action: str          # e.g. "confirmed risk" / "false positive" / "actioned"
    note: str = ""


@app.get("/")
def index():
    return {"service": "ssgcheck-monitor", "ui": "run monitor-web (Next.js) on :3000",
            "endpoints": ["/assess", "/api/alarms", "/api/ack"]}


@app.post("/assess")
def assess_endpoint(body: AssessIn):
    if body.kind not in MEASURES:
        return JSONResponse({"error": "kind must be 'code' or 'conversation'"}, 400)
    return assess(body.kind, body.content)


@app.get("/api/alarms")
def api_alarms():
    """Escalated alarms + which have been human-reviewed + chain status."""
    entries = core._read_all(ROOT)
    reviewed = {e.get("reviewed_seq") for e in entries if e.get("domain") == "human-review"}
    alarms = [{**e, "reviewed": e["seq"] in reviewed}
              for e in entries if str(e.get("user_choice", "")).startswith("ESCALATED")]
    ok, msg, n, head = core.verify_chain(ROOT)
    return {"alarms": alarms, "chain_ok": ok, "chain": msg, "head": head}


@app.post("/api/ack")
def api_ack(body: AckIn):
    """Human acknowledges an alarm — appended to the SAME chain (closes the loop)."""
    rec = core.append_decision(
        ROOT, "human-review",
        f"human reviewed alarm seq {body.seq}",
        ["confirmed risk", "false positive", "actioned"],
        f"reviewer disposition for escalated alarm #{body.seq}",
        f"REVIEWED by {body.reviewer}: {body.action}",
        rationale=body.note, model="human", session="monitor")
    # record which alarm this review closes (used by /api/alarms)
    return {"ok": True, "seq": rec["seq"], "hash": rec["hash"], "reviewed_seq": body.seq}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="127.0.0.1", port=int(os.environ.get("PORT", "8000")))
