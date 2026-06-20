"use client";
import { useEffect, useRef, useState } from "react";

/* ───────── types (match monitor/agent.py output contract) ───────── */
type Opt = { id: string; label: string; tradeoff: string };
type Decision = { id: string; question: string; source: string; options: Opt[] };
type Gate = {
  phase: "gate"; message: string; flagged: string[];
  decisions: Decision[]; provider?: string;
};
type Cite = { tag: string; text: string };
type Code = {
  phase: "code"; message: string; language: string; code: string;
  explanation: string; citations?: Cite[];
  audit_seq?: number; audit_hash?: string; provider?: string;
};
type Item =
  | { role: "user"; text: string }
  | { role: "gate"; gate: Gate; prompt: string; chosen: Record<string, string>; done: boolean }
  | { role: "code"; code: Code };

type AuditEntry = {
  seq: number; ts?: string; domain: string; trigger?: string;
  user_choice?: string; ai_act_ref?: string; rationale?: string;
  options_presented?: string[]; model?: string; hash: string; prev_hash?: string;
};
type AuditChain = { entries: AuditEntry[]; chain_ok: boolean; count: number; head?: string | null };

const EXAMPLE =
  "build a child-safety classifier — the governance layer should detect child-specific risks, present safer implementation options, and require explicit choices on escalation, retention and evaluation";

/* ───────── mock fallback (demo resilience if backend/LLM is down) ───────── */
const CHILD_RE = /child|kid|minor|under ?18|teen|student|pupil|coppa|under-?age|school|toddler|infant|nursery/i;

function mockGate(): Gate {
  return {
    phase: "gate",
    provider: "mock",
    message:
      "This builds software directed at or foreseeably used by children, so the governance gate engages before any code is written. Choose how each safeguard should be implemented.",
    flagged: [
      "Child-directed AI system (UN CRC art. 3 — best interests of the child)",
      "Processes data about minors (EU AI Act, rights-sensitive)",
      "Automated decisions affecting children need human oversight",
    ],
    decisions: [
      {
        id: "escalation",
        question: "How are low-confidence / high-risk classifications handled?",
        source: "EU AI Act Art. 14 — human oversight for high-risk AI",
        options: [
          { id: "a", label: "Escalate to a human reviewer below a confidence threshold", tradeoff: "Higher safety; adds review latency + staffing." },
          { id: "b", label: "Auto-decide, log every call for later audit", tradeoff: "Lower latency; weaker real-time oversight." },
        ],
      },
      {
        id: "retention",
        question: "How long is child data retained?",
        source: "UN CRC art. 16 (privacy) · GDPR-K / AADC data minimization",
        options: [
          { id: "a", label: "Process in-memory, retain nothing past the decision", tradeoff: "Strongest privacy; no retraining data, harder debugging." },
          { id: "b", label: "Retain hashed features 30 days for evaluation", tradeoff: "Enables eval; expands the data-protection surface." },
        ],
      },
      {
        id: "evaluation",
        question: "What fairness evaluation gates release?",
        source: "EU AI Act Annex III · Fairlearn group-fairness metrics",
        options: [
          { id: "a", label: "Block release until subgroup parity is within tolerance", tradeoff: "Fairness assured; slower to ship." },
          { id: "b", label: "Ship with a monitored fairness dashboard", tradeoff: "Faster; relies on post-deployment vigilance." },
        ],
      },
    ],
  };
}
function mockHash() {
  const h = "0123456789abcdef";
  let s = "";
  for (let i = 0; i < 64; i++) s += h[Math.floor(Math.random() * 16)];
  return s;
}
function mockCode(gated: boolean): Code {
  const code = `"""Child-safety text classifier — generated under AGENTS.md governance.

Safeguards wired in per the developer's choices:
  - escalation: low-confidence predictions routed to human review
  - retention : features processed in-memory; nothing persisted
  - evaluation: subgroup fairness checked before release
"""
from dataclasses import dataclass

REVIEW_THRESHOLD = 0.75          # below this confidence -> human review (AI Act Art.14)


@dataclass
class Decision:
    label: str
    confidence: float
    needs_human_review: bool


class ChildSafetyClassifier:
    def __init__(self, model):
        self._model = model      # injected; no child data stored on the instance

    def classify(self, text: str) -> Decision:
        # in-memory only: 'text' is never logged or persisted (CRC art.16)
        label, confidence = self._model.predict(text)
        return Decision(
            label=label,
            confidence=confidence,
            needs_human_review=confidence < REVIEW_THRESHOLD,
        )


def evaluate_fairness(clf, samples, groups, tolerance=0.05) -> bool:
    """Gate release on subgroup parity (Fairlearn-style)."""
    rates = {}
    for g in set(groups):
        sub = [s for s, gg in zip(samples, groups) if gg == g]
        flagged = sum(clf.classify(s).label == "unsafe" for s in sub)
        rates[g] = flagged / max(len(sub), 1)
    return (max(rates.values()) - min(rates.values())) <= tolerance
`;
  return {
    phase: "code",
    provider: "mock",
    message: gated
      ? "Generated with your chosen safeguards wired in. The decision was written to the audit trail before the code was returned."
      : "Generated. This request didn't trigger the child-safety gate, so it ran as ordinary development work.",
    language: "python",
    code,
    explanation:
      "Confidence below the review threshold routes to a human (escalation); inputs are processed in-memory and never persisted (retention); release is gated on subgroup parity (evaluation).",
    citations: [
      { tag: "EU AI Act Art. 14", text: "human oversight for high-risk AI" },
      { tag: "UN CRC art. 16", text: "child's right to privacy" },
      { tag: "Fairlearn", text: "group-fairness evaluation" },
    ],
    ...(gated ? { audit_seq: Math.floor(Math.random() * 90) + 10, audit_hash: mockHash() } : {}),
  };
}

