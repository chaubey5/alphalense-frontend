import { useEffect, useMemo, useRef, useState } from "react";
import { useParams, Link } from "react-router-dom";
import { motion, AnimatePresence } from "framer-motion";
import {
  ArrowLeft, TrendingUp, TrendingDown, Activity, Loader2,
  CheckCircle2, Circle, ExternalLink, AlertTriangle, Brain, Building2, Scale,
  Globe2, ThumbsUp, ThumbsDown, Gavel,
} from "lucide-react";
import { LineChart, Line, ResponsiveContainer, XAxis, YAxis, Tooltip, BarChart, Bar, ReferenceLine } from "recharts";
import GlassCard from "@/components/GlassCard";
import SearchBar from "@/components/SearchBar";

const API = `${process.env.REACT_APP_BACKEND_URL}/api`;

const AGENT_META = {
  research:  { label: "Research",  icon: Building2, color: "var(--accent-3)" },
  financial: { label: "Financial", icon: Activity,  color: "var(--accent)" },
  valuation: { label: "Valuation", icon: Scale,     color: "var(--gold)" },
  macro:     { label: "Macro",     icon: Globe2,    color: "#b39ddb" },
  bull:      { label: "Bull",      icon: ThumbsUp,  color: "var(--accent)" },
  bear:      { label: "Bear",      icon: ThumbsDown,color: "var(--danger)" },
  moderator: { label: "Moderator", icon: Gavel,     color: "var(--accent-2)" },
};
const AGENT_ORDER = ["research", "financial", "valuation", "macro", "bull", "bear", "moderator"];

function fmtNum(n, opts = {}) {
  if (n === null || n === undefined || isNaN(n)) return "—";
  const v = Number(n);
  const { currency = false, pct = false, compact = false, digits = 2 } = opts;
  if (pct) return `${(v * (Math.abs(v) < 1 ? 100 : 1)).toFixed(digits)}%`;
  if (compact) {
    const abs = Math.abs(v);
    if (abs >= 1e12) return `${currency ? "$" : ""}${(v / 1e12).toFixed(2)}T`;
    if (abs >= 1e9)  return `${currency ? "$" : ""}${(v / 1e9).toFixed(2)}B`;
    if (abs >= 1e6)  return `${currency ? "$" : ""}${(v / 1e6).toFixed(2)}M`;
    if (abs >= 1e3)  return `${currency ? "$" : ""}${(v / 1e3).toFixed(2)}K`;
  }
  return `${currency ? "$" : ""}${v.toFixed(digits)}`;
}

function verdictClass(v) {
  if (v === "INVEST") return "verdict-invest";
  if (v === "HOLD") return "verdict-hold";
  if (v === "PASS") return "verdict-pass";
  return "verdict-hold";
}

