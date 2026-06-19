"use client";
import { useState } from "react";

type Panel = { provider: string; scores: Record<string, number>; overall: number; reason: string };
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
};
type Msg = { who: "Child" | "Adult"; text: string };

const MODELS = ["deepseek", "openai", "gemini"] as const;

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
                  <div className="mb-1 mt-3 text-[10px] uppercase tracking-wide text-slate-400">Measures (worst across panel)</div>
                  {Object.entries(res.by_measure).map(([m, v]) => (
                    <div key={m} className="mb-1.5">
                      <div className="flex justify-between text-xs">
                        <span className="text-slate-300">{m}</span>
                        <span>{v.toFixed(2)}</span>
                      </div>
                      <Bar v={v} />
                    </div>
                  ))}
                </Card>

                <Card n={3} title="ESCALATION · THRESHOLD" badge="POLICY">
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
                  <Card n={4} title="AUDIT · HASH CHAIN" badge="SHA-256">
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
