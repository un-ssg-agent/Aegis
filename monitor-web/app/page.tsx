"use client";
import { useEffect, useState } from "react";

type Panel = { provider: string; scores: Record<string, number>; overall: number; reason: string };
type CatDist = { key: string; label: string; score: number; share: number; count: number };
type MsgLabel = { who: string; text: string; label: string; score: number };
type Result = {
  kind: string;
  n_models: number;
  panel: Panel[];
  by_measure: Record<string, number>;
  aggregate: number;
  threshold: number;
  alarm: boolean;
  errors: string[];
  audit_seq?: number;
  audit_hash?: string;
  distribution?: CatDist[];
  dominant?: string | null;
  messages?: MsgLabel[];
};
type Msg = { who: "Child" | "Adult"; text: string };

const MODELS = ["deepseek", "openai", "gemini"] as const;

// Fixed visual identity per risk category: a color (hue = category) used by the
// distribution chart, the legend dots, and the per-message chips. Fill/length
// encodes severity separately, so color never doubles as a score.
const CAT: Record<string, { label: string; hex: string; dot: string }> = {
  grooming:          { label: "grooming",          hex: "#a855f7", dot: "bg-purple-500" },
  bullying:          { label: "bullying",          hex: "#f97316", dot: "bg-orange-500" },
  suicidal_ideation: { label: "suicidal ideation", hex: "#ef4444", dot: "bg-red-500" },
  self_harm:         { label: "self harm",         hex: "#be123c", dot: "bg-rose-700" },
  pii_exposure:      { label: "PII exposure",      hex: "#3b82f6", dot: "bg-blue-500" },
  distress:          { label: "distress",          hex: "#06b6d4", dot: "bg-cyan-500" },
  fairness:          { label: "fairness",          hex: "#8b5cf6", dot: "bg-violet-500" },
  privacy:           { label: "privacy",           hex: "#3b82f6", dot: "bg-blue-500" },
  security:          { label: "security",          hex: "#ef4444", dot: "bg-red-500" },
};
const catLabel = (k: string) => CAT[k]?.label ?? k.replace(/_/g, " ");
const catHex = (k: string) => CAT[k]?.hex ?? "#64748b";

// Demo data so the sidebar visualization can be reviewed without a live backend.
const MOCK_MSGS: Msg[] = [
  { who: "Adult", text: "hey, are you home alone tonight?" },
  { who: "Child", text: "yeah my parents are out till late" },
  { who: "Adult", text: "cool — don't tell anyone we talk, it's our little secret 😉" },
  { who: "Child", text: "sometimes i feel like no one would even miss me" },
];
const MOCK_RES: Result = {
  kind: "conversation",
  n_models: 3,
  panel: [
    { provider: "deepseek:deepseek-chat", scores: {}, overall: 0.74, reason: "secrecy + isolation probing" },
    { provider: "openai:gpt-4o-mini", scores: {}, overall: 0.69, reason: "grooming pattern, distress signal" },
    { provider: "gemini:1.5-flash", scores: {}, overall: 0.71, reason: "self-worth statement is high risk" },
  ],
  by_measure: { grooming: 0.71, bullying: 0.12, suicidal_ideation: 0.78, self_harm: 0.34, pii_exposure: 0.08, distress: 0.52 },
  aggregate: 0.71,
  threshold: 0.6,
  alarm: true,
  errors: [],
  audit_seq: 7,
  audit_hash: "9f2c41ab7e0d5c83aa1b",
  dominant: "suicidal_ideation",
  distribution: [
    { key: "suicidal_ideation", label: "suicidal ideation", score: 0.78, share: 0.31, count: 1 },
    { key: "grooming", label: "grooming", score: 0.71, share: 0.28, count: 2 },
    { key: "distress", label: "distress", score: 0.52, share: 0.21, count: 0 },
    { key: "self_harm", label: "self harm", score: 0.34, share: 0.13, count: 0 },
    { key: "bullying", label: "bullying", score: 0.12, share: 0.05, count: 0 },
    { key: "pii_exposure", label: "PII exposure", score: 0.08, share: 0.03, count: 0 },
  ],
  messages: [
    { who: "Adult", text: "hey, are you home alone tonight?", label: "grooming", score: 0.55 },
    { who: "Child", text: "yeah my parents are out till late", label: "none", score: 0.1 },
    { who: "Adult", text: "cool — don't tell anyone we talk, it's our little secret 😉", label: "grooming", score: 0.71 },
    { who: "Child", text: "sometimes i feel like no one would even miss me", label: "suicidal_ideation", score: 0.78 },
  ],
};