export default function Dashboard() {
  const { ticker } = useParams();
  const [marketData, setMarketData] = useState(null);
  const [agents, setAgents] = useState({});      // { research: {...}, ... }
  const [steps, setSteps] = useState([]);        // running log
  const [status, setStatus] = useState({});      // { research: "running" | "done" }
  const [error, setError] = useState(null);
  const [done, setDone] = useState(false);
  const esRef = useRef(null);

  useEffect(() => {
    if (!ticker) return;
    // reset
    setMarketData(null); setAgents({}); setSteps([]); setStatus({});
    setError(null); setDone(false);

    const url = `${API}/research/start?ticker=${encodeURIComponent(ticker)}`;
    const es = new EventSource(url);
    esRef.current = es;

    const push = (text) => setSteps((s) => [...s, { t: Date.now(), text }]);

    es.addEventListener("init",        () => push(`Pipeline initialised for ${ticker}.`));
    es.addEventListener("step",        (e) => push(JSON.parse(e.data).label));
    es.addEventListener("market_data", (e) => { setMarketData(JSON.parse(e.data)); push("Market data fetched."); });
    es.addEventListener("agent_start", (e) => {
      const d = JSON.parse(e.data);
      setStatus((s) => ({ ...s, [d.agent]: "running" }));
      push(`${d.label || d.agent} started.`);
    });
    es.addEventListener("agent_done", (e) => {
      const d = JSON.parse(e.data);
      setStatus((s) => ({ ...s, [d.agent]: "done" }));
      setAgents((a) => ({ ...a, [d.agent]: d.data || {} }));
      push(`${(AGENT_META[d.agent]?.label) || d.agent} agent finished.`);
    });
    es.addEventListener("error", (e) => {
      try { const d = JSON.parse(e.data); setError(d.message); } catch {}
    });
    es.addEventListener("complete", () => { setDone(true); push("Report complete."); es.close(); });
    es.onerror = () => { /* server may close after complete */ };

    return () => es.close();
  }, [ticker]);

  const moderator = agents.moderator || {};
  const quote = marketData?.quote;
  const profile = marketData?.profile;
  const ratios = marketData?.ratios;
  const peers = marketData?.peers || [];
  const news = marketData?.news || [];
  const history = marketData?.history || [];
  const analyst = marketData?.analyst;
  const financials = marketData?.financials || {};

  const incomeRows = (financials.income || []).slice().reverse();
  const revChart = incomeRows.map((r) => ({
    year: (r.date || "").slice(0, 4),
    revenue: r.revenue || 0,
    netIncome: r.netIncome || 0,
  }));

  const fairValue = agents.valuation || {};

  return (
    <div className="min-h-screen grid-bg pb-20" data-testid="research-dashboard">
      <header className="px-6 md:px-12 py-5 flex items-center gap-6 border-b border-[var(--border)] sticky top-0 z-30 backdrop-blur-xl bg-[rgba(6,7,11,0.6)]">
        <Link to="/" data-testid="back-home-btn" className="flex items-center gap-2 text-sm text-[var(--text-dim)] hover:text-[var(--text)]">
          <ArrowLeft className="w-4 h-4" /> AlphaLens
        </Link>
        <div className="flex-1 max-w-2xl mx-auto"><SearchBar size="sm" /></div>
        <span className="label-eyebrow hidden md:block">
          {done ? "report complete" : "live · streaming"}
        </span>
      </header>

      <div className="max-w-7xl mx-auto px-6 md:px-12 pt-10 space-y-6">
        {/* Header */}
        <div className="flex items-start justify-between flex-wrap gap-6">
          <div>
            <div className="label-eyebrow mb-2">// equity research</div>
            <div className="flex items-baseline gap-4 flex-wrap">
              <h1 className="h-display text-5xl md:text-7xl">{profile?.name || ticker}</h1>
              <span className="font-mono text-2xl text-[var(--text-dim)]">{ticker?.toUpperCase()}</span>
              {profile?.exchange && (
                <span className="label-eyebrow">{profile.exchange} · {profile?.sector}</span>
              )}
            </div>
          </div>
          <div className="flex items-baseline gap-5">
            <div className="text-right">
              <div className="h-display text-5xl">
                {quote ? fmtNum(quote.price, { digits: 2 }) : <span className="shimmer inline-block w-32 h-10 rounded" />}
              </div>
              {quote && (
                <div className={`mt-1 font-mono text-sm flex items-center justify-end gap-2 ${quote.change >= 0 ? "text-[var(--accent)]" : "text-[var(--danger)]"}`}>
                  {quote.change >= 0 ? <TrendingUp className="w-4 h-4" /> : <TrendingDown className="w-4 h-4" />}
                  {fmtNum(quote.change)} ({fmtNum(quote.changesPercentage)}%)
                </div>
              )}
            </div>
          </div>
        </div>

        {error && (
          <GlassCard glow="glow-orange">
            <div className="flex items-center gap-3 text-[var(--danger)]">
              <AlertTriangle className="w-5 h-5" /> {error}
            </div>
          </GlassCard>
        )}

        {/* Status pipeline strip */}
        <GlassCard testId="agent-pipeline" eyebrow="// agent pipeline" title="Live reasoning">
          <div className="grid grid-cols-2 md:grid-cols-7 gap-3">
            {AGENT_ORDER.map((a) => {
              const m = AGENT_META[a];
              const st = status[a];
              const Icon = m.icon;
              return (
                <div key={a} data-testid={`agent-status-${a}`} className="glass-strong glass p-3 rounded-xl flex items-center gap-3">
                  <div className="w-9 h-9 rounded-lg flex items-center justify-center" style={{ background: `${m.color}1A`, color: m.color }}>
                    <Icon className="w-4 h-4" />
                  </div>
                  <div className="flex-1 min-w-0">
                    <div className="text-sm">{m.label}</div>
                    <div className="text-[10px] font-mono uppercase tracking-widest text-[var(--text-faint)]">
                      {st === "done" ? "complete" : st === "running" ? "thinking…" : "queued"}
                    </div>
                  </div>
                  {st === "done" ? <CheckCircle2 className="w-4 h-4 text-[var(--accent)]" /> :
                   st === "running" ? <Loader2 className="w-4 h-4 animate-spin text-[var(--accent-3)]" /> :
                   <Circle className="w-4 h-4 text-[var(--text-faint)]" />}
                </div>
              );
            })}
          </div>
        </GlassCard>

        {/* Recommendation hero */}
        <AnimatePresence>
          {moderator?.recommendation && (
            <motion.div
              initial={{ opacity: 0, y: 16 }} animate={{ opacity: 1, y: 0 }}
              transition={{ duration: 0.6 }}
            >
              <GlassCard glow={moderator.recommendation === "INVEST" ? "glow-mint" : moderator.recommendation === "PASS" ? "glow-orange" : ""} testId="recommendation-card">
                <div className="grid lg:grid-cols-3 gap-8 items-center">
                  <div className="lg:col-span-2">
                    <div className="label-eyebrow mb-3">// final verdict</div>
                    <div className="flex items-center gap-4 mb-5">
                      <span className={`px-5 py-2 rounded-full text-sm font-mono tracking-widest ${verdictClass(moderator.recommendation)}`} data-testid="verdict-badge">
                        {moderator.recommendation}
                      </span>
                      <div className="font-mono text-sm text-[var(--text-dim)]">
                        confidence: <span className="text-[var(--text)]">{moderator.confidence_score ?? "—"}/100</span>
                      </div>
                      <div className="font-mono text-sm text-[var(--text-dim)]">
                        horizon: <span className="text-[var(--text)]">{moderator.time_horizon || "—"}</span>
                      </div>
                    </div>
                    <p className="h-display text-2xl md:text-3xl leading-tight" data-testid="exec-summary">
                      {moderator.executive_summary || "—"}
                    </p>
                    <ul className="mt-6 space-y-2">
                      {(moderator.key_reasons || []).map((r, i) => (
                        <li key={i} className="flex gap-3 text-sm text-[var(--text-dim)]">
                          <span className="text-[var(--accent)] font-mono mt-0.5">→</span>{r}
                        </li>
                      ))}
                    </ul>
                  </div>
                  <div className="space-y-4">
                    <Gauge value={moderator.confidence_score || 0} />
                    <div className="grid grid-cols-2 gap-3">
                      <Stat label="Upside" value={`${moderator.expected_upside_pct ?? "—"}%`} good />
                      <Stat label="Downside" value={`${moderator.expected_downside_pct ?? "—"}%`} bad />
                    </div>
                  </div>
                </div>
              </GlassCard>
            </motion.div>
          )}
        </AnimatePresence>

        {/* Overview grid */}
        <div className="grid lg:grid-cols-3 gap-6">
          <GlassCard eyebrow="// company" title="Overview" className="lg:col-span-2" testId="overview-card">
            {profile ? (
              <>
                <p className="text-sm text-[var(--text-dim)] leading-relaxed line-clamp-6">
                  {profile.description || "No description available."}
                </p>
                <div className="grid grid-cols-2 md:grid-cols-4 gap-4 mt-6">
                  <Stat label="Market Cap" value={fmtNum(profile.marketCap, { compact: true, currency: true })} />
                  <Stat label="Sector" value={profile.sector || "—"} small />
                  <Stat label="Industry" value={profile.industry || "—"} small />
                  <Stat label="Country" value={profile.country || "—"} small />
                  <Stat label="Employees" value={profile.employees ? profile.employees.toLocaleString() : "—"} small />
                  <Stat label="CEO" value={profile.ceo || "—"} small />
                  <Stat label="IPO" value={profile.ipoDate || "—"} small />
                  <Stat label="Beta" value={profile.beta ? Number(profile.beta).toFixed(2) : "—"} small />
                </div>
              </>
            ) : <Skeleton lines={6} />}
          </GlassCard>

          <GlassCard eyebrow="// 6-month price" title="Trajectory" testId="price-chart-card">
            {history.length > 0 ? (
              <ResponsiveContainer width="100%" height={220}>
                <LineChart data={history} margin={{ top: 6, right: 8, bottom: 0, left: 0 }}>
                  <XAxis dataKey="date" hide />
                  <YAxis domain={["auto", "auto"]} hide />
                  <Tooltip
                    contentStyle={{ background: "rgba(10,12,18,0.95)", border: "1px solid var(--border-strong)", borderRadius: 12, fontSize: 12 }}
                    labelStyle={{ color: "var(--text-dim)" }}
                  />
                  <Line type="monotone" dataKey="close" stroke="var(--accent)" strokeWidth={2} dot={false} />
                </LineChart>
              </ResponsiveContainer>
            ) : <Skeleton lines={6} />}
            {quote && (
              <div className="mt-4 grid grid-cols-2 gap-3">
                <Stat label="52W Low"  value={fmtNum(quote.yearLow,  { digits: 2 })} small />
                <Stat label="52W High" value={fmtNum(quote.yearHigh, { digits: 2 })} small />
              </div>
            )}
          </GlassCard>
        </div>

        {/* Financials + Valuation */}
        <div className="grid lg:grid-cols-3 gap-6">
          <GlassCard eyebrow="// fundamentals" title="Revenue & Net Income" className="lg:col-span-2" testId="financials-card">
            {revChart.length > 0 ? (
              <ResponsiveContainer width="100%" height={260}>
                <BarChart data={revChart}>
                  <XAxis dataKey="year" stroke="var(--text-faint)" fontSize={11} />
                  <YAxis stroke="var(--text-faint)" fontSize={11} tickFormatter={(v) => fmtNum(v, { compact: true })} />
                  <Tooltip
                    formatter={(v) => fmtNum(v, { compact: true, currency: true })}
                    contentStyle={{ background: "rgba(10,12,18,0.95)", border: "1px solid var(--border-strong)", borderRadius: 12 }}
                  />
                  <Bar dataKey="revenue"    fill="var(--accent)"   radius={[6, 6, 0, 0]} />
                  <Bar dataKey="netIncome"  fill="var(--accent-3)" radius={[6, 6, 0, 0]} />
                </BarChart>
              </ResponsiveContainer>
            ) : <Skeleton lines={6} />}

            {agents.financial && (
              <div className="mt-5 grid grid-cols-2 md:grid-cols-4 gap-3">
                <Stat label="Rev Growth"  value={`${agents.financial.revenue_growth_yoy_pct ?? "—"}%`} />
                <Stat label="Net Margin"  value={`${agents.financial.net_margin_pct ?? "—"}%`} />
                <Stat label="ROE"         value={`${agents.financial.roe_pct ?? "—"}%`} />
                <Stat label="D/E"         value={agents.financial.debt_to_equity ?? "—"} />
              </div>
            )}
          </GlassCard>

          <GlassCard eyebrow="// valuation" title="Fair value" testId="valuation-card">
            {ratios ? (
              <div className="space-y-3">
                <Stat label="P/E (TTM)"     value={ratios.peTTM ? Number(ratios.peTTM).toFixed(2) : "—"} small />
                <Stat label="PEG"           value={ratios.pegTTM ? Number(ratios.pegTTM).toFixed(2) : "—"} small />
                <Stat label="EV/EBITDA"     value={ratios.evToEbitda ? Number(ratios.evToEbitda).toFixed(2) : "—"} small />
                <Stat label="P/B"           value={ratios.pbTTM ? Number(ratios.pbTTM).toFixed(2) : "—"} small />
                <Stat label="DCF Fair Value" value={fmtNum(ratios.dcfFairValue, { currency: true })} small />
                {fairValue.fair_value_mid && (
                  <div className="mt-4 pt-4 border-t border-[var(--border)]">
                    <div className="label-eyebrow mb-2">AI Range</div>
                    <div className="text-sm font-mono">
                      ${Number(fairValue.fair_value_low).toFixed(0)} —{" "}
                      <span className="text-[var(--accent)]">${Number(fairValue.fair_value_mid).toFixed(0)}</span>{" "}
                      — ${Number(fairValue.fair_value_high).toFixed(0)}
                    </div>
                    <div className="text-xs mt-1 text-[var(--text-dim)]">{fairValue.valuation_verdict}</div>
                  </div>
                )}
              </div>
            ) : <Skeleton lines={6} />}
          </GlassCard>
        </div>

        {/* Bull vs Bear */}
        <div className="grid lg:grid-cols-2 gap-6">
          <GlassCard glow="glow-mint" testId="bull-card">
            <div className="flex items-center gap-3 mb-4">
              <ThumbsUp className="w-5 h-5 text-[var(--accent)]" />
              <div className="label-eyebrow">// bull case</div>
            </div>
            <h3 className="font-serif text-2xl mb-4 italic">Why you'd buy this</h3>
            {agents.bull ? (
              <ul className="space-y-3">
                {(agents.bull.thesis_points || []).map((p, i) => (
                  <li key={i} className="flex gap-3 text-sm">
                    <span className="text-[var(--accent)] font-mono">+{(i + 1).toString().padStart(2, "0")}</span>
                    <span className="text-[var(--text-dim)]">{p}</span>
                  </li>
                ))}
                {agents.bull.catalysts?.length > 0 && (
                  <li className="pt-3 border-t border-[var(--border)]">
                    <div className="label-eyebrow mb-2">Catalysts</div>
                    <div className="flex flex-wrap gap-2">
                      {agents.bull.catalysts.map((c, i) => (
                        <span key={i} className="text-xs px-3 py-1 rounded-full bg-[var(--accent)]/10 border border-[var(--accent)]/30 text-[var(--accent)]">{c}</span>
                      ))}
                    </div>
                  </li>
                )}
              </ul>
            ) : <Skeleton lines={5} />}
          </GlassCard>

          <GlassCard glow="glow-orange" testId="bear-card">
            <div className="flex items-center gap-3 mb-4">
              <ThumbsDown className="w-5 h-5 text-[var(--danger)]" />
              <div className="label-eyebrow">// bear case</div>
            </div>
            <h3 className="font-serif text-2xl mb-4 italic">Why you'd pass</h3>
            {agents.bear ? (
              <ul className="space-y-3">
                {(agents.bear.thesis_points || []).map((p, i) => (
                  <li key={i} className="flex gap-3 text-sm">
                    <span className="text-[var(--danger)] font-mono">-{(i + 1).toString().padStart(2, "0")}</span>
                    <span className="text-[var(--text-dim)]">{p}</span>
                  </li>
                ))}
                {agents.bear.risks?.length > 0 && (
                  <li className="pt-3 border-t border-[var(--border)]">
                    <div className="label-eyebrow mb-2">Risks</div>
                    <div className="flex flex-wrap gap-2">
                      {agents.bear.risks.map((c, i) => (
                        <span key={i} className="text-xs px-3 py-1 rounded-full bg-[var(--danger)]/10 border border-[var(--danger)]/30 text-[var(--danger)]">{c}</span>
                      ))}
                    </div>
                  </li>
                )}
              </ul>
            ) : <Skeleton lines={5} />}
          </GlassCard>
        </div>

        {/* Research + Macro */}
        <div className="grid lg:grid-cols-2 gap-6">
          <GlassCard eyebrow="// business" title="Moat & Market Position" testId="research-card">
            {agents.research ? (
              <div className="space-y-4">
                <div className="text-sm text-[var(--text-dim)] leading-relaxed">
                  {agents.research.business_summary}
                </div>
                <div className="grid grid-cols-2 gap-3">
                  <Stat label="Moat"           value={agents.research.moat_strength || "—"} small />
                  <Stat label="Market Position" value={agents.research.market_position || "—"} small />
                </div>
                <div>
                  <div className="label-eyebrow mb-2">Growth Drivers</div>
                  <div className="flex flex-wrap gap-2">
                    {(agents.research.growth_drivers || []).map((g, i) => (
                      <span key={i} className="text-xs px-3 py-1 rounded-full glass-strong glass">{g}</span>
                    ))}
                  </div>
                </div>
              </div>
            ) : <Skeleton lines={5} />}
          </GlassCard>

          <GlassCard eyebrow="// macro" title="Macro & Sector context" testId="macro-card">
            {agents.macro ? (
              <div className="space-y-4">
                <div className="grid grid-cols-2 gap-3">
                  <Stat label="Rate sensitivity"  value={agents.macro.rate_sensitivity || "—"} small />
                  <Stat label="Inflation impact"  value={agents.macro.inflation_impact || "—"} small />
                  <Stat label="Sector phase"      value={agents.macro.sector_cycle_phase || "—"} small />
                  <Stat label="FX exposure"       value={agents.macro.fx_exposure || "—"} small />
                </div>
                {agents.macro.macro_tailwinds && (
                  <div>
                    <div className="label-eyebrow mb-2 text-[var(--accent)]">Tailwinds</div>
                    <ul className="text-sm text-[var(--text-dim)] space-y-1">
                      {agents.macro.macro_tailwinds.map((t, i) => <li key={i}>↑ {t}</li>)}
                    </ul>
                  </div>
                )}
                {agents.macro.macro_headwinds && (
                  <div>
                    <div className="label-eyebrow mb-2 text-[var(--danger)]">Headwinds</div>
                    <ul className="text-sm text-[var(--text-dim)] space-y-1">
                      {agents.macro.macro_headwinds.map((t, i) => <li key={i}>↓ {t}</li>)}
                    </ul>
                  </div>
                )}
              </div>
            ) : <Skeleton lines={5} />}
          </GlassCard>
        </div>

        {/* Analyst + Peers */}
        <div className="grid lg:grid-cols-2 gap-6">
          <GlassCard eyebrow="// the street" title="Analyst consensus" testId="analyst-card">
            {analyst ? (
              <div className="space-y-4">
                <div className="grid grid-cols-3 gap-3">
                  <Stat label="Target low"   value={fmtNum(analyst.targetLow, { currency: true })} small />
                  <Stat label="Consensus"    value={fmtNum(analyst.targetConsensus, { currency: true })} small />
                  <Stat label="Target high"  value={fmtNum(analyst.targetHigh, { currency: true })} small />
                </div>
                {(analyst.strongBuy ?? null) !== null && (
                  <div className="flex items-center gap-2 flex-wrap">
                    {["strongBuy","buy","hold","sell","strongSell"].map((k, i) => (
                      <div key={k} className="text-xs font-mono px-3 py-1 rounded-full border border-[var(--border)]">
                        {k}: <span className="text-[var(--text)]">{analyst[k] ?? 0}</span>
                      </div>
                    ))}
                  </div>
                )}
              </div>
            ) : <Skeleton lines={4} />}
          </GlassCard>

          <GlassCard eyebrow="// peers" title="Direct competitors" testId="peers-card">
            {peers.length > 0 ? (
              <div className="space-y-2">
                {peers.map((p) => (
                  <Link
                    key={p.ticker} to={`/research/${p.ticker}`}
                    data-testid={`peer-${p.ticker}`}
                    className="flex items-center justify-between px-3 py-2.5 rounded-xl hover:bg-white/[0.04] transition border border-transparent hover:border-[var(--border)]"
                  >
                    <div className="flex items-center gap-3">
                      <span className="font-mono text-sm text-[var(--accent)]">{p.ticker}</span>
                      <span className="text-sm text-[var(--text-dim)]">{p.name}</span>
                    </div>
                    <span className="font-mono text-xs text-[var(--text-faint)]">
                      {fmtNum(p.marketCap, { compact: true, currency: true })}
                    </span>
                  </Link>
                ))}
              </div>
            ) : <Skeleton lines={5} />}
          </GlassCard>
        </div>

        {/* News */}
        <GlassCard eyebrow="// the tape" title="Latest news" testId="news-card">
          {news.length > 0 ? (
            <div className="grid md:grid-cols-2 gap-3">
              {news.slice(0, 8).map((n, i) => (
                <a key={i} href={n.url} target="_blank" rel="noreferrer"
                   className="glass-strong glass rounded-xl p-4 hover:border-[var(--border-strong)] transition group">
                  <div className="flex items-center justify-between mb-2">
                    <span className="label-eyebrow truncate">{n.site || "—"}</span>
                    <ExternalLink className="w-3 h-3 text-[var(--text-faint)] group-hover:text-[var(--accent)]" />
                  </div>
                  <div className="text-sm font-medium leading-snug line-clamp-2">{n.title}</div>
                  {n.snippet && <div className="text-xs text-[var(--text-dim)] mt-2 line-clamp-2">{n.snippet}</div>}
                </a>
              ))}
            </div>
          ) : <Skeleton lines={6} />}
        </GlassCard>

        {/* Activity log */}
        <GlassCard eyebrow="// pipeline log" title="Reasoning trace" testId="log-card">
          <div className="font-mono text-xs space-y-1 max-h-60 overflow-auto">
            {steps.length === 0 && <div className="text-[var(--text-faint)]">connecting…</div>}
            {steps.map((s, i) => (
              <div key={i} className="text-[var(--text-dim)]">
                <span className="text-[var(--text-faint)]">[{new Date(s.t).toLocaleTimeString()}]</span> {s.text}
              </div>
            ))}
          </div>
        </GlassCard>
      </div>
    </div>
  );
}