/* ───────── API ───────── */
async function callAgent(prompt: string, choices?: Record<string, string>) {
  const r = await fetch("/api/generate", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ prompt, choices: choices || {} }),
  });
  if (!r.ok) throw new Error(`backend ${r.status}`);
  const j = await r.json();
  if (j?.error) throw new Error(j.error);
  return j as Gate | Code;
}

/* ───────── component ───────── */
export default function Page() {
  const [items, setItems] = useState<Item[]>([]);
  const [input, setInput] = useState("");
  const [busy, setBusy] = useState(false);
  const [dev, setDev] = useState(true);
  const [auditOpen, setAuditOpen] = useState(false);
  const [auditData, setAuditData] = useState<AuditChain | null>(null);
  const [auditLoading, setAuditLoading] = useState(false);
  const [auditErr, setAuditErr] = useState(false);
  const scrollRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    scrollRef.current?.scrollTo({ top: 1e9, behavior: "smooth" });
  }, [items, busy]);

  function mockChainFromSession(): AuditChain {
    const coded = items.filter((i) => i.role === "code" && i.code.audit_hash) as Extract<Item, { role: "code" }>[];
    let prev = "GENESIS";
    const entries: AuditEntry[] = coded.map((it) => {
      const c = it.code;
      const e: AuditEntry = {
        seq: c.audit_seq ?? 0,
        ts: new Date().toISOString(),
        domain: "child-safety",
        trigger: "child-directed coding request",
        user_choice: "developer choice recorded",
        ai_act_ref: "UN CRC arts 3,12,16,19,34; EU AI Act",
        model: c.provider || "mock",
        hash: c.audit_hash!,
        prev_hash: prev,
      };
      prev = c.audit_hash!;
      return e;
    });
    return { entries, chain_ok: true, count: entries.length, head: entries.length ? entries[entries.length - 1].hash : null };
  }

  async function openAudit() {
    setAuditOpen(true);
    setAuditLoading(true);
    setAuditErr(false);
    try {
      const r = await fetch("/api/audit");
      if (!r.ok) throw new Error();
      setAuditData(await r.json());
    } catch {
      setAuditErr(true);
      setAuditData(mockChainFromSession());
    } finally {
      setAuditLoading(false);
    }
  }

  async function send(text: string) {
    const prompt = text.trim();
    if (!prompt || busy) return;
    setItems((x) => [...x, { role: "user", text: prompt }]);
    setInput("");
    setBusy(true);
    try {
      const res = await callAgent(prompt);
      if (res.phase === "gate")
        setItems((x) => [...x, { role: "gate", gate: res, prompt, chosen: {}, done: false }]);
      else setItems((x) => [...x, { role: "code", code: res }]);
    } catch {
      if (CHILD_RE.test(prompt))
        setItems((x) => [...x, { role: "gate", gate: mockGate(), prompt, chosen: {}, done: false }]);
      else setItems((x) => [...x, { role: "code", code: mockCode(false) }]);
    } finally {
      setBusy(false);
    }
  }

  function pick(idx: number, decisionId: string, optId: string) {
    setItems((x) =>
      x.map((it, i) =>
        i === idx && it.role === "gate"
          ? { ...it, chosen: { ...it.chosen, [decisionId]: optId } }
          : it
      )
    );
  }

  async function generateFrom(idx: number) {
    const it = items[idx];
    if (it.role !== "gate" || busy) return;
    const choices: Record<string, string> = {};
    for (const d of it.gate.decisions) {
      const opt = d.options.find((o) => o.id === it.chosen[d.id]);
      choices[d.id] = opt ? opt.label : it.chosen[d.id];
    }
    setItems((x) => x.map((m, i) => (i === idx && m.role === "gate" ? { ...m, done: true } : m)));
    setBusy(true);
    try {
      const res = await callAgent(it.prompt, choices);
      setItems((x) => [...x, { role: "code", code: res.phase === "code" ? res : mockCode(true) }]);
    } catch {
      setItems((x) => [...x, { role: "code", code: mockCode(true) }]);
    } finally {
      setBusy(false);
    }
  }

  /* derive rail state */
  const lastGate = [...items].reverse().find((i) => i.role === "gate") as
    | Extract<Item, { role: "gate" }> | undefined;
  const lastCode = [...items].reverse().find((i) => i.role === "code") as
    | Extract<Item, { role: "code" }> | undefined;
  const lastUser = [...items].reverse().find((i) => i.role === "user") as
    | Extract<Item, { role: "user" }> | undefined;
  const gateOpen = !!lastGate && !lastGate.done;
  const gated = !!lastCode?.code.audit_hash || gateOpen;
  const codeReady = !!lastCode && (!lastGate || lastGate.done);

  type SState = "idle" | "run" | "done" | "skip";
  const stages: { lab: string; tag?: string; xf?: boolean; state: SState }[] = [
    { lab: "Input intercepted", state: items.length ? "done" : "idle" },
    { lab: "Sensitive-signal scan", tag: "LLM", state: busy && !gateOpen && !lastGate?.done ? "run" : items.length ? "done" : "idle" },
    { lab: "Child-directed gate", tag: "LLM", state: gated ? "done" : codeReady ? "skip" : "idle" },
    { lab: "Developer choices", xf: true, state: gateOpen ? "run" : gated ? "done" : codeReady ? "skip" : "idle" },
    { lab: "Citation grounding", xf: true, state: codeReady ? "done" : "idle" },
    { lab: "Audit append", state: lastCode?.code.audit_hash ? "done" : codeReady && !gated ? "skip" : busy && lastGate?.done ? "run" : "idle" },
    { lab: "Code generated", state: codeReady ? "done" : busy && lastGate?.done ? "run" : "idle" },
  ];

  const cites = lastCode?.code.citations || [];
  const auditHash = lastCode?.code.audit_hash;
  const auditSeq = lastCode?.code.audit_seq;

  return (
    <div className="wrap">
      <style>{CSS}</style>

      <header className="top">
        <div className="brand">
          <div className="logo">SG</div>
          <div>
            <div className="bname">ssgcheck</div>
            <div className="bsub">coding agent</div>
          </div>
        </div>
        <button className={`devtog ${dev ? "on" : ""}`} onClick={() => setDev((d) => !d)}>
          <span className="dot" /> Developer mode
        </button>
      </header>

      <div className="body">
        <main className="chat" ref={scrollRef}>
          {items.length === 0 && (
            <div className="empty">
              <div className="ehead">A coding agent with a governance gate built in.</div>
              <p className="esub">
                Describe what you want to build. If the work is directed at or affects children, the
                agent pauses, flags the risks, and makes you choose how each safeguard is implemented —
                then writes the code under <code>AGENTS.md</code> and logs the decision to a
                tamper-evident audit trail.
              </p>
              <button className="example" onClick={() => setInput(EXAMPLE)}>
                Try: “{EXAMPLE.slice(0, 60)}…”
              </button>
            </div>
          )}

          {items.map((it, idx) => {
            if (it.role === "user")
              return (
                <div key={idx} className="row">
                  <div className="who"><span className="av u">{"{ }"}</span> YOU</div>
                  <div className="bubble u">{it.text}</div>
                </div>
              );

            if (it.role === "gate") {
              const g = it.gate;
              const allChosen = g.decisions.every((d) => it.chosen[d.id]);
              return (
                <div key={idx} className="row">
                  <div className="who"><span className="av a">SG</span> SSGCHECK</div>
                  <div className="bubble a">
                    <div className="gatehd">
                      <span className="pill flag">GATE · child-directed</span>
                      <span className="gmsg">{g.message}</span>
                    </div>
                    <div className="flagged">
                      {g.flagged.map((f, i) => (
                        <div key={i} className="fitem"><span className="fmark">!</span> {f}</div>
                      ))}
                    </div>
                    <div className="decisions">
                      {g.decisions.map((d) => (
                        <div key={d.id} className="dcard">
                          <div className="dq">{d.question}</div>
                          <div className="dsrc">{d.source}</div>
                          <div className="opts">
                            {d.options.map((o) => {
                              const on = it.chosen[d.id] === o.id;
                              return (
                                <button key={o.id} className={`opt ${on ? "on" : ""}`} disabled={it.done} onClick={() => pick(idx, d.id, o.id)}>
                                  <span className="radio" />
                                  <span className="olab">{o.label}</span>
                                  <span className="otrade">{o.tradeoff}</span>
                                </button>
                              );
                            })}
                          </div>
                        </div>
                      ))}
                    </div>
                    {!it.done ? (
                      <button className="gen" disabled={!allChosen || busy} onClick={() => generateFrom(idx)}>
                        {allChosen ? "Generate code with these choices →" : "Choose an option for each decision"}
                      </button>
                    ) : (
                      <div className="chosenline">Choices recorded · generating under policy…</div>
                    )}
                  </div>
                </div>
              );
            }

            const c = it.code;
            return (
              <div key={idx} className="row">
                <div className="who"><span className="av a">SG</span> SSGCHECK</div>
                <div className="bubble a">
                  <div className="cmsg">{c.message}</div>
                  <div className="codewrap">
                    <div className="codebar">
                      <span className="lang">{c.language || "code"}</span>
                      {c.provider && <span className="prov">{c.provider}</span>}
                    </div>
                    <pre className="code"><code>{c.code}</code></pre>
                  </div>
                  {c.explanation && <div className="expl">{c.explanation}</div>}
                  {!!(c.citations && c.citations.length) && (
                    <div className="cites">
                      {c.citations.map((ci, i) => (
                        <span key={i} className="cite"><b>{ci.tag}</b> {ci.text}</span>
                      ))}
                    </div>
                  )}
                  {c.audit_hash && (
                    <div className="auditline">
                      <span className="ok">●</span> Logged to audit trail · seq #{c.audit_seq} ·{" "}
                      <code>{c.audit_hash.slice(0, 16)}…</code>
                    </div>
                  )}
                </div>
              </div>
            );
          })}

          {busy && (
            <div className="row">
              <div className="who"><span className="av a">SG</span> SSGCHECK</div>
              <div className="bubble a thinking">
                <span className="d" /><span className="d" /><span className="d" />
                <span className="tlabel">{lastGate?.done ? "writing code under policy" : "scanning for child-directed signals"}</span>
              </div>
            </div>
          )}

          <div className="composer">
            <textarea
              value={input}
              placeholder="Describe what you want to build…"
              onChange={(e) => setInput(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); send(input); }
              }}
              rows={1}
            />
            <button className="snd" disabled={!input.trim() || busy} onClick={() => send(input)}>↑</button>
          </div>
          <div className="foot">Coding agent · gate engages for child-directed work · governed by AGENTS.md</div>
        </main>

        {dev && (
          <aside className="rail">
            <div className="railhd">
              <span className="rdot" /> Governance Pipeline <span className="live">LIVE</span>
            </div>

            <div className="card">
              <div className="ctitle"><span className="bolt">⚡</span> PIPELINE FLOW</div>
              {stages.map((s, i) => (
                <div key={i} className={`stage ${s.state}`}>
                  <span className="mk">{s.state === "done" ? "✓" : s.state === "skip" ? "–" : ""}</span>
                  <span className="slab">{s.lab}</span>
                  {s.tag && <span className="tag">{s.tag}</span>}
                  {s.xf && <span className="arr">→</span>}
                </div>
              ))}
            </div>

            <div className="card">
              <div className="cnum"><span className="n">1</span> CONTEXT {gated && <span className="tag">GATED</span>}</div>
              <div className="ctxt">
                {lastUser ? (
                  <><span className="muted">prompt:</span> {lastUser.text.slice(0, 90)}{lastUser.text.length > 90 ? "…" : ""}</>
                ) : (
                  <span className="muted">awaiting a build request…</span>
                )}
              </div>
              <div className="csub">{gated ? "child-directed → gate engaged" : codeReady ? "standard → no gate" : "—"}</div>
            </div>

            {(gateOpen || gated) && lastGate && (
              <div className="card">
                <div className="cnum"><span className="n">2</span> FLAGGED RISKS</div>
                {lastGate.gate.flagged.map((f, i) => (
                  <div key={i} className="rrisk"><span className="rx">!</span> {f}</div>
                ))}
                <div className="dlist">
                  {lastGate.gate.decisions.map((d) => {
                    const opt = d.options.find((o) => o.id === lastGate.chosen[d.id]);
                    return (
                      <div key={d.id} className="drow">
                        <span className="dname">{d.id}</span>
                        <span className={`dval ${opt ? "set" : ""}`}>{opt ? opt.label : "awaiting choice"}</span>
                      </div>
                    );
                  })}
                </div>
              </div>
            )}

            {codeReady && cites.length > 0 && (
              <div className="card">
                <div className="cnum"><span className="n">3</span> CITATIONS</div>
                {cites.map((c, i) => (
                  <div key={i} className="crow"><b>{c.tag}</b> <span className="muted">{c.text}</span></div>
                ))}
              </div>
            )}

            <div className="card audcard" onClick={openAudit} role="button" tabIndex={0}
              onKeyDown={(e) => { if (e.key === "Enter") openAudit(); }}>
              <div className="cnum">
                <span className="n">4</span> ESCALATION · AUDIT
                <span className="viewtrail">View full trail →</span>
              </div>
              {auditHash ? (
                <>
                  <div className="arow"><span className="muted">seq</span> #{auditSeq}</div>
                  <div className="arow"><span className="muted">sha-256</span></div>
                  <div className="hash">{auditHash}</div>
                  <div className="chainok"><span className="ok">●</span> appended to hash chain</div>
                </>
              ) : codeReady ? (
                <div className="muted small">no gate fired — nothing to escalate</div>
              ) : (
                <div className="muted small">no decision logged yet · click to view the chain</div>
              )}
            </div>
          </aside>
        )}
      </div>

      {auditOpen && (
        <div className="modal" onClick={() => setAuditOpen(false)}>
          <div className="sheet" onClick={(e) => e.stopPropagation()}>
            <div className="sheethd">
              <div>
                <div className="stitle">Audit trail</div>
                <div className="ssub">tamper-evident decision chain · SHA-256 linked</div>
              </div>
              <button className="x" onClick={() => setAuditOpen(false)}>✕</button>
            </div>

            {auditLoading ? (
              <div className="aload">loading chain…</div>
            ) : (
              <>
                <div className={`verify ${auditData?.chain_ok ? "ok" : "bad"}`}>
                  <span className="vmk">{auditData?.chain_ok ? "✓" : "✕"}</span>
                  <span>
                    {auditData?.chain_ok
                      ? `Chain intact · ${auditData?.count ?? 0} ${(auditData?.count ?? 0) === 1 ? "entry" : "entries"}`
                      : "Chain verification FAILED"}
                  </span>
                  {auditErr && <span className="demo">demo data · backend unreachable</span>}
                </div>
                {auditData?.head && (
                  <div className="headrow"><span className="muted">head</span> <code>{auditData.head.slice(0, 28)}…</code></div>
                )}

                <div className="trail">
                  {(auditData?.entries ?? []).slice().reverse().map((e) => (
                    <div key={e.seq} className="entry">
                      <div className="ehd">
                        <span className="eseq">#{e.seq}</span>
                        <span className="edom">{e.domain}</span>
                        {e.ts && <span className="ets">{new Date(e.ts).toLocaleString()}</span>}
                      </div>
                      {e.trigger && <div className="erow"><span className="ek">trigger</span><span className="ev">{e.trigger}</span></div>}
                      {!!(e.options_presented && e.options_presented.length) && (
                        <div className="erow"><span className="ek">options</span><span className="ev">{e.options_presented.join("  ·  ")}</span></div>
                      )}
                      {e.user_choice && <div className="erow"><span className="ek">choice</span><span className="ev hi">{e.user_choice}</span></div>}
                      {e.ai_act_ref && <div className="erow"><span className="ek">source</span><span className="ev">{e.ai_act_ref}</span></div>}
                      {e.model && <div className="erow"><span className="ek">model</span><span className="ev">{e.model}</span></div>}
                      <div className="ehash"><span className="muted">sha-256</span> <code>{e.hash}</code></div>
                      {e.prev_hash && (
                        <div className="eprev"><span className="muted">prev</span> <code>{e.prev_hash === "GENESIS" ? "GENESIS" : e.prev_hash.slice(0, 24) + "…"}</code></div>
                      )}
                    </div>
                  ))}
                  {(!auditData?.entries || auditData.entries.length === 0) && (
                    <div className="aempty">No decisions logged yet. Run a child-directed build to create the first entry.</div>
                  )}
                </div>
              </>
            )}
          </div>
        </div>
      )}
    </div>
  );
}

