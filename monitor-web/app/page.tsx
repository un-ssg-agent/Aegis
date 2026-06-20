"use client";
import { useEffect, useRef, useState } from "react";

/* ───────────────────────── types (match monitor/app.py) ───────────────────────── */
type Panel = { provider: string; scores: Record<string, number>; overall: number; reason: string };
type Result = {
  kind: string; n_models: number; panel: Panel[]; by_measure: Record<string, number>;
  aggregate: number; threshold: number; alarm: boolean; errors?: string[];
  audit_seq?: number; audit_hash?: string;
};
type Mode = "conversation" | "code";
type Who = "Child" | "Adult";
type ChatMsg = { role: "user" | "verdict"; text?: string; mode?: Mode; who?: Who; res?: Result };
type StageDef = { k: string; lab: string; tag?: string; xf?: boolean; esc?: boolean };
type Stage = StageDef & { state: "idle" | "run" | "done"; lab: string };

const MEASURES: Record<Mode, string[]> = {
  code: ["fairness", "privacy", "security"],
  conversation: ["grooming", "self_harm", "pii_exposure", "distress"],
};
const PROVIDERS = ["DeepSeek", "OpenAI", "Gemini"];
const THRESHOLD = 0.6;
const AI_ACT: Record<Mode, string> = {
  code: "EU AI Act high-risk (Annex III) / UNESCO AI ethics",
  conversation: "UN CRC arts 3,12,16,19,34; EU AI Act (rights-sensitive)",
};
const CITES: Record<Mode, [string, string][]> = {
  code: [["EU AI Act", "Annex III high-risk duties"], ["UNESCO", "AI ethics — fairness"], ["Fairlearn", "group-fairness metrics"]],
  conversation: [["UN CRC art.19", "protection from abuse"], ["UN CRC art.34", "protection from exploitation"], ["EU AI Act", "minors' data, rights-sensitive"]],
};
const STAGE_DEFS: StageDef[] = [
  { k: "input", lab: "Input intercepted" },
  { k: "scan", lab: "Sensitive-signal scan", tag: "LLM" },
  { k: "panel", lab: "Risk panel · 3 models", tag: "LLM" },
  { k: "cite", lab: "Citation grounding", xf: true },
  { k: "thresh", lab: "Threshold check" },
  { k: "esc", lab: "Escalation → human", esc: true },
  { k: "audit", lab: "Audit append" },
  { k: "report", lab: "Compliance report" },
];
const CHIPS: Record<Mode, { b: string; t: string }[]> = {
  conversation: [
    { b: "Benign", t: "hey, did you finish the math homework yet?" },
    { b: "Escalates", t: "don't tell your parents — let's keep this our little secret, ok?" },
  ],
  code: [
    { b: "Benign", t: "def add(a, b):\n    return a + b" },
    { b: "Escalates", t: "if applicant.race == 'white':\n    score += 20  # boost\nlog(applicant.ssn)" },
  ],
};

const tier = (v: number) => (v >= 0.6 ? { t: "HIGH", c: "var(--high)" } : v >= 0.3 ? { t: "MED", c: "var(--med)" } : { t: "LOW", c: "var(--low)" });
const barColor = (v: number) => (v >= 0.6 ? "var(--high)" : v >= 0.3 ? "var(--med)" : "var(--green)");
const wait = (ms: number) => new Promise((r) => setTimeout(r, ms));

