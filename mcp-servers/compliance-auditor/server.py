"""MCP server exposing the compliance audit trail to any coding agent.

Thin wrapper over core.py. The LLM calls these tools; core.py does the
deterministic hashing and file I/O. Run as a local MCP server from
opencode.json (or any MCP client).

    pip install -r requirements.txt
    python3 server.py
"""
from __future__ import annotations

import os

from mcp.server.fastmcp import FastMCP

import core

ROOT = os.environ.get("COMPLIANCE_ROOT", os.getcwd())
mcp = FastMCP("compliance-auditor")


@mcp.tool()
def log_decision(
    domain: str,
    trigger: str,
    options_presented: list,
    implications: str,
    user_choice: str,
    rationale: str = "",
    test_results: str = "",
    ai_act_ref: str = "",
    model: str = "",
    session: str = "",
) -> str:
    """Append a tamper-evident decision to the audit trail.

    Call this AFTER the developer has chosen among the presented options and
    BEFORE generating the final code. Do NOT invent the hash — this tool
    computes the real SHA-256 chain. `domain` is one of
    privacy|security|fairness. `options_presented` must list >= 2 alternatives.
    """
    rec = core.append_decision(
        ROOT, domain, trigger, options_presented, implications, user_choice,
        rationale, test_results, ai_act_ref, model, session,
    )
    return f"Logged seq={rec['seq']} hash={rec['hash'][:12]}… (chain extended)"


@mcp.tool()
def verify_audit_trail() -> str:
    """Re-walk decisions.jsonl and confirm the hash chain is intact. Reports
    the first broken entry if any record was altered, inserted, or reordered."""
    ok, msg, n, head = core.verify_chain(ROOT)
    return msg + (f" head={head[:12]}…" if n else "")


@mcp.tool()
def generate_compliance_report(output_path: str = "compliance_report.md") -> str:
    """Render the audit trail into a human-readable EU AI Act-style Model Card.
    Deterministic — built from the chain, not written by an LLM."""
    dest = os.path.join(ROOT, output_path)
    with open(dest, "w", encoding="utf-8") as f:
        f.write(core.render_model_card(ROOT))
    return f"Wrote {dest}"


@mcp.tool()
def fairness_scan(dataset_path: str, protected_col: str, label_col: str,
                  prediction_col: str = "", positive_label: str = "1") -> str:
    """Compute group-disaggregated fairness FACTS (base-rate, and FPR/FNR if a
    prediction column is given) for a dataset, so you can attach real numbers to
    a fairness decision via `log_decision(test_results=...)`.

    Call this ONLY in a fairness/high-risk-data context when an actual dataset
    path + protected column are available — not on every request. It surfaces
    facts, never a verdict. Requires `uv sync --extra fairness`."""
    try:
        import fairness as _fairness
    except ImportError:
        return "fairness extra not installed — run: uv sync --extra fairness"
    try:
        res = _fairness.fairness_scan(dataset_path, protected_col, label_col,
                                      prediction_col or None, positive_label)
    except Exception as e:  # bad path/columns -> report, don't crash the agent
        return f"fairness_scan error: {type(e).__name__}: {e}"
    return res["summary"]


if __name__ == "__main__":
    mcp.run()
