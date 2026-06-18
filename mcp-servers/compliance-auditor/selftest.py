"""Backend self-test — proves the hash chain is real and tamper-evident.

Runs with stock python3 (no MCP, no LLM, no network). Writes three honest
decisions to a throwaway directory, verifies the chain, then flips one logged
choice (A -> B) without recomputing its hash — exactly the forgery a reviewer
would attempt — and shows that verification catches it.
"""
import json
import os
import tempfile

import core

root = tempfile.mkdtemp(prefix="audit-selftest-")
print(f"sandbox: {root}\n")

core.append_decision(
    root, "privacy",
    "SELECT * over user_profile -> sent to frontend (data minimisation)",
    ["A: select id, name only", "B: keep all fields"],
    "B exposes PII beyond what the frontend needs",
    "A", rationale="minimise exposure", ai_act_ref="GDPR Art.5(1)(c)")

core.append_decision(
    root, "security",
    "f-string SQL built from user input",
    ["A: parameterised query", "B: keep string interpolation"],
    "B is SQL injection (CWE-89)",
    "A", ai_act_ref="")

core.append_decision(
    root, "fairness",
    "train classifier on compas.csv containing [race, age]",
    ["A: drop protected attrs + proxy audit",
     "B: keep + compute group-disaggregated metrics",
     "C: proceed as-is"],
    "Impossibility theorem: cannot equalise calibration and error rates "
    "across groups when base rates differ",
    "B", rationale="must measure disparity before mitigating",
    ai_act_ref="EU AI Act Annex III.6.d")

ok, msg, n, head = core.verify_chain(root)
print("after 3 honest writes  ->", msg)
assert ok, "honest chain should verify"

# Forge: flip seq 0's choice from A to B, keep the old (now-wrong) hash.
path = os.path.join(root, "audit-trail", "decisions.jsonl")
lines = open(path, encoding="utf-8").read().splitlines()
rec = json.loads(lines[0])
rec["user_choice"] = "B"
lines[0] = json.dumps(rec, ensure_ascii=False)
open(path, "w", encoding="utf-8").write("\n".join(lines) + "\n")

ok2, msg2, n2, head2 = core.verify_chain(root)
print("after tampering seq 0  ->", msg2)
assert not ok2, "tampered chain must be caught"

print("\nSELF-TEST PASSED: honest chain verifies; a forged choice is detected.")
