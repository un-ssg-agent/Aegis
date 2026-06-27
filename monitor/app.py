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
from collections import Counter

from fastapi import FastAPI
from fastapi.responses import JSONResponse
from pydantic import BaseModel

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, ".."))
sys.path.insert(0, os.path.join(ROOT, "mcp-servers", "compliance-auditor"))
import core          # noqa: E402  (audit hash chain)
import llm_client    # noqa: E402  (the 3 providers)
import strands_agent as agent         # noqa: E402  (web coding agent — AGENTS.md gate + codegen)

THRESHOLD = float(os.environ.get("ALARM_THRESHOLD", "0.6"))

MEASURES = {
    "code": ["fairness", "privacy", "security"],
    "conversation": ["grooming", "bullying", "suicidal_ideation",
                     "self_harm", "pii_exposure", "distress"],
}
# Human-readable category labels for the UI distribution view.
CATEGORY_LABELS = {
    "fairness": "fairness", "privacy": "privacy", "security": "security",
    "grooming": "grooming", "bullying": "bullying",
    "suicidal_ideation": "suicidal ideation", "self_harm": "self harm",
    "pii_exposure": "PII exposure", "distress": "distress",
}
LABEL_FLOOR = 0.15  # below this a message carries no salient risk label
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


def _label_messages(kind: str, content: str, provider: str) -> list[dict]:
    """Label each line with its dominant risk category, using ONE model.

    The 3-model panel scores the whole context for escalation; this gives every
    individual message a category so the UI can tag bubbles and build the
    per-message distribution. One provider keeps the extra call count modest.
    """
    out = []
    for line in content.splitlines():
        line = line.strip()
        if not line:
            continue
        who, sep, text = line.partition(":")
        text, who = (text.strip(), who.strip()) if sep else (line, "?")
        try:
            scores = score_one(provider, kind, text)["scores"]
            label = max(scores, key=scores.get) if scores else "none"
            top = round(scores.get(label, 0.0), 3)
            if top < LABEL_FLOOR:
                label = "none"
        except Exception:
            label, top = "none", 0.0
        out.append({"who": who, "text": text, "label": label, "score": top})
    return out


def _distribution(kind: str, by_measure: dict, msgs: list[dict]) -> list[dict]:
    """Per-category distribution: severity score + share + message count, hi→lo."""
    counts = Counter(m["label"] for m in msgs)
    total = sum(by_measure.values()) or 1.0
    dist = [{"key": k, "label": CATEGORY_LABELS.get(k, k),
             "score": by_measure.get(k, 0.0),
             "share": round(by_measure.get(k, 0.0) / total, 3),
             "count": counts.get(k, 0)} for k in MEASURES[kind]]
    dist.sort(key=lambda d: d["score"], reverse=True)
    return dist


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
    providers = llm_client.provider_names()
    msgs = (_label_messages(kind, content, providers[0])
            if kind == "conversation" and providers else [])
    distribution = _distribution(kind, by_measure, msgs)
    dominant = distribution[0]["key"] if distribution and distribution[0]["score"] > 0 else None
    result = {"kind": kind, "n_models": len(panel), "panel": panel,
              "by_measure": by_measure, "aggregate": agg,
              "threshold": THRESHOLD, "alarm": alarm, "errors": errors,
              "messages": msgs, "distribution": distribution, "dominant": dominant}
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


class GenerateIn(BaseModel):
    prompt: str
    choices: dict | None = None   # {} on first call; filled after the dev picks options
    # optional custom governing policy for the developer's own use case; blank/None
    # falls back to the repo's AGENTS.md.
    system_prompt: str | None = None


class ChatIn(BaseModel):
    message: str
    # optional custom child-safety policy; blank/None falls back to child-policy.md.
    system_prompt: str | None = None


@app.get("/")
def index():
    return {"service": "ssgcheck-monitor", "ui": "run monitor-web (Next.js) on :3000",
            "endpoints": ["/api/generate", "/api/chat", "/api/policy", "/api/narrative", "/api/audit", "/assess", "/api/alarms", "/api/ack"]}


@app.post("/api/generate")
def generate_endpoint(body: GenerateIn):
    """Web coding agent: flag child-directed work, present developer choices, then
    generate code under AGENTS.md, logging the decision to the hash chain."""
    if not body.prompt.strip():
        return JSONResponse({"error": "prompt required"}, 400)
    try:
        return agent.generate(body.prompt, body.choices or {}, policy=body.system_prompt)
    except Exception as e:
        return JSONResponse({"error": f"{type(e).__name__}: {e}"}, 502)


@app.post("/api/chat")
def chat_endpoint(body: ChatIn):
    """Child-facing safeguarding chat: returns a calm child-facing reply plus the
    internal 5-axis assessment (bullying/grooming/abuse/self-harm/distress), escalation,
    and human-review flag. Logs to the hash chain when a human takes over (S4+)."""
    if not body.message.strip():
        return JSONResponse({"error": "message required"}, 400)
    try:
        return agent.child_chat(body.message, policy=body.system_prompt)
    except Exception as e:
        return JSONResponse({"error": f"{type(e).__name__}: {e}"}, 502)


@app.post("/assess")
def assess_endpoint(body: AssessIn):
    if body.kind not in MEASURES:
        return JSONResponse({"error": "kind must be 'code' or 'conversation'"}, 400)
    return assess(body.kind, body.content)


@app.get("/api/policy")
def api_policy():
    """The governing policy documents (read-only), so the UI can show the exact
    AGENTS.md / child-policy.md the agents actually run under. These are also the
    defaults a custom 'system_prompt' overrides per request."""
    return {"agents_md": agent._load_agents_md(),
            "child_policy_md": agent._load_child_policy()}


@app.get("/api/narrative")
def api_narrative():
    """The audit trail rendered as a plain-English reasoning log — the same prose
    as audit-trail/narrative.md, generated deterministically from the chain (no
    model in the loop), anchored to the verified head hash."""
    ok, msg, n, head = core.verify_chain(ROOT)
    return {"markdown": core.render_narrative(ROOT), "chain_ok": ok, "count": n, "head": head}


@app.get("/api/audit")
def api_audit():
    """The full tamper-evident decision chain (every entry) + verification status.
    Unlike /api/alarms (escalated monitor alarms only), this returns ALL decisions,
    including the coding-agent's child-safety gate decisions."""
    entries = core._read_all(ROOT)
    ok, msg, n, head = core.verify_chain(ROOT)
    return {"entries": entries, "chain_ok": ok, "chain": msg, "count": n, "head": head}


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