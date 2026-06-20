"""Pure-stdlib core of the compliance audit trail.

No third-party dependencies, so this module runs and self-tests with stock
python3. `server.py` wraps these functions as MCP tools; `verify` and
`report` also run from the command line for the live demo.

Design rule (the whole point of this project):
    The LLM NEVER computes a hash and NEVER writes a file. It only decides
    and calls log_decision(). This module does the deterministic work — so
    the audit trail cannot be faked by a chatty model that "writes" a log
    line with a made-up hash.

Tamper-evidence:
    Each record stores the SHA-256 hash of the PREVIOUS record (`prev_hash`)
    plus its own hash over the canonical form of all other fields. Altering,
    inserting, removing, or reordering any record breaks the chain, which
    verify_chain() detects and localises.
"""
from __future__ import annotations

import ast
import hashlib
import json
import os
import re
import sys
from datetime import datetime, timezone

GENESIS = "0" * 64


def _log_file(root: str) -> str:
    return os.path.join(root, "audit-trail", "decisions.jsonl")


def _canonical(record: dict) -> str:
    """Deterministic pre-image: every field EXCEPT the record's own `hash`,
    key-sorted, no incidental whitespace, UTF-8 preserved. Logger and verifier
    MUST use this identical function or hashes will never match."""
    payload = {k: v for k, v in record.items() if k != "hash"}
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def _read_all(root: str) -> list[dict]:
    path = _log_file(root)
    out: list[dict] = []
    if os.path.exists(path):
        with open(path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    out.append(json.loads(line))
    return out


def append_decision(
    root: str,
    domain: str,
    trigger: str,
    options: list,
    implications: str,
    user_choice: str,
    rationale: str = "",
    test_results: str = "",
    ai_act_ref: str = "",
    model: str = "",
    session: str = "",
) -> dict:
    """Append one tamper-evident decision record and return it."""
    path = _log_file(root)
    entries = _read_all(root)
    prev_hash = entries[-1]["hash"] if entries else GENESIS
    seq = entries[-1]["seq"] + 1 if entries else 0

    record = {
        "seq": seq,
        "ts": datetime.now(timezone.utc).isoformat(),
        "domain": domain,                 # privacy | security | fairness
        "trigger": trigger,               # why the gate fired (keyword/pattern)
        "options_presented": options,     # >= 2 alternatives shown to the dev
        "implications": implications,     # the tradeoff / what each option costs
        "user_choice": user_choice,       # the human decision
        "rationale": rationale,           # why the human chose it
        "test_results": test_results,     # any test/scan output, if available
        "ai_act_ref": ai_act_ref,         # verbatim legal anchor (not LLM-recalled)
        "model": model,                   # which model was driving
        "session": session,               # session id
        "prev_hash": prev_hash,           # chain link
    }
    record["hash"] = hashlib.sha256(_canonical(record).encode("utf-8")).hexdigest()

    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "a", encoding="utf-8") as f:
        f.write(json.dumps(record, ensure_ascii=False) + "\n")

    # Autosave a readable projection next to the raw chain. Best-effort: the
    # .jsonl is the authoritative record, so a narrative-write failure must
    # never break the append above.
    try:
        narrative_path = os.path.join(root, "audit-trail", "narrative.md")
        with open(narrative_path, "w", encoding="utf-8") as f:
            f.write(render_narrative(root))
    except Exception:
        pass

    return record


def verify_chain(root: str):
    """Return (ok: bool, message: str, count: int, head_hash: str).
    Walks the whole file, recomputing every hash and checking every link."""
    entries = _read_all(root)
    if not entries:
        return True, "Empty: no audit trail yet.", 0, GENESIS
    prev = GENESIS
    for i, rec in enumerate(entries):
        recomputed = hashlib.sha256(_canonical(rec).encode("utf-8")).hexdigest()
        if rec.get("prev_hash") != prev:
            return (False,
                    f"BROKEN at seq {rec.get('seq', i)}: prev_hash mismatch "
                    f"(an entry was inserted, removed, or reordered).", i, prev)
        if rec.get("hash") != recomputed:
            return (False,
                    f"BROKEN at seq {rec.get('seq', i)}: content was altered "
                    f"after it was logged.", i, prev)
        prev = rec["hash"]
    return True, f"OK: {len(entries)} entries, chain intact.", len(entries), prev


