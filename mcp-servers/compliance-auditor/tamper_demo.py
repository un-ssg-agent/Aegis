"""Tamper demo — show that hand-editing the audit log is detected.

This is the "moat" demo for judges. It builds a small honest chain, then runs
several kinds of manual tampering on fresh copies and shows what `verify`
reports for each. It is SAFE: it works in a throwaway temp directory and never
touches your real audit-trail/decisions.jsonl.

Run:
    uv run python mcp-servers/compliance-auditor/tamper_demo.py

What it demonstrates:
  1. Flip a logged choice, leave the hash      -> caught: content altered
  2. Garble the stored hash                     -> caught: content altered
  3. Delete a whole record                      -> caught: chain link broken
  4. "Smart forger": edit a MIDDLE record AND
     recompute its hash                          -> still caught at the NEXT record
  5. Honest caveat: edit the LAST record AND
     recompute its hash                          -> NOT caught by the chain alone
     (why a signed/anchored head hash matters — see docs/design.md §13, M6)
"""
import hashlib
import json
import os
import shutil
import tempfile

import core


def build_chain(root: str) -> None:
    core.append_decision(root, "privacy",
                         "SELECT * over user_profile -> frontend",
                         ["A: id,name only", "B: all fields"],
                         "B exposes PII beyond need", "A",
                         rationale="data minimisation", ai_act_ref="GDPR Art.5(1)(c)")
    core.append_decision(root, "security",
                         "f-string SQL from user input",
                         ["A: parameterised", "B: interpolation"],
                         "B is SQL injection (CWE-89)", "A")
    core.append_decision(root, "fairness",
                         "train on compas_data.csv [race, age]",
                         ["A: drop+audit", "B: keep+group metrics", "C: proceed"],
                         "impossibility theorem", "B",
                         ai_act_ref="EU AI Act Annex III.6.d")


def read_lines(path: str) -> list[str]:
    return open(path, encoding="utf-8").read().splitlines()


def write_lines(path: str, lines: list[str]) -> None:
    open(path, "w", encoding="utf-8").write("\n".join(lines) + "\n")


def recompute_hash(rec: dict) -> str:
    """What a 'smart' forger does: recompute THIS record's own hash after editing
    it (using the project's exact canonicalisation)."""
    return hashlib.sha256(core._canonical(rec).encode("utf-8")).hexdigest()


def show_verify(root: str, label: str) -> None:
    ok, msg, n, head = core.verify_chain(root)
    icon = "✅" if ok else "❌"
    print(f"   {icon} verify: {msg}")


def fresh_copy(pristine: str, scenario: str) -> str:
    """Copy the pristine trail into a new sandbox so each scenario is isolated."""
    d = tempfile.mkdtemp(prefix=f"tamper-{scenario}-")
    os.makedirs(os.path.join(d, "audit-trail"), exist_ok=True)
    shutil.copy(pristine, os.path.join(d, "audit-trail", "decisions.jsonl"))
    return d


def main() -> None:
    base = tempfile.mkdtemp(prefix="tamper-base-")
    build_chain(base)
    pristine = core._log_file(base)
    print("Built an honest 3-record chain.")
    show_verify(base, "pristine")

    # 1) Flip a logged choice, leave the old hash in place.
    print("\n[1] Flip seq 0 choice  A -> B  (attacker forgets to fix the hash)")
    root = fresh_copy(pristine, "flip")
    path = core._log_file(root)
    lines = read_lines(path); rec = json.loads(lines[0])
    print(f"    before: user_choice={rec['user_choice']!r}")
    rec["user_choice"] = "B"
    lines[0] = json.dumps(rec, ensure_ascii=False); write_lines(path, lines)
    print(f"    after:  user_choice={rec['user_choice']!r}  (hash left unchanged)")
    show_verify(root, "flip")

    # 2) Garble the stored hash directly.
    print("\n[2] Overwrite seq 1's stored hash with garbage")
    root = fresh_copy(pristine, "garble")
    path = core._log_file(root)
    lines = read_lines(path); rec = json.loads(lines[1])
    rec["hash"] = "deadbeef" * 8
    lines[1] = json.dumps(rec, ensure_ascii=False); write_lines(path, lines)
    show_verify(root, "garble")

    # 3) Delete a record entirely.
    print("\n[3] Delete seq 1 (remove the line)")
    root = fresh_copy(pristine, "delete")
    path = core._log_file(root)
    lines = read_lines(path); del lines[1]; write_lines(path, lines)
    show_verify(root, "delete")

    # 4) Smart forger: edit a MIDDLE record AND recompute its own hash.
    print("\n[4] Smart forger: edit seq 0 AND recompute seq 0's own hash")
    root = fresh_copy(pristine, "smart-mid")
    path = core._log_file(root)
    lines = read_lines(path); rec = json.loads(lines[0])
    rec["user_choice"] = "B"
    rec["hash"] = recompute_hash(rec)          # rec passes its OWN check now
    lines[0] = json.dumps(rec, ensure_ascii=False); write_lines(path, lines)
    print("    seq 0 now self-consistent — but seq 1 still points at the OLD hash")
    show_verify(root, "smart-mid")             # caught at seq 1 (the chain link)

    # 5) Honest caveat: edit the LAST record AND recompute its hash.
    print("\n[5] Honest caveat: edit the LAST record (seq 2) AND recompute its hash")
    root = fresh_copy(pristine, "smart-last")
    path = core._log_file(root)
    lines = read_lines(path); rec = json.loads(lines[-1])
    rec["user_choice"] = "C"
    rec["hash"] = recompute_hash(rec)
    lines[-1] = json.dumps(rec, ensure_ascii=False); write_lines(path, lines)
    show_verify(root, "smart-last")
    print("    ^ NOT caught by the chain alone: nothing downstream links to the head.")
    print("      Mitigation = sign / externally anchor the head hash (design.md §13, M6).")

    print("\nSummary: every edit is caught EXCEPT recomputing the head's own hash,")
    print("which is exactly why the head hash must be anchored outside the file.")


if __name__ == "__main__":
    main()