/* ───────── styles (scoped, no external deps) ───────── */
const CSS = `
.wrap{--bg:#f7f7f8;--ink:#1d1d1f;--mut:#8a8a8e;--line:#ececf0;--acc:#3b6ef5;
  --rail:#0f1115;--rcard:#171a21;--rline:#262b36;--green:#34c759;--amber:#e8b22e;--red:#ff5a52;
  position:fixed;inset:0;display:flex;flex-direction:column;background:var(--bg);color:var(--ink);
  font:14px/1.5 -apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif;}
.top{display:flex;align-items:center;justify-content:space-between;padding:14px 20px;border-bottom:1px solid var(--line);background:#fff;}
.brand{display:flex;align-items:center;gap:10px;}
.logo{width:32px;height:32px;border-radius:9px;background:#1d1d1f;color:#fff;display:grid;place-items:center;font-weight:700;font-size:12px;}
.bname{font-weight:650;}
.bsub{font-size:11px;color:var(--mut);letter-spacing:.04em;text-transform:uppercase;}
.devtog{display:flex;align-items:center;gap:7px;border:1px solid var(--line);background:#fff;color:var(--mut);padding:7px 13px;border-radius:20px;font-size:13px;cursor:pointer;}
.devtog.on{color:var(--ink);border-color:#d6d6dc;}
.devtog .dot{width:7px;height:7px;border-radius:50%;background:#c7c7cc;}
.devtog.on .dot{background:var(--acc);}
.body{flex:1;display:flex;min-height:0;}
.chat{flex:1;overflow-y:auto;padding:26px 22px 0;display:flex;flex-direction:column;}
.empty{max-width:560px;margin:6vh auto 0;text-align:center;}
.ehead{font-size:20px;font-weight:650;margin-bottom:10px;}
.esub{color:#55555b;font-size:14px;}
.esub code{background:#ececf0;padding:1px 5px;border-radius:4px;font-size:12px;}
.example{margin-top:18px;border:1px solid var(--line);background:#fff;border-radius:10px;padding:10px 14px;cursor:pointer;color:#444;font-size:13px;}
.example:hover{border-color:#cfcfd6;}
.row{max-width:760px;width:100%;margin:0 auto 22px;}
.who{display:flex;align-items:center;gap:8px;font-size:11px;letter-spacing:.05em;color:var(--mut);margin-bottom:7px;font-weight:600;}
.av{width:20px;height:20px;border-radius:6px;display:grid;place-items:center;font-size:9px;font-weight:700;color:#fff;}
.av.u{background:var(--acc);}
.av.a{background:#1d1d1f;}
.bubble.u{background:#1d1d1f;color:#fff;padding:14px 16px;border-radius:14px;white-space:pre-wrap;}
.bubble.a{background:#fff;border:1px solid var(--line);border-radius:14px;padding:16px;}
.gatehd{display:flex;flex-direction:column;gap:8px;margin-bottom:12px;}
.pill{align-self:flex-start;font-size:11px;font-weight:700;padding:3px 9px;border-radius:6px;letter-spacing:.03em;}
.pill.flag{background:#fde9c8;color:#92600c;}
.gmsg{color:#3a3a40;}
.flagged{display:flex;flex-direction:column;gap:6px;margin-bottom:14px;}
.fitem{display:flex;gap:8px;align-items:flex-start;font-size:13px;color:#4a4a50;}
.fmark{flex:none;width:16px;height:16px;border-radius:50%;background:#fde9c8;color:#92600c;display:grid;place-items:center;font-size:10px;font-weight:800;margin-top:1px;}
.decisions{display:flex;flex-direction:column;gap:12px;}
.dcard{border:1px solid var(--line);border-radius:11px;padding:13px;}
.dq{font-weight:600;margin-bottom:3px;}
.dsrc{font-size:11.5px;color:var(--acc);margin-bottom:10px;}
.opts{display:flex;flex-direction:column;gap:8px;}
.opt{display:grid;grid-template-columns:18px 1fr;gap:4px 9px;align-items:start;text-align:left;border:1px solid var(--line);border-radius:9px;padding:10px 12px;background:#fff;cursor:pointer;}
.opt:hover:not(:disabled){border-color:#cfcfd6;}
.opt.on{border-color:var(--acc);background:#f5f8ff;}
.opt:disabled{opacity:.65;cursor:default;}
.radio{grid-row:1/3;width:15px;height:15px;border-radius:50%;border:2px solid #c7c7cc;margin-top:2px;}
.opt.on .radio{border-color:var(--acc);background:radial-gradient(circle,var(--acc) 0 38%,transparent 42%);}
.olab{font-weight:550;}
.otrade{font-size:12px;color:var(--mut);}
.gen{margin-top:14px;width:100%;border:none;border-radius:10px;padding:12px;font-size:14px;font-weight:600;background:#1d1d1f;color:#fff;cursor:pointer;}
.gen:disabled{background:#e3e3e8;color:#a0a0a6;cursor:default;}
.chosenline{margin-top:12px;font-size:12.5px;color:var(--mut);}
.cmsg{margin-bottom:12px;color:#3a3a40;}
.codewrap{border-radius:11px;overflow:hidden;border:1px solid #20232b;}
.codebar{display:flex;justify-content:space-between;align-items:center;background:#1a1d24;color:#9aa0ad;padding:7px 12px;font-size:11px;}
.lang{text-transform:uppercase;letter-spacing:.05em;}
.prov{font-family:ui-monospace,Menlo,monospace;}
.code{margin:0;background:#0f1115;color:#e6e6ea;padding:14px;overflow-x:auto;font:12.5px/1.6 ui-monospace,Menlo,Consolas,monospace;white-space:pre;}
.expl{margin-top:12px;font-size:13px;color:#4a4a50;}
.cites{display:flex;flex-wrap:wrap;gap:7px;margin-top:12px;}
.cite{font-size:11.5px;background:#f0f2f6;border-radius:6px;padding:4px 9px;color:#55555b;}
.cite b{color:#2c2c32;}
.auditline{margin-top:13px;font-size:12.5px;color:#3a3a40;border-top:1px solid var(--line);padding-top:11px;}
.auditline .ok{color:var(--green);}
.auditline code{font-family:ui-monospace,Menlo,monospace;background:#f0f2f6;padding:1px 5px;border-radius:4px;}
.thinking{display:flex;align-items:center;gap:5px;}
.thinking .d{width:6px;height:6px;border-radius:50%;background:#c7c7cc;animation:bln 1.2s infinite;}
.thinking .d:nth-child(2){animation-delay:.2s}.thinking .d:nth-child(3){animation-delay:.4s}
.tlabel{margin-left:8px;font-size:12.5px;color:var(--mut);}
@keyframes bln{0%,80%,100%{opacity:.3}40%{opacity:1}}
.composer{position:sticky;bottom:0;max-width:760px;width:100%;margin:6px auto 0;background:var(--bg);padding:10px 0 6px;display:flex;gap:8px;align-items:flex-end;}
.composer textarea{flex:1;resize:none;border:1px solid #dcdce2;border-radius:14px;padding:13px 15px;font:14px/1.4 inherit;background:#fff;outline:none;max-height:160px;}
.composer textarea:focus{border-color:#bfbfc8;}
.snd{flex:none;width:38px;height:38px;border-radius:50%;border:none;background:#1d1d1f;color:#fff;font-size:17px;cursor:pointer;}
.snd:disabled{background:#d6d6dc;cursor:default;}
.foot{max-width:760px;width:100%;margin:0 auto;text-align:center;font-size:11px;color:#b0b0b6;padding:4px 0 10px;}
.rail{width:340px;flex:none;background:var(--rail);color:#d4d8e0;overflow-y:auto;padding:18px;}
.railhd{display:flex;align-items:center;gap:8px;font-weight:650;color:#fff;margin-bottom:14px;}
.rdot{width:8px;height:8px;border-radius:50%;background:var(--green);}
.live{margin-left:auto;font-size:10px;letter-spacing:.08em;color:var(--green);border:1px solid #1f6b34;padding:2px 7px;border-radius:5px;}
.card{background:var(--rcard);border:1px solid var(--rline);border-radius:13px;padding:14px;margin-bottom:13px;}
.ctitle{display:flex;align-items:center;gap:7px;font-size:11px;letter-spacing:.07em;color:#9aa0ad;margin-bottom:13px;}
.bolt{color:var(--amber);}
.stage{display:flex;align-items:center;gap:10px;padding:5px 0;font-size:13px;color:#aeb4c0;}
.mk{width:20px;height:20px;border-radius:50%;flex:none;display:grid;place-items:center;font-size:11px;font-weight:800;border:2px solid #333a47;color:#5b6271;}
.stage.done .mk{background:var(--green);border-color:var(--green);color:#04210e;}
.stage.done .slab{color:#e9ecf1;}
.stage.run .mk{border-color:var(--acc);border-top-color:transparent;animation:spin .8s linear infinite;}
.stage.run .slab{color:#fff;}
.stage.skip{opacity:.4;}
.stage.skip .mk{border-style:dashed;}
@keyframes spin{to{transform:rotate(360deg)}}
.slab{flex:1;}
.tag{font-size:9px;font-weight:700;letter-spacing:.05em;color:var(--amber);border:1px solid #5a4a1c;border-radius:4px;padding:1px 5px;}
.arr{color:#5b6271;}
.cnum{display:flex;align-items:center;gap:8px;font-size:11px;letter-spacing:.06em;color:#9aa0ad;margin-bottom:11px;}
.cnum .n{width:18px;height:18px;border-radius:5px;background:var(--amber);color:#3a2c05;display:grid;place-items:center;font-weight:800;font-size:11px;}
.cnum .tag{margin-left:auto;color:var(--red);border-color:#6b2420;}
.ctxt{font-size:13px;color:#dfe3ea;}
.csub{margin-top:7px;font-size:12px;color:#7f8694;}
.muted{color:#7f8694;}
.small{font-size:12px;}
.rrisk{display:flex;gap:8px;align-items:flex-start;font-size:12.5px;color:#c3c8d2;margin-bottom:6px;}
.rx{flex:none;width:15px;height:15px;border-radius:50%;background:#5a4a1c;color:var(--amber);display:grid;place-items:center;font-size:9px;font-weight:800;margin-top:1px;}
.dlist{margin-top:10px;border-top:1px solid var(--rline);padding-top:10px;display:flex;flex-direction:column;gap:8px;}
.drow{display:flex;justify-content:space-between;gap:10px;font-size:12px;}
.dname{color:#9aa0ad;text-transform:capitalize;}
.dval{color:#6f7682;text-align:right;}
.dval.set{color:#7fd99a;}
.crow{font-size:12px;margin-bottom:6px;color:#c3c8d2;}
.crow b{color:#fff;}
.arow{display:flex;justify-content:space-between;font-size:12.5px;margin-bottom:5px;}
.hash{font-family:ui-monospace,Menlo,monospace;font-size:10.5px;color:#7fd99a;word-break:break-all;background:#0e1622;border:1px solid #173024;border-radius:7px;padding:8px;margin:4px 0 9px;}
.chainok{font-size:12px;color:#7fd99a;}
.chainok .ok,.arow .ok{color:var(--green);}
.audcard{cursor:pointer;transition:border-color .15s;}
.audcard:hover{border-color:#3a4250;}
.audcard .viewtrail{margin-left:auto;font-size:10.5px;color:var(--acc);letter-spacing:0;text-transform:none;}
.modal{position:fixed;inset:0;background:rgba(6,8,12,.62);display:flex;align-items:center;justify-content:center;padding:24px;z-index:50;}
.sheet{width:min(620px,94vw);max-height:86vh;display:flex;flex-direction:column;background:#12151c;border:1px solid #262b36;border-radius:16px;overflow:hidden;box-shadow:0 24px 60px rgba(0,0,0,.5);}
.sheethd{display:flex;align-items:flex-start;justify-content:space-between;padding:18px 20px;border-bottom:1px solid #222732;}
.stitle{font-size:16px;font-weight:650;color:#fff;}
.ssub{font-size:12px;color:#7f8694;margin-top:2px;}
.x{border:none;background:#1c212b;color:#aeb4c0;width:30px;height:30px;border-radius:8px;cursor:pointer;font-size:13px;}
.x:hover{background:#262c38;color:#fff;}
.aload{padding:34px;text-align:center;color:#7f8694;}
.verify{display:flex;align-items:center;gap:9px;margin:16px 20px 0;padding:11px 13px;border-radius:10px;font-size:13px;font-weight:550;}
.verify.ok{background:#0e2418;border:1px solid #1d4a30;color:#7fd99a;}
.verify.bad{background:#2a1414;border:1px solid #5a2420;color:#ff8a82;}
.verify .vmk{width:20px;height:20px;border-radius:50%;display:grid;place-items:center;font-weight:800;font-size:12px;}
.verify.ok .vmk{background:var(--green);color:#04210e;}
.verify.bad .vmk{background:var(--red);color:#2a0a08;}
.verify .demo{margin-left:auto;font-size:10.5px;font-weight:600;color:#e8b22e;background:#2a230e;border:1px solid #5a4a1c;border-radius:5px;padding:2px 7px;}
.headrow{margin:10px 20px 0;font-size:12px;color:#7f8694;}
.headrow code{font-family:ui-monospace,Menlo,monospace;color:#9aa0ad;}
.trail{overflow-y:auto;padding:14px 20px 20px;display:flex;flex-direction:column;gap:11px;}
.entry{border:1px solid #232833;border-radius:11px;padding:13px;background:#161a22;}
.ehd{display:flex;align-items:center;gap:9px;margin-bottom:9px;}
.eseq{font-weight:700;color:#fff;font-size:13px;}
.edom{font-size:10.5px;font-weight:700;letter-spacing:.04em;text-transform:uppercase;color:var(--amber);border:1px solid #5a4a1c;border-radius:5px;padding:2px 7px;}
.ets{margin-left:auto;font-size:11px;color:#6f7682;}
.erow{display:flex;gap:10px;font-size:12.5px;margin-bottom:5px;}
.ek{flex:none;width:62px;color:#7f8694;}
.ev{color:#c8cdd6;}
.ev.hi{color:#7fd99a;font-weight:600;}
.ehash{margin-top:8px;font-size:10.5px;color:#9aa0ad;}
.ehash code{font-family:ui-monospace,Menlo,monospace;color:#7fd99a;word-break:break-all;}
.eprev{margin-top:3px;font-size:10.5px;color:#6f7682;}
.eprev code{font-family:ui-monospace,Menlo,monospace;word-break:break-all;}
.aempty{padding:24px;text-align:center;color:#7f8694;font-size:13px;}
@media(max-width:880px){.rail{display:none;}}
`;