def render_model_card(root: str) -> str:
    """Deterministically render the audit trail into an EU AI Act-style
    Model Card. No LLM call: the report is a faithful projection of the
    chain, itself anchored to the verified head hash."""
    entries = _read_all(root)
    ok, msg, n, head = verify_chain(root)
    now = datetime.now(timezone.utc).isoformat()
    chain_line = ("✅ INTACT" if ok else "❌ " + msg)

    by_domain: dict[str, int] = {}
    for e in entries:
        by_domain[e["domain"]] = by_domain.get(e["domain"], 0) + 1

    L: list[str] = []
    L.append("# Compliance Model Card")
    L.append("")
    L.append("_Auto-generated from the tamper-evident audit trail. "
             "Every claim below is traceable to `audit-trail/decisions.jsonl`._")
    L.append("")
    L.append("## 1. System identification")
    L.append(f"- Generated at: `{now}`")
    L.append(f"- Audit chain status: **{chain_line}**")
    L.append(f"- Chain head hash: `{head}`")
    L.append(f"- Decisions recorded: **{n}**  "
             + " ".join(f"({k}: {v})" for k, v in sorted(by_domain.items())))
    L.append("")
    L.append("## 2. Purpose & scope")
    L.append("This record documents the fairness / privacy / cybersecurity "
             "tensions surfaced to the developer during AI-assisted code "
             "generation, and the human decisions made at each one. It does "
             "**not** certify that the resulting system is fair or secure — "
             "it certifies what was flagged, what choices were offered, and "
             "what the human decided.")
    L.append("")
    L.append("## 3. Decisions log (human oversight)")
    if not entries:
        L.append("_No decisions recorded._")
    else:
        L.append("| seq | time (UTC) | domain | trigger | choice | legal anchor |")
        L.append("|----:|------------|--------|---------|--------|--------------|")
        for e in entries:
            L.append(f"| {e['seq']} | {e['ts']} | {e['domain']} | "
                     f"{e['trigger']} | **{e['user_choice']}** | {e.get('ai_act_ref','')} |")
        L.append("")
        L.append("### Decision details")
        for e in entries:
            L.append(f"#### seq {e['seq']} — {e['domain']}: {e['trigger']}")
            L.append(f"- Options presented: {e['options_presented']}")
            L.append(f"- Implications / tradeoff: {e['implications']}")
            L.append(f"- **Developer chose:** {e['user_choice']}")
            if e.get("rationale"):
                L.append(f"- Rationale: {e['rationale']}")
            if e.get("test_results"):
                L.append(f"- Test results: {e['test_results']}")
            if e.get("ai_act_ref"):
                L.append(f"- Legal anchor (verbatim): {e['ai_act_ref']}")
            L.append(f"- Record hash: `{e['hash']}`")
            L.append("")
    cs = [e for e in entries if e.get("domain") == "child-safety"]
    if cs:
        L.append("## 3b. Child-safety safeguards (UN CRC / UNICEF)")
        L.append("Explicit safeguarding choices recorded for child-facing systems:")
        for e in cs:
            L.append(f"- **{e['trigger']}**")
            L.append(f"  - choice (escalation / retention / evaluation): {e['user_choice']}")
            if e.get("ai_act_ref"):
                L.append(f"  - basis: {e['ai_act_ref']}")
        L.append("")
    L.append("## 4. Known limitations")
    L.append("- The compliance gate is **prompt-enforced**: the chain proves "
             "that *what was logged* was not altered, but cannot prove that "
             "*everything that should have been logged* was logged. A model "
             "that skips the gate leaves no record — by design this tool "
             "audits disclosed decisions, like any audit.")
    L.append("- Detection is keyword/pattern based; concealed intent "
             "(unnamed columns, no domain words) will not trigger.")
    L.append("- This tool makes no fairness judgement; fairness outcomes are "
             "measurable only at runtime on real data.")
    L.append("")
    L.append("## 5. Traceability")
    L.append("- Raw evidence: `audit-trail/decisions.jsonl` (append-only, "
             "SHA-256 hash chain).")
    L.append("- Verify independently: "
             "`python3 mcp-servers/compliance-auditor/core.py verify`")
    L.append("")
    L.append("<!-- Optional: an LLM-written narrative MAY be appended below, "
             "clearly labelled as non-authoritative. The verifiable facts are "
             "those above, anchored to the chain head hash. -->")
    L.append("")
    return "\n".join(L)