// --- small UI helpers ---

function Stat({ label, value, small, good, bad }) {
  return (
    <div>
      <div className="label-eyebrow mb-1">{label}</div>
      <div className={`${small ? "text-sm" : "text-xl"} font-medium ${good ? "text-[var(--accent)]" : bad ? "text-[var(--danger)]" : ""}`}>
        {value ?? "—"}
      </div>
    </div>
  );
}

function Skeleton({ lines = 4 }) {
  return (
    <div className="space-y-2">
      {Array.from({ length: lines }).map((_, i) => (
        <div key={i} className="h-3 rounded shimmer" style={{ width: `${60 + ((i * 13) % 35)}%` }} />
      ))}
    </div>
  );
}

function Gauge({ value }) {
  const v = Math.max(0, Math.min(100, value));
  const stroke = v > 70 ? "var(--accent)" : v > 45 ? "var(--gold)" : "var(--danger)";
  const C = 2 * Math.PI * 48;
  const offset = C - (v / 100) * C;
  return (
    <div className="glass-strong glass rounded-2xl p-4 flex items-center gap-4" data-testid="gauge">
      <svg width="110" height="110" viewBox="0 0 110 110">
        <circle cx="55" cy="55" r="48" stroke="rgba(255,255,255,0.08)" strokeWidth="8" fill="none" />
        <circle cx="55" cy="55" r="48" stroke={stroke} strokeWidth="8" fill="none"
                strokeDasharray={C} strokeDashoffset={offset} strokeLinecap="round"
                transform="rotate(-90 55 55)" style={{ transition: "stroke-dashoffset 1.2s ease" }} />
        <text x="55" y="58" textAnchor="middle" fontSize="22" fontFamily="JetBrains Mono" fill="#e7ecf3" data-testid="confidence-score">{v}</text>
        <text x="55" y="74" textAnchor="middle" fontSize="9" fontFamily="JetBrains Mono" fill="#5b6477" letterSpacing="2">CONF</text>
      </svg>
      <div className="flex-1">
        <div className="label-eyebrow">Confidence</div>
        <div className="text-sm text-[var(--text-dim)] mt-1">
          {v > 70 ? "High conviction." : v > 45 ? "Moderate conviction." : "Low conviction — proceed with care."}
        </div>
      </div>
    </div>
  );
}