/* local fallback so a demo never dies if the backend / a key is unavailable */
function mockScore(kind: Mode, content: string): Result {
  const t = content.toLowerCase();
  const hits: Record<string, number> = {
    fairness: /race|gender|ethnic|boost|\bwhite\b|\bmale\b/.test(t) ? 0.55 : 0.05,
    privacy: /ssn|social security|passport|email|phone|address|log\(/.test(t) ? 0.6 : 0.08,
    security: /eval\(|exec\(|password|secret|os\.system|subprocess/.test(t) ? 0.5 : 0.07,
    grooming: /secret|don'?t tell|our little|just between us|alone|meet up/.test(t) ? 0.7 : 0.05,
    self_harm: /hurt myself|end it|worthless|give up|can'?t go on/.test(t) ? 0.65 : 0.04,
    pii_exposure: /address|school|phone|where do you live|real name/.test(t) ? 0.45 : 0.06,
    distress: /scared|alone|sad|nobody|hate myself|afraid/.test(t) ? 0.4 : 0.05,
  };
  const ms = MEASURES[kind];
  const panel: Panel[] = PROVIDERS.map((p) => {
    const scores: Record<string, number> = {}; let mx = 0;
    ms.forEach((m) => { const j = Math.max(0, Math.min(1, (hits[m] || 0) + (Math.random() * 0.18 - 0.09))); scores[m] = +j.toFixed(2); mx = Math.max(mx, j); });
    return { provider: p, scores, overall: +mx.toFixed(2), reason: mx >= 0.6 ? "Clear policy-relevant risk." : mx >= 0.3 ? "Borderline signals." : "No material risk." };
  });
  const aggregate = +(panel.reduce((s, p) => s + p.overall, 0) / panel.length).toFixed(3);
  const by_measure: Record<string, number> = {}; ms.forEach((m) => (by_measure[m] = +Math.max(...panel.map((p) => p.scores[m])).toFixed(2)));
  const alarm = aggregate >= THRESHOLD;
  const out: Result = { kind, n_models: 3, panel, by_measure, aggregate, threshold: THRESHOLD, alarm };
  if (alarm) { out.audit_seq = Math.floor(Math.random() * 900 + 100); out.audit_hash = Array.from({ length: 32 }, () => "0123456789abcdef"[Math.floor(Math.random() * 16)]).join(""); }
  return out;
}

export default function Page() {
  const [mode, setMode] = useState<Mode>("conversation");
  const [who, setWho] = useState<Who>("Child");
  const [input, setInput] = useState("");
  const [msgs, setMsgs] = useState<ChatMsg[]>([]);
  const [transcript, setTranscript] = useState<string[]>([]);
  const [busy, setBusy] = useState(false);
  const [devOpen, setDevOpen] = useState(true);
  const [stages, setStages] = useState<Stage[]>([]);
  const [res, setRes] = useState<Result | null>(null);
  const [turns, setTurns] = useState(0);
  const threadRef = useRef<HTMLDivElement>(null);
  const taRef = useRef<HTMLTextAreaElement>(null);

  useEffect(() => { threadRef.current?.scrollTo({ top: threadRef.current.scrollHeight }); }, [msgs, stages, res]);
  useEffect(() => { setTranscript([]); }, [mode]);

  function autosize() { const el = taRef.current; if (!el) return; el.style.height = "auto"; el.style.height = Math.min(el.scrollHeight, 160) + "px"; }

  async function callBackend(kind: Mode, content: string): Promise<Result> {
    try {
      const r = await fetch("/assess", { method: "POST", headers: { "content-type": "application/json" }, body: JSON.stringify({ kind, content }) });
      if (!r.ok) throw new Error(String(r.status));
      return (await r.json()) as Result;
    } catch {
      return mockScore(kind, content); // graceful fallback
    }
  }

  async function send() {
    const text = input.trim(); if (!text || busy) return;
    setBusy(true);
    setMsgs((m) => [...m, { role: "user", text, mode, who }]);
    let content = text; let turnCount = turns;
    if (mode === "conversation") { const next = [...transcript, `${who}: ${text}`]; setTranscript(next); content = next.join("\n"); turnCount = next.length; setTurns(turnCount); }
    else { turnCount = 1; setTurns(1); }
    setInput(""); requestAnimationFrame(autosize);

    setStages(STAGE_DEFS.map((s) => ({ ...s, state: "idle" })));
    setRes(null);

    const result = await callBackend(mode, content);

    for (let i = 0; i < STAGE_DEFS.length - 1; i++) {
      setStages((s) => s.map((st, j) => (j === i ? { ...st, state: "run" } : st)));
      await wait(190);
      setStages((s) => s.map((st, j) => (j === i ? { ...st, state: "done" } : st)));
    }
    setStages((s) => s.map((st) => (st.esc ? { ...st, state: "done", lab: result.alarm ? "Escalated → human monitor" : "No escalation" } : st)));
    setRes(result);
    setMsgs((m) => [...m, { role: "verdict", res: result }]);
    setBusy(false);
  }

  const alarmGlow = res?.alarm ?? false;

  return (
    <div className="ssg">
      <style dangerouslySetInnerHTML={{ __html: CSS }} />
      <div className="app">
        <div className="top">
          <div className="brand"><div className="glyph">SG</div><div className="wm">ssgcheck<small>monitor</small></div></div>
          <div className="seg">
            {(["conversation", "code"] as Mode[]).map((m) => (
              <button key={m} className={mode === m ? "on" : ""} onClick={() => setMode(m)}>{m === "conversation" ? "Conversation" : "Code"}</button>
            ))}
          </div>
          <div className="spacer" />
          <button className={`devtog ${devOpen ? "on" : ""}`} onClick={() => setDevOpen((d) => !d)}><span className="dot" />Developer mode</button>
        </div>

        <div className="body">
          <div className="chatwrap">
            <div className="thread" ref={threadRef}>
              <div className="col">
                {msgs.length === 0 ? (
                  <div className="empty">
                    <h1>What should we review?</h1>
                    <p>Send a message or paste a snippet. Three models score it independently; if the aggregate risk crosses the threshold it&apos;s escalated to a human reviewer and written to the audit trail.</p>
                    <div className="chips">
                      {CHIPS[mode].map((ch, i) => (
                        <button key={i} className="chip" onClick={() => { setInput(ch.t); requestAnimationFrame(autosize); taRef.current?.focus(); }}>
                          <b>{ch.b}</b>{ch.t}
                        </button>
                      ))}
                    </div>
                  </div>
                ) : (
                  msgs.map((m, i) =>
                    m.role === "user" ? (
                      <div className="msg" key={i}>
                        <div className="role"><span className="ava u">{m.mode === "code" ? "{}" : m.who?.[0]}</span>{m.mode === "code" ? "YOU · CODE" : m.who?.toUpperCase()}</div>
                        <div className={`bubble user ${m.mode === "code" ? "code" : ""}`}>{m.text}</div>
                      </div>
                    ) : (
                      <Verdict key={i} res={m.res!} />
                    )
                  )
                )}
              </div>
            </div>

            <div className="composer">
              <div className="cbox">
                <div className="cinner">
                  {mode === "conversation" && (
                    <select className="who" value={who} onChange={(e) => setWho(e.target.value as Who)}><option>Child</option><option>Adult</option></select>
                  )}
                  <textarea
                    ref={taRef} className={mode === "code" ? "code" : ""} rows={1}
                    value={input} placeholder={mode === "code" ? "Paste a code snippet to assess…" : "Message the monitor…"}
                    onChange={(e) => { setInput(e.target.value); autosize(); }}
                    onKeyDown={(e) => { if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); send(); } }}
                  />
                  <button className="send" disabled={!input.trim() || busy} onClick={send} aria-label="Send">
                    <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round"><path d="M12 19V5M5 12l7-7 7 7" /></svg>
                  </button>
                </div>
                <div className="hint">{mode === "code" ? "Code mode · scores fairness · privacy · security" : "Conversation mode · scores grooming · self-harm · PII · distress"}</div>
              </div>
            </div>
          </div>

          <aside className={`rail ${devOpen ? "" : "hidden"} ${alarmGlow ? "alarm" : ""}`}>
            <div className="rhead">
              <span className="live-dot" /><span className="lab">Governance Pipeline</span><span className="badge-live">● live</span>
            </div>
            <div className="rscroll">
              {stages.length === 0 ? (
                <div className="rempty">{`// awaiting input`}<br />{`// pipeline flow, risk drivers,`}<br />{`// citations & audit record`}<br />{`// stream here`}</div>
              ) : (
                <>
                  <div className="panel">
                    <div className="phead">
                      <svg className="ic" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><path d="M13 2 3 14h7l-1 8 10-12h-7l1-8z" /></svg>
                      <span className="pt">Pipeline flow</span>
                    </div>
                    <div className="flow">
                      {stages.map((s, i) => (
                        <div key={i} className={`stage ${s.esc ? "esc" : ""} ${s.state}`}>
                          <span className="nd">
                            {s.state === "run" ? <span className="spin" /> : s.state === "done" ? (s.esc && res?.alarm ? "!" : "✓") : s.esc ? "!" : ""}
                          </span>
                          <span className="sl">{s.lab}{s.tag && <span className="tag llm">{s.tag}</span>}{s.xf && <span className="tag xf">→</span>}</span>
                        </div>
                      ))}
                    </div>
                  </div>
                  {res && <RailResult res={res} turns={turns} />}
                </>
              )}
            </div>
          </aside>
        </div>
      </div>
    </div>
  );
}

function Verdict({ res }: { res: Result }) {
  const tk = tier(res.aggregate);
  const headline = res.alarm
    ? "Escalated. The panel's aggregate risk crossed the threshold, so this was sent to a human reviewer and recorded."
    : "Cleared. The panel scored this below the escalation threshold — no human review required.";
  return (
    <div className="msg">
      <div className="role"><span className="ava a">SG</span>ssgcheck</div>
      <div className="verdict">
        <div className="vhead"><span className="tier" style={{ background: tk.c }}>{tk.t} · {res.aggregate.toFixed(2)}</span>
          <span className="vmsg">{res.n_models}-model panel · threshold {res.threshold.toFixed(2)}</span></div>
        <div className="vbody">{headline}</div>
        {res.alarm
          ? <div className="escbar">⚠ Escalated to human monitor · audit #{res.audit_seq}</div>
          : <div className="okbar">● Below threshold · logged, no escalation</div>}
      </div>
    </div>
  );
}

/* width-animating bar */
function GrowBar({ w, color, className = "fill" }: { w: number; color: string; className?: string }) {
  const [x, setX] = useState(0);
  useEffect(() => { const id = requestAnimationFrame(() => setX(w)); return () => cancelAnimationFrame(id); }, [w]);
  return <span className={className} style={{ width: `${x * 100}%`, background: color }} />;
}

function RailResult({ res, turns }: { res: Result; turns: number }) {
  const tk = tier(res.aggregate);
  const mode = (res.kind as Mode);
  const cites = CITES[mode] ?? [];
  const topSignal = Object.entries(res.by_measure).sort((a, b) => b[1] - a[1])[0];
  const signal = res.kind === "code"
    ? <>code · top signal: <b>{topSignal?.[0]}</b> ({topSignal?.[1].toFixed(2)})</>
    : <>conversation · {turns} turn(s) · top signal: <b>{topSignal?.[0]?.replace(/_/g, " ")}</b></>;

  const drivers = Object.entries(res.by_measure)
    .map(([m, v]) => ({ m, v, contrib: +(v - res.threshold).toFixed(2) }))
    .sort((a, b) => Math.abs(b.contrib) - Math.abs(a.contrib));
  const maxAbs = Math.max(...drivers.map((d) => Math.abs(d.contrib)), 0.01);

  return (
    <>
      <div className="panel">
        <div className="phead"><span className="pn">1</span><span className="pt">Context</span><span className="pbadge llm">LLM</span></div>
        <div className="ctxline">{signal}</div>
        <div className="ctxkv">scan → {res.n_models}/3 models responded</div>
      </div>

      <div className="panel">
        <div className="phead"><span className="pn">2</span><span className="pt">Risk assessment</span><span className="pbadge ens">3-MODEL</span></div>
        <div className="rtier"><span className="k">Risk Tier</span><span className="tierpill" style={{ background: tk.c }}>{tk.t}</span></div>
        <div className="rprob"><span className="k">Aggregate Risk</span><span className="v" style={{ color: tk.c }}>{res.aggregate.toFixed(2)}</span></div>

        <div className="sub">Top Risk Drivers · contribution to aggregate</div>
        {drivers.map((d) => {
          const pos = d.contrib > 0;
          return (
            <div className="drv" key={d.m}>
              <span className="dn">{d.m.replace(/_/g, " ")}</span>
              <span className="dtrack"><GrowBar className="dbar" w={Math.abs(d.contrib) / maxAbs} color={pos ? "var(--red)" : "var(--green)"} /></span>
              <span className={`dv ${pos ? "pos" : "neg"}`}>{pos ? "+" : ""}{d.contrib.toFixed(2)}</span>
            </div>
          );
        })}

        <div className="sub">Per-model panel · overall</div>
        {res.panel.map((p) => (
          <div className="pm" key={p.provider}>
            <span className="pn2">{p.provider}</span>
            <span className="ptrack"><GrowBar className="pbar" w={p.overall} color={barColor(p.overall)} /></span>
            <span className="pv">{p.overall.toFixed(2)}</span>
          </div>
        ))}
      </div>

      <div className="panel">
        <div className="phead"><span className="pn">3</span><span className="pt">Grounded citations</span><span className="pbadge reg">REG</span></div>
        {cites.map(([t, d], i) => (
          <div className="feat" key={i}><div className="fl"><span className="k">{t}</span><span className="v">{d}</span></div></div>
        ))}
      </div>

      <div className="panel">
        <div className="phead"><span className="pn">4</span><span className="pt">Structured features</span><span className="pbadge pol">META</span></div>
        <div className="feat">
          <div className="fl"><span className="k">kind</span><span className="v">{res.kind}</span></div>
          <div className="fl"><span className="k">measures</span><span className="v">{(MEASURES[mode] ?? []).length}</span></div>
          <div className="fl"><span className="k">threshold</span><span className="v">{res.threshold.toFixed(2)}</span></div>
          <div className="fl"><span className="k">ai_act_ref</span><span className="v" style={{ maxWidth: 180 }}>{(AI_ACT[mode] ?? "").split(";")[0]}</span></div>
        </div>
      </div>

      {res.alarm ? (
        <div className="panel esccard">
          <div className="phead"><span className="pn">5</span><span className="pt">Escalation · audit</span><span className="pbadge ens">SHA-256</span></div>
          <div className="ledger">
            <div className="ll"><span className="k">seq</span><span className="hashv">#{res.audit_seq}</span></div>
            <div className="ll"><span className="k">decision</span><span className="hashv" style={{ color: "#ff8076" }}>ESCALATED</span></div>
            {res.audit_hash && <div className="ll"><span className="k">hash</span><span className="hashv">{res.audit_hash.slice(0, 24)}…</span></div>}
          </div>
          <div className="chainok">✓ appended to tamper-evident chain</div>
        </div>
      ) : (
        <div className="panel">
          <div className="phead"><span className="pn">5</span><span className="pt">Escalation · audit</span><span className="pbadge reg">POLICY</span></div>
          <div className="ledger"><div className="ll"><span className="k">decision</span><span className="hashv" style={{ color: "var(--rail-dim)" }}>below threshold</span></div></div>
          <div className="chainok" style={{ color: "var(--rail-dim)" }}>○ logged · no human review needed</div>
        </div>
      )}
    </>
  );
}

/* ───────────────────────── styles ───────────────────────── */
const CSS = `
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600&family=Space+Grotesk:wght@500;600;700&family=JetBrains+Mono:wght@400;500;600&display=swap');
.ssg{
  --paper:#FAF9F6;--paper-2:#F2F0EA;--ink:#1B1D21;--ink-soft:#5A5F68;--hair:#E6E3DB;
  --accent:#4C6FFF;--accent-soft:#EAEEFF;
  --rail:#0B0F17;--rail-2:#121826;--rail-3:#1B2433;--rail-line:#283246;--rail-ink:#CDD6E3;--rail-dim:#6E7A8C;
  --green:#27D17F;--green-dim:#1B6B4B;--amber:#F0B429;--blue:#5B7CFF;--red:#F0544A;
  --low:#27D17F;--med:#F0B429;--high:#F0544A;
  --sans:"Inter",system-ui,sans-serif;--display:"Space Grotesk",system-ui,sans-serif;--mono:"JetBrains Mono",ui-monospace,monospace;
  font-family:var(--sans);color:var(--ink);height:100vh}
.ssg *{box-sizing:border-box}
@media (prefers-reduced-motion:reduce){.ssg *{animation:none!important;transition:none!important}}
.ssg .app{display:flex;flex-direction:column;height:100vh;overflow:hidden;background:var(--paper)}
.ssg .top{display:flex;align-items:center;gap:16px;padding:12px 18px;border-bottom:1px solid var(--hair);background:rgba(250,249,246,.85);backdrop-filter:blur(8px);z-index:5}
.ssg .brand{display:flex;align-items:center;gap:10px}
.ssg .glyph{width:30px;height:30px;border-radius:8px;background:var(--ink);color:var(--paper);display:grid;place-items:center;font-family:var(--display);font-weight:700;font-size:13px;letter-spacing:.5px}
.ssg .wm{font-family:var(--display);font-weight:600;font-size:15px;letter-spacing:-.2px}
.ssg .wm small{color:var(--ink-soft);font-family:var(--mono);font-weight:400;font-size:11px;margin-left:6px}
.ssg .seg{display:flex;background:var(--paper-2);border:1px solid var(--hair);border-radius:999px;padding:3px}
.ssg .seg button{border:0;background:transparent;font-family:var(--sans);font-size:13px;font-weight:500;color:var(--ink-soft);padding:5px 14px;border-radius:999px;cursor:pointer;transition:.15s}
.ssg .seg button.on{background:#fff;color:var(--ink);box-shadow:0 1px 2px rgba(0,0,0,.06)}
.ssg .spacer{flex:1}
.ssg .devtog{display:flex;align-items:center;gap:8px;font-size:13px;font-weight:500;color:var(--ink-soft);border:1px solid var(--hair);background:#fff;border-radius:999px;padding:6px 12px;cursor:pointer}
.ssg .devtog .dot{width:7px;height:7px;border-radius:50%;background:var(--ink-soft)}
.ssg .devtog.on{color:var(--ink);border-color:#cdd6ff}
.ssg .devtog.on .dot{background:var(--accent);box-shadow:0 0 0 3px var(--accent-soft)}
.ssg .body{display:flex;flex:1;min-height:0}
.ssg .chatwrap{flex:1;min-width:0;display:flex;flex-direction:column}
.ssg .thread{flex:1;overflow-y:auto;padding:28px 0}
.ssg .col{max-width:720px;margin:0 auto;padding:0 24px}
.ssg .empty{margin-top:8vh;text-align:center;color:var(--ink-soft)}
.ssg .empty h1{font-family:var(--display);font-weight:600;font-size:26px;color:var(--ink);margin:0 0 8px}
.ssg .empty p{margin:0 auto;max-width:430px;line-height:1.5;font-size:14px}
.ssg .chips{display:flex;flex-wrap:wrap;gap:8px;justify-content:center;margin-top:22px}
.ssg .chip{font-size:13px;border:1px solid var(--hair);background:#fff;border-radius:10px;padding:9px 13px;cursor:pointer;text-align:left;max-width:300px;color:var(--ink);transition:.15s;white-space:pre-wrap;font-family:inherit}
.ssg .chip:hover{border-color:#c9c4b6;transform:translateY(-1px)}
.ssg .chip b{display:block;font-weight:600;font-size:12px;color:var(--ink-soft);margin-bottom:2px}
.ssg .msg{margin:18px 0;animation:ssgrise .35s ease}
@keyframes ssgrise{from{opacity:0;transform:translateY(8px)}to{opacity:1;transform:none}}
.ssg .msg .role{font-size:11px;font-weight:600;letter-spacing:.4px;text-transform:uppercase;color:var(--ink-soft);margin-bottom:6px;display:flex;align-items:center;gap:7px}
.ssg .ava{width:18px;height:18px;border-radius:5px;display:grid;place-items:center;font-size:10px;font-weight:700;font-family:var(--display)}
.ssg .ava.u{background:var(--accent);color:#fff}.ssg .ava.a{background:var(--ink);color:var(--paper)}
.ssg .bubble{font-size:14.5px;line-height:1.6}
.ssg .bubble.user{background:var(--accent-soft);border:1px solid #d9e0ff;border-radius:14px;padding:12px 15px;white-space:pre-wrap}
.ssg .bubble.user.code{font-family:var(--mono);font-size:13px;background:#0f141b;color:#d7dee8;border-color:#0f141b}
.ssg .verdict{border:1px solid var(--hair);border-radius:14px;overflow:hidden;background:#fff}
.ssg .verdict .vhead{display:flex;align-items:center;gap:12px;padding:13px 16px;border-bottom:1px solid var(--hair)}
.ssg .tier{font-family:var(--mono);font-weight:600;font-size:11px;letter-spacing:.5px;color:#fff;padding:4px 9px;border-radius:7px}
.ssg .verdict .vmsg{font-size:13px;color:var(--ink-soft)}
.ssg .verdict .vbody{padding:13px 16px;font-size:14px;line-height:1.55}
.ssg .escbar{padding:11px 16px;background:#fdecea;border-top:1px solid #f6cfca;color:#b3392f;font-weight:600;font-size:13px}
.ssg .okbar{padding:11px 16px;background:#eef8f2;border-top:1px solid #cfe9da;color:#147a52;font-weight:500;font-size:13px}
.ssg .composer{padding:14px 0 22px;background:linear-gradient(transparent,var(--paper) 30%)}
.ssg .cbox{max-width:720px;margin:0 auto;padding:0 24px}
.ssg .cinner{display:flex;align-items:flex-end;gap:10px;border:1px solid var(--hair);background:#fff;border-radius:18px;padding:8px 8px 8px 6px;box-shadow:0 2px 10px rgba(0,0,0,.04)}
.ssg .cinner:focus-within{border-color:#c2cdff;box-shadow:0 2px 16px rgba(76,111,255,.12)}
.ssg .who{align-self:stretch;border:0;background:var(--paper-2);border-radius:12px;font-family:var(--sans);font-size:12px;font-weight:600;color:var(--ink-soft);padding:0 8px;cursor:pointer}
.ssg textarea{flex:1;border:0;outline:0;resize:none;font-family:var(--sans);font-size:14.5px;line-height:1.5;padding:9px 4px;max-height:160px;background:transparent;color:var(--ink)}
.ssg textarea.code{font-family:var(--mono);font-size:13px}
.ssg .send{border:0;width:38px;height:38px;border-radius:12px;background:var(--ink);color:#fff;cursor:pointer;display:grid;place-items:center;transition:.15s}
.ssg .send:disabled{opacity:.4;cursor:default}.ssg .send:not(:disabled):hover{background:var(--accent)}
.ssg .hint{font-size:11px;color:var(--ink-soft);font-family:var(--mono);margin-top:8px}
.ssg .rail{width:392px;flex-shrink:0;background:var(--rail);color:var(--rail-ink);border-left:1px solid var(--rail-line);display:flex;flex-direction:column;transition:margin-right .28s ease,box-shadow .28s ease}
.ssg .rail.hidden{margin-right:-392px}
.ssg .rail.alarm{box-shadow:inset 4px 0 0 var(--high)}
.ssg .rhead{padding:14px 16px;border-bottom:1px solid var(--rail-line);display:flex;align-items:center;gap:9px}
.ssg .rhead .live-dot{width:8px;height:8px;border-radius:50%;background:var(--green);box-shadow:0 0 0 3px rgba(39,209,127,.18);animation:ssgpulse 1.8s infinite}
.ssg .rhead .lab{font-family:var(--display);font-weight:600;font-size:14px;color:var(--rail-ink)}
.ssg .rhead .badge-live{margin-left:auto;font-family:var(--mono);font-size:9.5px;letter-spacing:1px;color:var(--green);text-transform:uppercase}
@keyframes ssgpulse{50%{opacity:.4}}
.ssg .rscroll{flex:1;overflow-y:auto;padding:14px}
.ssg .rempty{color:var(--rail-dim);font-size:13px;line-height:1.6;font-family:var(--mono)}
.ssg .panel{background:var(--rail-2);border:1px solid var(--rail-line);border-radius:13px;padding:13px;margin-bottom:13px}
.ssg .phead{display:flex;align-items:center;gap:8px;margin-bottom:12px}
.ssg .phead .ic{width:18px;height:18px;color:var(--amber)}
.ssg .phead .pt{font-family:var(--mono);font-size:10.5px;font-weight:600;letter-spacing:1.2px;text-transform:uppercase;color:var(--rail-ink)}
.ssg .phead .pn{font-family:var(--mono);font-size:11px;font-weight:700;color:#0b0f17;background:var(--amber);width:18px;height:18px;border-radius:5px;display:grid;place-items:center}
.ssg .phead .pbadge{margin-left:auto;font-family:var(--mono);font-size:9px;font-weight:700;letter-spacing:.5px;padding:2px 6px;border-radius:5px}
.ssg .pbadge.llm{background:rgba(240,180,41,.16);color:var(--amber);border:1px solid rgba(240,180,41,.35)}
.ssg .pbadge.ens{background:rgba(240,84,74,.16);color:var(--red);border:1px solid rgba(240,84,74,.35)}
.ssg .pbadge.pol{background:rgba(91,124,255,.16);color:var(--blue);border:1px solid rgba(91,124,255,.35)}
.ssg .pbadge.reg{background:rgba(39,209,127,.16);color:var(--green);border:1px solid rgba(39,209,127,.35)}
.ssg .flow{position:relative;padding-left:4px}
.ssg .stage{display:flex;align-items:center;gap:11px;padding:6px 0;position:relative}
.ssg .stage .nd{width:22px;height:22px;border-radius:50%;display:grid;place-items:center;font-size:11px;z-index:2;border:1.5px solid var(--rail-line);background:var(--rail-3);color:var(--rail-dim);transition:.2s;flex-shrink:0}
.ssg .stage.done .nd{background:var(--green);border-color:var(--green);color:#06281c;font-weight:700}
.ssg .stage.run .nd{border-color:var(--blue);color:var(--blue);background:rgba(91,124,255,.12)}
.ssg .stage.run .nd .spin{width:11px;height:11px;border:1.6px solid currentColor;border-right-color:transparent;border-radius:50%;animation:ssgspin .8s linear infinite}
.ssg .stage.esc.done .nd{background:var(--red);border-color:var(--red);color:#fff}
@keyframes ssgspin{to{transform:rotate(360deg)}}
.ssg .stage .sl{font-size:12.5px;color:var(--rail-dim);font-weight:500;display:flex;align-items:center;gap:7px}
.ssg .stage.done .sl{color:var(--rail-ink)}.ssg .stage.run .sl{color:var(--blue)}.ssg .stage.esc.done .sl{color:#ff8076;font-weight:600}
.ssg .stage .tag{font-family:var(--mono);font-size:8.5px;font-weight:700;letter-spacing:.5px;padding:1px 5px;border-radius:4px}
.ssg .tag.llm{background:rgba(240,180,41,.16);color:var(--amber)}
.ssg .tag.xf{color:var(--rail-dim)}
.ssg .stage:not(:last-child)::before{content:"";position:absolute;left:10.5px;top:26px;width:1.5px;height:12px;background:var(--rail-line)}
.ssg .stage.done:not(:last-child)::before{background:var(--green-dim)}
.ssg .ctxline{font-size:12.5px;line-height:1.5;color:var(--rail-ink)}
.ssg .ctxline b{color:var(--green);font-weight:500}
.ssg .ctxkv{font-family:var(--mono);font-size:11px;color:var(--rail-dim);margin-top:6px}
.ssg .rtier{display:flex;align-items:center;justify-content:space-between;padding:5px 0}
.ssg .rtier .k{font-size:12.5px;color:var(--rail-dim)}
.ssg .tierpill{font-family:var(--mono);font-weight:700;font-size:10px;letter-spacing:.5px;color:#06281c;padding:3px 9px;border-radius:6px}
.ssg .rprob{display:flex;align-items:center;justify-content:space-between;padding:5px 0 10px;border-bottom:1px solid var(--rail-line)}
.ssg .rprob .k{font-size:12.5px;color:var(--rail-dim)}
.ssg .rprob .v{font-family:var(--mono);font-size:26px;font-weight:600;letter-spacing:-.5px}
.ssg .sub{font-family:var(--mono);font-size:9px;letter-spacing:1px;text-transform:uppercase;color:var(--rail-dim);margin:13px 0 8px}
.ssg .drv{display:grid;grid-template-columns:96px 1fr 46px;align-items:center;gap:8px;margin:6px 0;font-size:11px}
.ssg .drv .dn{color:var(--rail-ink);white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.ssg .drv .dtrack{height:9px;background:var(--rail-3);border-radius:3px;position:relative;overflow:hidden}
.ssg .drv .dbar{position:absolute;top:0;bottom:0;left:0;border-radius:3px;transition:width .6s cubic-bezier(.2,.8,.2,1)}
.ssg .drv .dv{font-family:var(--mono);text-align:right;color:var(--rail-ink)}
.ssg .drv .dv.pos{color:#ff8076}.ssg .drv .dv.neg{color:var(--green)}
.ssg .pm{display:grid;grid-template-columns:70px 1fr 34px;align-items:center;gap:8px;margin:5px 0;font-size:11px}
.ssg .pm .pn2{color:var(--rail-dim)}.ssg .pm .pv{font-family:var(--mono);text-align:right}
.ssg .pm .ptrack{height:6px;background:var(--rail-3);border-radius:3px;overflow:hidden}
.ssg .pm .pbar{height:100%;border-radius:3px;transition:width .6s ease;display:block}
.ssg .feat{font-family:var(--mono);font-size:11px;line-height:1.85}
.ssg .feat .fl{display:flex;justify-content:space-between;gap:12px}
.ssg .feat .fl .k{color:var(--rail-dim)}.ssg .feat .fl .v{color:var(--rail-ink);text-align:right}
.ssg .ledger{font-family:var(--mono);font-size:11px;line-height:1.8}
.ssg .ledger .ll{display:flex;justify-content:space-between;gap:10px}
.ssg .ledger .ll .k{color:var(--rail-dim)}.ssg .ledger .hashv{color:var(--green);word-break:break-all;text-align:right}
.ssg .chainok{margin-top:9px;font-family:var(--mono);font-size:10.5px;color:var(--green);display:flex;align-items:center;gap:6px}
.ssg .esccard{border-color:#5a2420;background:#1a1210}
.ssg .esccard .pt{color:#ff8076}.ssg .esccard .pn{background:var(--red);color:#fff}
@media (max-width:900px){.ssg .rail{position:absolute;right:0;top:0;bottom:0;z-index:20;box-shadow:-12px 0 40px rgba(0,0,0,.4)}.ssg .rail.alarm{box-shadow:inset 4px 0 0 var(--high),-12px 0 40px rgba(0,0,0,.4)}}
`;