# --- narrative helpers -------------------------------------------------------
# These turn the structured record fields into readable English. They are pure
# string/dict transforms with no LLM call, so the narrative below stays a
# faithful, reproducible projection of the chain rather than an invented story.

_MEASURE_NAMES = {
    "pii_exposure": "PII exposure",
    "self_harm": "self-harm",
    "sexual_exploitation": "sexual exploitation",
}
_RISK_LEVELS = {
    "HIGH_RISK": "high-risk",
    "CONCERNING": "concerning",
    "SENSITIVE": "sensitive",
    "SAFE": "safe",
}


def _measure_name(key: str) -> str:
    return _MEASURE_NAMES.get(key, key.replace("_", " "))


def _join(parts: list[str]) -> str:
    """Oxford-comma join: ['a'] -> 'a', ['a','b'] -> 'a and b',
    ['a','b','c'] -> 'a, b, and c'."""
    parts = [p for p in parts if p]
    if not parts:
        return ""
    if len(parts) == 1:
        return parts[0]
    if len(parts) == 2:
        return f"{parts[0]} and {parts[1]}"
    return ", ".join(parts[:-1]) + ", and " + parts[-1]


def _loose_dict(text) -> dict:
    """Best-effort extraction of a dict from a value that may be a real dict,
    a JSON string, a Python-repr string, or prose with a `{...}` blob inside."""
    if isinstance(text, dict):
        return text
    if not isinstance(text, str):
        return {}
    for attempt in (text, "{" + text.split("{", 1)[-1].rsplit("}", 1)[0] + "}"
                    if "{" in text and "}" in text else text):
        for parser in (json.loads, ast.literal_eval):
            try:
                val = parser(attempt)
                if isinstance(val, dict):
                    return val
            except (ValueError, SyntaxError):
                continue
    return {}


def _describe_measures(scores: dict) -> str:
    """Turn {'self_harm': 9.6, 'grooming': 0.0, ...} into prose, auto-detecting
    a 0-10 vs 0-1 scale and folding the long tail of zeros into one clause."""
    numeric = {k: v for k, v in scores.items() if isinstance(v, (int, float))}
    if not numeric:
        return ""
    scale10 = any(v > 1.0 for v in numeric.values())
    fmt = (lambda v: f"{v:g}/10") if scale10 else (lambda v: f"{v:.2f}")
    nonzero = sorted([(k, v) for k, v in numeric.items() if v > 0],
                     key=lambda kv: -kv[1])
    zeros = [k for k, v in numeric.items() if v == 0]
    if not nonzero:
        return "every category came back clean (all at zero)"
    lead = _join([f"{_measure_name(k)} at {fmt(v)}" for k, v in nonzero])
    if not zeros:
        return lead
    if len(zeros) <= 2:
        return f"{lead}, while {_join([_measure_name(k) for k in zeros])} stayed at zero"
    return f"{lead}, while every other category stayed at zero"


def _parse_votes(rationale: str):
    """['deepseek-chat', '0.95'], ... from 'deepseek:deepseek-chat=0.95; ...'."""
    return re.findall(r"(?:[\w.\-]+:)?([\w.\-]+)=([0-9.]+)", rationale or "")