function tierFor(v: number) {
  if (v >= 0.6) return { t: "HIGH", c: "bg-red-600" };
  if (v >= 0.3) return { t: "MED", c: "bg-amber-500" };
  return { t: "LOW", c: "bg-emerald-600" };
}
function barColor(v: number) {
  return v >= 0.6 ? "bg-red-500" : v >= 0.3 ? "bg-amber-400" : "bg-emerald-500";
}

function Bar({ v }: { v: number }) {
  return (
    <div className="h-1.5 w-full overflow-hidden rounded bg-slate-700">
      <div className={`h-full ${barColor(v)}`} style={{ width: `${Math.round(v * 100)}%` }} />
    </div>
  );
}

function Card({ n, title, badge, children }: { n: number; title: string; badge?: string; children: React.ReactNode }) {
  return (
    <div className="rounded-xl border border-slate-700 bg-slate-800/60 p-3">
      <div className="mb-2 flex items-center gap-2">
        <span className="flex h-5 w-5 items-center justify-center rounded bg-slate-600 text-[11px] font-bold">{n}</span>
        <span className="text-xs font-semibold uppercase tracking-wide text-slate-200">{title}</span>
        {badge && <span className="ml-auto rounded bg-slate-700 px-1.5 py-0.5 text-[10px] text-slate-300">{badge}</span>}
      </div>
      {children}
    </div>
  );
}

function Row({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex justify-between py-0.5 text-sm">
      <span className="text-slate-400">{label}</span>
      <span className="text-slate-100">{value}</span>
    </div>
  );
}

// Per-message label tag shown under a chat bubble.
function CatChip({ label, score }: { label: string; score: number }) {
  if (!label || label === "none") return null;
  return (
    <span
      className="mt-1 inline-flex items-center gap-1 rounded-full px-1.5 py-0.5 text-[10px] font-medium text-white"
      style={{ backgroundColor: catHex(label) }}
    >
      {catLabel(label)} · {score.toFixed(2)}
    </span>
  );
}

// 100%-stacked bar: each category's share of total risk (proportion by severity).
function StackedDist({ dist }: { dist: CatDist[] }) {
  const total = dist.reduce((a, d) => a + d.score, 0) || 1;
  const segs = dist.filter((d) => d.score > 0);
  if (segs.length === 0) return <div className="h-3 w-full rounded bg-slate-700" />;
  return (
    <div className="flex h-3 w-full overflow-hidden rounded">
      {segs.map((d) => (
        <div
          key={d.key}
          title={`${catLabel(d.key)} · ${Math.round((d.score / total) * 100)}%`}
          style={{ width: `${(d.score / total) * 100}%`, backgroundColor: catHex(d.key) }}
        />
      ))}
    </div>
  );
}

// Distribution card: stacked share bar on top, labeled severity bars below.
function DistCard({ dist, dominant }: { dist: CatDist[]; dominant?: string | null }) {
  return (
    <Card n={3} title="RISK DISTRIBUTION" badge="BY CATEGORY">
      <StackedDist dist={dist} />
      <div className="mb-3 mt-1.5 flex items-center justify-between text-[10px] text-slate-400">
        <span>share of total risk</span>
        {dominant && (
          <span className="flex items-center gap-1">
            dominant
            <span className="rounded px-1.5 py-0.5 font-semibold text-white" style={{ backgroundColor: catHex(dominant) }}>
              {catLabel(dominant)}
            </span>
          </span>
        )}
      </div>
      {dist.map((d, i) => (
        <div key={d.key} className="mb-1.5">
          <div className="flex items-center gap-1.5 text-xs">
            <span className={`h-2 w-2 shrink-0 rounded-full ${CAT[d.key]?.dot ?? "bg-slate-500"}`} />
            <span className={i === 0 && d.score > 0 ? "font-semibold text-slate-100" : "text-slate-300"}>{d.label}</span>
            <span className="ml-auto tabular-nums text-slate-200">{d.score.toFixed(2)}</span>
            <span className="w-7 text-right tabular-nums text-slate-500" title="messages labeled this category">·{d.count}</span>
          </div>
          <Bar v={d.score} />
        </div>
      ))}
    </Card>
  );
}

