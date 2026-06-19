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

import hashlib
import json
import os
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
    print(f"usage: core.py [verify|report [path]]", file=sys.stderr)
    return 2


if __name__ == "__main__":
    raise SystemExit(_cli(sys.argv))