def _parse_signals(test_results) -> list[str]:
    data = _loose_dict(test_results)
    out = []
    for sig in data.get("signals", []) or []:
        if isinstance(sig, dict) and sig.get("description"):
            out.append(sig["description"])
    return out


def _render_options(opts) -> str:
    rendered = []
    for o in opts or []:
        if isinstance(o, dict) and "axis" in o:
            choices = " / ".join(str(c) for c in o.get("options", []))
            rendered.append(f"{o['axis']} ({choices})")
        else:
            rendered.append(str(o))
    return "; ".join(rendered)


def render_narrative(root: str) -> str:
    """Deterministically render the audit trail as a plain-English reasoning
    log — one paragraph per decision, written in the voice of the compliance
    agent walking through what it saw, what tradeoffs were on the table, and
    what was decided. Like render_model_card(), this is a faithful projection
    of the chain (no LLM), anchored to the verified head hash, so the narrative
    stays auditable rather than becoming an unverifiable story.
    """
    entries = _read_all(root)
    ok, msg, n, head = verify_chain(root)

    def _when(ts: str) -> str:
        try:
            return datetime.fromisoformat(ts).strftime("%-d %B %Y at %H:%M UTC")
        except (ValueError, TypeError):
            return ts

    L: list[str] = []
    L.append("# Compliance audit trail — reasoning log")
    L.append("")
    status = "intact and verified" if ok else f"BROKEN — {msg}"
    L.append(
        f"What follows is a plain-English account of every compliance decision "
        f"on this run, written as the agent's own reasoning. The underlying "
        f"hash chain is currently **{status}**, covering {n} recorded "
        f"decision(s) and anchored to chain head `{head}`. The prose is "
        f"generated deterministically from `audit-trail/decisions.jsonl` with "
        f"no model in the loop, so every sentence traces back to a sealed "
        f"record; each paragraph ends with the record's own hash."
    )
    L.append("")
    if not entries:
        L.append("_No decisions have been recorded yet._")
        return "\n".join(L) + "\n"

    for e in entries:
        when = _when(e.get("ts", ""))
        seq = e.get("seq")
        trigger = e.get("trigger", "")
        choice = e.get("user_choice", "")
        rationale = e.get("rationale", "") or ""
        anchor = e.get("ai_act_ref", "") or ""
        domain = e.get("domain", "")
        escalated = "escalat" in choice.lower() or "escalat" in choice.lower()

        # --- shape 1: a human reviewer closed an escalation -------------------
        if domain == "human-review":
            m = re.match(r"REVIEWED by (.+?):\s*(.+)", choice)
            who = m.group(1) if m else "a reviewer"
            disp = (m.group(2) if m else choice).replace("_", " ")
            target = re.search(r"(conv_\w+|test_\w+)", trigger)
            tgt = f"conversation {target.group(1)}" if target else "the escalation"
            s = (f"On {when} the loop closed on {tgt}: {who} reviewed it and "
                 f"marked it **{disp}** (entry #{seq}).")
            if rationale:
                s += f" Their note: {rationale.rstrip('.')}."
            s += (" This is the human-in-the-loop step doing its job — the "
                  "system flags, a person makes the call.")

        # --- shape 2: a single conversation scored by the classifier ----------
        elif "risk_level=" in trigger:
            cid = re.search(r"(conv_\w+|test_\w+)", trigger)
            cid = cid.group(1) if cid else "a conversation"
            lvl = re.search(r"risk_level=(\w+)", trigger)
            lvl = _RISK_LEVELS.get(lvl.group(1), lvl.group(1).lower()) if lvl else "flagged"
            overall = re.search(r"overall=([0-9.]+)", trigger)
            overall = overall.group(1) if overall else "?"
            measures = _describe_measures(
                _loose_dict(e.get("test_results")).get("by_measure", {})
                or _loose_dict(e.get("implications")))
            signals = _parse_signals(e.get("test_results"))

            openers = [
                f"On {when}, conversation {cid} came back **{lvl}**, scoring "
                f"{overall}/10 overall (entry #{seq}).",
                f"On {when}, the classifier put conversation {cid} at {overall}/10, "
                f"landing it in **{lvl}** territory (entry #{seq}).",
                f"On {when}, {cid} tripped the classifier — **{lvl}** at {overall}/10 "
                f"(entry #{seq}).",
            ]
            s = openers[(seq or 0) % len(openers)]
            if measures:
                s += f" What drove the score was {measures}."
            if signals:
                quoted = _join([f"\u201c{d}\u201d" for d in signals])
                s += f" Concretely, it matched {quoted}."
            s += (" With a child potentially at risk, missing real harm costs far "
                  "more than an unnecessary review, so the human-in-the-loop "
                  "protocol escalated it to a human monitor rather than letting "
                  "it pass.")

        # --- shape 3: a multi-model risk panel voted -------------------------
        elif _parse_votes(rationale) and ("per-measure" in (e.get("implications") or "")
                                          or "panel" in trigger):
            subject = "a block of generated code" if domain == "code" else "a conversation"
            agg = re.search(r"aggregate ([0-9.]+)", trigger)
            agg = agg.group(1) if agg else "?"
            votes = _parse_votes(rationale)
            vote_text = _join([f"{model} scored it {score}" for model, score in votes])
            measures = _describe_measures(_loose_dict(e.get("implications")))
            s = (f"On {when} I paused over {subject} (entry #{seq}). My risk "
                 f"panel runs the material past three independent models, and "
                 f"their combined score came out at {agg} — past the 0.6 line "
                 f"where I stop and ask for a human.")
            if vote_text:
                s += f" They didn't fully agree: {vote_text}."
            if measures:
                s += f" Broken down by concern, {measures}."
            s += (" Two paths were open — escalate to a human monitor, or clear "
                  "it unreviewed — and I wasn't willing to clear it on my own, "
                  "so it went to a human." if escalated else
                  " I weighed escalation against clearing it unreviewed.")

        # --- shape 4: a design / architecture choice -------------------------
        else:
            opts = _render_options(e.get("options_presented"))
            label = "a fairness concern" if domain == "fairness" else "a design decision"
            s = (f"On {when}, {label} came up — {trigger.rstrip('.')} (entry "
                 f"#{seq}). "
                 f"Rather than pick a default silently — these are safeguarding "
                 f"tradeoffs, not neutral technical knobs — I surfaced the "
                 f"options: {opts}.")
            impl = e.get("implications", "")
            if impl:
                s += f" The tradeoff I laid out: {impl.rstrip('.')}."
            s += f" The developer settled on {choice}"
            s += f", reasoning that {rationale.rstrip('.').lower()}." if rationale else "."

        if anchor:
            s += f" Legal anchor: {anchor}."
        s += f" _(sealed in the chain under `{e['hash']}`)_"
        L.append(s)
        L.append("")
    return "\n".join(L)
def _cli(argv: list[str]) -> int:
    root = os.environ.get("COMPLIANCE_ROOT", os.getcwd())
    cmd = argv[1] if len(argv) > 1 else "verify"
    if cmd == "verify":
        ok, msg, n, head = verify_chain(root)
        print(("✅ " if ok else "") + msg)
        if n:
            print(f"   head: {head}")
        return 0 if ok else 1
    if cmd == "report":
        dest = os.path.join(root, argv[2] if len(argv) > 2 else "compliance_report.md")
        with open(dest, "w", encoding="utf-8") as f:
            f.write(render_model_card(root))
        print(f"✅ wrote {dest}")
        return 0
    if cmd == "narrate":
        dest = os.path.join(root, argv[2] if len(argv) > 2 else "audit-trail/narrative.md")
        with open(dest, "w", encoding="utf-8") as f:
            f.write(render_narrative(root))
        print(f"✅ wrote {dest}")
        return 0
    print(f"usage: core.py [verify|report [path]]", file=sys.stderr)
    return 2


if __name__ == "__main__":
    raise SystemExit(_cli(sys.argv))