export default function Page() {
  const [mode, setMode] = useState<"conversation" | "code">("conversation");
  const [speaker, setSpeaker] = useState<"Child" | "Adult">("Child");
  const [msgs, setMsgs] = useState<Msg[]>([]);
  const [input, setInput] = useState("");
  const [code, setCode] = useState("");
  const [res, setRes] = useState<Result | null>(null);
  const [loading, setLoading] = useState(false);
  const [showPanel, setShowPanel] = useState(true);

  async function runAssess(kind: string, content: string) {
    if (!content.trim()) return;
    setLoading(true);
    try {
      const r = await fetch("/assess", {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({ kind, content }),
      });
      setRes(await r.json());
    } catch (e) {
      setRes({ kind, n_models: 0, panel: [], by_measure: {}, aggregate: 0, threshold: 0, alarm: false, errors: [String(e)] });
    } finally {
      setLoading(false);
    }
  }

  function loadMock() {
    setMode("conversation");
    setMsgs(MOCK_MSGS);
    setRes(MOCK_RES);
    setShowPanel(true);
  }

  // ?mock=1 auto-loads the demo data (for screenshots / sharing the design).
  useEffect(() => {
    if (new URLSearchParams(window.location.search).get("mock") === "1") loadMock();
  }, []);

  function send() {
    if (!input.trim()) return;
    const next = [...msgs, { who: speaker, text: input.trim() }];
    setMsgs(next);
    setInput("");
    runAssess("conversation", next.map((m) => `${m.who}: ${m.text}`).join("\n"));
  }

  const modelDone = (name: string) => res?.panel.some((p) => p.provider.startsWith(name)) ?? false;

  const pipeline = [
    { k: "input", label: "Input context", done: !!res || msgs.length > 0 },
    ...MODELS.map((m) => ({ k: m, label: `Model: ${m}`, done: modelDone(m) })),
    { k: "agg", label: "Aggregate · threshold", done: !!res },
    { k: "esc", label: res?.alarm ? "Escalated to human monitor" : "Escalation", done: !!res },
  ];

  return (
    <div className="flex h-screen flex-col bg-gray-50 text-gray-900">
      <header className="flex items-center justify-between border-b bg-white px-5 py-3">
        <div className="flex items-center gap-3">
          <div className="flex h-9 w-9 items-center justify-center rounded-lg bg-blue-600 font-bold text-white">SG</div>
          <div>
            <div className="font-semibold leading-tight">SSGCheck Monitor</div>
            <div className="text-xs text-gray-500">3-model safety panel · human-in-the-loop</div>
          </div>
        </div>
        <div className="flex items-center gap-4 text-sm">
          <span className="flex items-center gap-1.5">
            <span className="h-2 w-2 rounded-full bg-emerald-500" />
            Online
          </span>
          <button onClick={loadMock} className="rounded-lg border border-blue-600 px-3 py-1.5 font-medium text-blue-600">
            Mock
          </button>
          <button onClick={() => setShowPanel((s) => !s)} className="rounded-lg bg-blue-600 px-3 py-1.5 font-medium text-white">
            {showPanel ? "Hide Panel" : "Show Panel"}
          </button>
        </div>
      </header>

      <div className="flex min-h-0 flex-1">
        <main className="flex min-w-0 flex-1 flex-col">
          <div className="flex items-center gap-2 border-b bg-white px-5 py-2 text-sm">
            {(["conversation", "code"] as const).map((m) => (
              <button
                key={m}
                onClick={() => setMode(m)}
                className={`rounded-full px-3 py-1 ${mode === m ? "bg-blue-600 text-white" : "bg-gray-100 text-gray-600"}`}
              >
                {m === "conversation" ? "Conversation" : "Code"}
              </button>
            ))}
          </div>

          {mode === "conversation" ? (
            <>
              <div className="flex-1 space-y-4 overflow-y-auto p-6">
                {msgs.length === 0 && (
                  <p className="mt-10 text-center text-sm text-gray-400">
                    Type messages below. Each turn is scored by 3 models; risk builds on the right.
                  </p>
                )}
                {msgs.map((m, i) => (
                  <div key={i} className={`flex ${m.who === "Child" ? "justify-end" : "justify-start"}`}>
                    <div
                      className={`max-w-[70%] rounded-2xl px-4 py-2 text-sm ${
                        m.who === "Child" ? "bg-blue-600 text-white" : "border bg-white"
                      }`}
                    >
                      <div className={`mb-0.5 text-[10px] font-semibold uppercase ${m.who === "Child" ? "text-blue-100" : "text-gray-400"}`}>
                        {m.who}
                      </div>
                      {m.text}
                      {res?.messages?.[i] && (
                        <div className={`flex ${m.who === "Child" ? "justify-end" : "justify-start"}`}>
                          <CatChip label={res.messages[i].label} score={res.messages[i].score} />
                        </div>
                      )}
                    </div>
                  </div>
                ))}
              </div>
              <div className="flex items-center gap-2 border-t bg-white p-4">
                <select
                  value={speaker}
                  onChange={(e) => setSpeaker(e.target.value as Msg["who"])}
                  className="rounded-lg border px-2 py-2 text-sm"
                >
                  <option>Child</option>
                  <option>Adult</option>
                </select>
                <input
                  value={input}
                  onChange={(e) => setInput(e.target.value)}
                  onKeyDown={(e) => e.key === "Enter" && send()}
                  placeholder="Type your message..."
                  className="flex-1 rounded-full border px-4 py-2.5 text-sm outline-none focus:border-blue-500"
                />
                <button
                  onClick={send}
                  disabled={loading}
                  className="rounded-full bg-blue-600 px-5 py-2.5 text-sm font-medium text-white disabled:opacity-50"
                >
                  {loading ? "Scoring…" : "Send"}
                </button>
              </div>
            </>
          ) : (
            <div className="flex flex-1 flex-col p-6">
              <textarea
                value={code}
                onChange={(e) => setCode(e.target.value)}
                placeholder="Paste a code snippet (scored for fairness / privacy / security)…"
                className="flex-1 rounded-lg border p-3 font-mono text-sm outline-none focus:border-blue-500"
              />
              <button
                onClick={() => runAssess("code", code)}
                disabled={loading}
                className="mt-3 self-end rounded-full bg-blue-600 px-6 py-2.5 text-sm font-medium text-white disabled:opacity-50"
              >
                {loading ? "Scoring…" : "Assess"}
              </button>
            </div>
          )}
        </main>

        {showPanel && (
          <aside className="w-[400px] shrink-0 overflow-y-auto bg-slate-900 p-4 text-slate-200">
            <div className="mb-4 space-y-2 rounded-xl border border-slate-700 bg-slate-800/50 p-3">
              {pipeline.map((s) => (
                <div key={s.k} className="flex items-center gap-2 text-sm">
                  <span
                    className={`flex h-5 w-5 items-center justify-center rounded-full text-[11px] ${
                      loading && !s.done ? "bg-blue-500 text-white" : s.done ? "bg-emerald-600 text-white" : "bg-slate-600 text-slate-300"
                    }`}
                  >
                    {s.done ? "✓" : loading ? "…" : "•"}
                  </span>
                  <span className={s.k === "esc" && res?.alarm ? "font-semibold text-red-400" : s.done ? "text-slate-200" : "text-slate-400"}>
                    {s.label}
                  </span>
                </div>
              ))}
            </div>

            {!res ? (
              <p className="px-1 text-sm text-slate-400">Awaiting input… scores appear here.</p>
            ) : (
              <div className="space-y-4">
                <Card n={1} title="INPUT · CONTEXT" badge={res.kind.toUpperCase()}>
                  <Row label="Kind" value={res.kind} />
                  <Row label="Models responded" value={`${res.n_models} / 3`} />
                </Card>

                <Card n={2} title="RISK PANEL · 3 MODELS" badge="ENSEMBLE">
                  <div className="mb-2 flex items-center justify-between text-sm">
                    <span className="text-slate-300">Risk tier</span>
                    <span className={`rounded px-2 py-0.5 text-xs font-bold text-white ${tierFor(res.aggregate).c}`}>{tierFor(res.aggregate).t}</span>
                  </div>
                  <div className="mb-3 flex items-center justify-between">
                    <span className="text-sm text-slate-300">Aggregate</span>
                    <span className="text-lg font-bold">{res.aggregate.toFixed(2)}</span>
                  </div>
                  <div className="mb-1 text-[10px] uppercase tracking-wide text-slate-400">Per model</div>
                  {res.panel.map((p) => (
                    <div key={p.provider} className="mb-1.5">
                      <div className="flex justify-between text-xs">
                        <span className="text-slate-300">{p.provider}</span>
                        <span>{p.overall.toFixed(2)}</span>
                      </div>
                      <Bar v={p.overall} />
                    </div>
                  ))}
                </Card>

                {res.distribution && res.distribution.length > 0 && (
                  <DistCard dist={res.distribution} dominant={res.dominant} />
                )}

                <Card n={4} title="ESCALATION · THRESHOLD" badge="POLICY">
                  <Row label="Threshold" value={res.threshold.toFixed(2)} />
                  <Row label="Aggregate" value={res.aggregate.toFixed(2)} />
                  {res.alarm ? (
                    <div className="mt-2 rounded-lg border border-red-500 bg-red-500/15 px-3 py-2 text-center text-sm font-bold text-red-400">
                      🚨 ESCALATED TO HUMAN MONITOR
                    </div>
                  ) : (
                    <div className="mt-2 rounded-lg border border-emerald-600 bg-emerald-600/10 px-3 py-2 text-center text-sm text-emerald-400">
                      ● below threshold
                    </div>
                  )}
                </Card>

                {res.audit_hash && (
                  <Card n={5} title="AUDIT · HASH CHAIN" badge="SHA-256">
                    <Row label="seq" value={String(res.audit_seq)} />
                    <Row label="hash" value={res.audit_hash.slice(0, 16) + "…"} />
                    <div className="mt-1 text-xs text-emerald-400">appended to tamper-evident trail</div>
                  </Card>
                )}

                {res.errors.length > 0 && <p className="text-xs text-slate-500">unavailable: {res.errors.join(", ")}</p>}
              </div>
            )}
          </aside>
        )}
      </div>
    </div>
  );
}
