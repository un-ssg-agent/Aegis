"""Fairness demo — the full high-risk flow, with REAL disparity numbers.

Shows the fairness branch end to end:
  gate fires (recidivism + protected attribute)
    -> options presented (A: debias with Fairlearn/AIF360, B: keep + measure, C: proceed)
    -> human chooses
    -> fairness_scan computes the ACTUAL group disparities from the data
    -> log_decision records the choice WITH those numbers in `test_results`
    -> verify the chain.

Unlike demo.py this needs no API key — it is the deterministic "what the audit
record should contain" demo, with Fairlearn producing the facts. It appends to
the project's real audit trail so `core.py verify` / `report` pick it up.

Run: uv run --extra fairness python mcp-servers/compliance-auditor/fairness_demo.py
"""
import json
import os
import random
import tempfile

import core
import fairness

ROOT = os.environ.get(
    "COMPLIANCE_ROOT",
    os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))


def make_dataset(path: str) -> None:
    """Synthetic COMPAS-like data: one group has a higher base rate (mirroring
    the real arrest-rate skew) and a predictor that over-flags it."""
    random.seed(7)
    rows = [("race", "two_year_recid", "pred")]
    for _ in range(600):
        r = random.choice(["African-American", "Caucasian"])
        base = 0.55 if r == "African-American" else 0.39
        y = 1 if random.random() < base else 0
        p = 1 if random.random() < (0.6 if r == "African-American" else 0.4) else 0
        rows.append((r, y, p))
    with open(path, "w", newline="", encoding="utf-8") as f:
        f.write("\n".join(",".join(map(str, x)) for x in rows))


def main() -> None:
    ds = os.path.join(tempfile.mkdtemp(prefix="fairness-demo-"), "compas_demo.csv")
    make_dataset(ds)

    print("=" * 72)
    print("DEV REQUEST: train a recidivism risk classifier on compas_demo.csv "
          "(has race, two_year_recid)")
    print("=" * 72)
    print("\n[GATE] Fairness signal — EU AI Act Annex III.6.d (law-enforcement "
          "recidivism risk). Code generation paused. Options:")
    options = [
        "A: drop race + proxy audit, debias with Fairlearn/AIF360",
        "B: keep race + compute group-disaggregated metrics (measure first)",
        "C: proceed as-is",
    ]
    for o in options:
        print(f"   - {o}")
    print("   Tension: impossibility theorem — when base rates differ you "
          "cannot equalize calibration AND error rates across groups.")

    choice = "B: keep + compute group-disaggregated metrics"
    print(f"\n[DEV CHOICE] {choice}")

    # The facts — computed from the data, not asserted by a model.
    print("\n[TOOL] fairness_scan(compas_demo.csv, protected=race, "
          "label=two_year_recid, pred=pred)")
    scan = fairness.fairness_scan(ds, "race", "two_year_recid", prediction_col="pred")
    print(f"   -> {scan['summary']}")

    rec = core.append_decision(
        ROOT, "fairness",
        "train recidivism classifier on compas_demo.csv [race, two_year_recid]",
        options,
        "impossibility theorem: base rates differ -> cannot equalize "
        "calibration & error rates across groups",
        choice,
        rationale="measure the disparity before deciding how to mitigate",
        test_results=scan["summary"],            # <-- REAL numbers in the record
        ai_act_ref="EU AI Act Annex III.6.d",
        model="fairness_demo", session="fairness-demo")
    print(f"\n[LOGGED] seq={rec['seq']} hash={rec['hash'][:12]}…")

    ok, msg, n, head = core.verify_chain(ROOT)
    print(f"[VERIFY] {'✅' if ok else '❌'} {msg}")

    print("\n[RECORD] the fairness decision now carries the real disparities:")
    print("   test_results:", rec["test_results"])
    print("\nThis is the point: the audit trail records not just the human's "
          "choice, but the measured facts the choice was made against — and the "
          "tool still asserts no verdict.")


if __name__ == "__main__":
    main()
