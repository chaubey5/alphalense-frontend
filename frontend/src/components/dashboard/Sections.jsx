import { ExternalLink } from "lucide-react";
import { Link } from "react-router-dom";
import { LineChart, Line, ResponsiveContainer, XAxis, YAxis, Tooltip, BarChart, Bar } from "recharts";
import GlassCard from "@/components/GlassCard";
import Stat from "@/components/dashboard/Stat";
import Skeleton from "@/components/dashboard/Skeleton";
import { fmtNum } from "@/lib/format";

const TOOLTIP_STYLE = {
  background: "rgba(10,12,18,0.95)",
  border: "1px solid var(--border-strong)",
  borderRadius: 12,
  fontSize: 12,
};
const TOOLTIP_LABEL = { color: "var(--text-dim)" };
const PRICE_MARGIN = { top: 6, right: 8, bottom: 0, left: 0 };

function compactTick(value) { return fmtNum(value, { compact: true }); }
function compactCurrencyTip(value) { return fmtNum(value, { compact: true, currency: true }); }

export function OverviewCard({ profile }) {
  return (
    <GlassCard eyebrow="// company" title="Overview" className="lg:col-span-2" testId="overview-card">
      {profile ? (
        <>
          <p className="text-sm text-[var(--text-dim)] leading-relaxed line-clamp-6">
            {profile.description || "No description available."}
          </p>
          <div className="grid grid-cols-2 md:grid-cols-4 gap-4 mt-6">
            <Stat label="Market Cap" value={fmtNum(profile.marketCap, { compact: true, currency: true })} />
            <Stat label="Sector"     value={profile.sector || "—"} small />
            <Stat label="Industry"   value={profile.industry || "—"} small />
            <Stat label="Country"    value={profile.country || "—"} small />
            <Stat label="Employees"  value={profile.employees ? profile.employees.toLocaleString() : "—"} small />
            <Stat label="CEO"        value={profile.ceo || "—"} small />
            <Stat label="IPO"        value={profile.ipoDate || "—"} small />
            <Stat label="Beta"       value={profile.beta ? Number(profile.beta).toFixed(2) : "—"} small />
          </div>
        </>
      ) : <Skeleton lines={6} />}
    </GlassCard>
  );
}

export function PriceChartCard({ history, quote }) {
  return (
    <GlassCard eyebrow="// 6-month price" title="Trajectory" testId="price-chart-card">
      {history.length > 0 ? (
        <ResponsiveContainer width="100%" height={220}>
          <LineChart data={history} margin={PRICE_MARGIN}>
            <XAxis dataKey="date" hide />
            <YAxis domain={["auto", "auto"]} hide />
            <Tooltip contentStyle={TOOLTIP_STYLE} labelStyle={TOOLTIP_LABEL} />
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
  );
}

export function RevenueChartCard({ revChart, financial }) {
  return (
    <GlassCard eyebrow="// fundamentals" title="Revenue & Net Income"
               className="lg:col-span-2" testId="financials-card">
      {revChart.length > 0 ? (
        <ResponsiveContainer width="100%" height={260}>
          <BarChart data={revChart}>
            <XAxis dataKey="year" stroke="var(--text-faint)" fontSize={11} />
            <YAxis stroke="var(--text-faint)" fontSize={11} tickFormatter={compactTick} />
            <Tooltip formatter={compactCurrencyTip} contentStyle={TOOLTIP_STYLE} />
            <Bar dataKey="revenue"   fill="var(--accent)"   radius={[6, 6, 0, 0]} />
            <Bar dataKey="netIncome" fill="var(--accent-3)" radius={[6, 6, 0, 0]} />
          </BarChart>
        </ResponsiveContainer>
      ) : <Skeleton lines={6} />}

      {financial && (
        <div className="mt-5 grid grid-cols-2 md:grid-cols-4 gap-3">
          <Stat label="Rev Growth" value={`${financial.revenue_growth_yoy_pct ?? "—"}%`} />
          <Stat label="Net Margin" value={`${financial.net_margin_pct ?? "—"}%`} />
          <Stat label="ROE"        value={`${financial.roe_pct ?? "—"}%`} />
          <Stat label="D/E"        value={financial.debt_to_equity ?? "—"} />
        </div>
      )}
    </GlassCard>
  );
}

export function ValuationCard({ ratios, fairValue }) {
  return (
    <GlassCard eyebrow="// valuation" title="Fair value" testId="valuation-card">
      {ratios ? (
        <div className="space-y-3">
          <Stat label="P/E (TTM)"     value={ratios.peTTM ? Number(ratios.peTTM).toFixed(2) : "—"} small />
          <Stat label="PEG"           value={ratios.pegTTM ? Number(ratios.pegTTM).toFixed(2) : "—"} small />
          <Stat label="EV/EBITDA"     value={ratios.evToEbitda ? Number(ratios.evToEbitda).toFixed(2) : "—"} small />
          <Stat label="P/B"           value={ratios.pbTTM ? Number(ratios.pbTTM).toFixed(2) : "—"} small />
          <Stat label="DCF Fair Value" value={fmtNum(ratios.dcfFairValue, { currency: true })} small />
          {fairValue?.fair_value_mid && (
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
  );
}

export function ResearchCard({ research }) {
  return (
    <GlassCard eyebrow="// business" title="Moat & Market Position" testId="research-card">
      {research ? (
        <div className="space-y-4">
          <div className="text-sm text-[var(--text-dim)] leading-relaxed">
            {research.business_summary}
          </div>
          <div className="grid grid-cols-2 gap-3">
            <Stat label="Moat"            value={research.moat_strength || "—"} small />
            <Stat label="Market Position" value={research.market_position || "—"} small />
          </div>
          <div>
            <div className="label-eyebrow mb-2">Growth Drivers</div>
            <div className="flex flex-wrap gap-2">
              {(research.growth_drivers || []).map((g) => (
                <span key={g} className="text-xs px-3 py-1 rounded-full glass-strong glass">{g}</span>
              ))}
            </div>
          </div>
        </div>
      ) : <Skeleton lines={5} />}
    </GlassCard>
  );
}

export function MacroCard({ macro }) {
  return (
    <GlassCard eyebrow="// macro" title="Macro & Sector context" testId="macro-card">
      {macro ? (
        <div className="space-y-4">
          <div className="grid grid-cols-2 gap-3">
            <Stat label="Rate sensitivity" value={macro.rate_sensitivity || "—"} small />
            <Stat label="Inflation impact" value={macro.inflation_impact || "—"} small />
            <Stat label="Sector phase"     value={macro.sector_cycle_phase || "—"} small />
            <Stat label="FX exposure"      value={macro.fx_exposure || "—"} small />
          </div>
          {macro.macro_tailwinds && (
            <div>
              <div className="label-eyebrow mb-2 text-[var(--accent)]">Tailwinds</div>
              <ul className="text-sm text-[var(--text-dim)] space-y-1">
                {macro.macro_tailwinds.map((t) => <li key={t}>↑ {t}</li>)}
              </ul>
            </div>
          )}
          {macro.macro_headwinds && (
            <div>
              <div className="label-eyebrow mb-2 text-[var(--danger)]">Headwinds</div>
              <ul className="text-sm text-[var(--text-dim)] space-y-1">
                {macro.macro_headwinds.map((t) => <li key={t}>↓ {t}</li>)}
              </ul>
            </div>
          )}
        </div>
      ) : <Skeleton lines={5} />}
    </GlassCard>
  );
}

const ANALYST_BUCKETS = ["strongBuy", "buy", "hold", "sell", "strongSell"];

export function AnalystCard({ analyst }) {
  const hasTargets = analyst && (analyst.targetConsensus || analyst.targetHigh || analyst.targetLow);
  const hasRatings = analyst && (analyst.strongBuy ?? null) !== null;
  return (
    <GlassCard eyebrow="// the street" title="Analyst consensus" testId="analyst-card">
      {analyst ? (
        <div className="space-y-4">
          {hasTargets ? (
            <div className="grid grid-cols-3 gap-3">
              <Stat label="Target low"  value={fmtNum(analyst.targetLow,       { currency: true })} small />
              <Stat label="Consensus"   value={fmtNum(analyst.targetConsensus, { currency: true })} small />
              <Stat label="Target high" value={fmtNum(analyst.targetHigh,      { currency: true })} small />
            </div>
          ) : (
            <div className="text-xs text-[var(--text-faint)]">Price targets not available on this data tier.</div>
          )}
          {hasRatings && (
            <div className="flex items-center gap-2 flex-wrap">
              {ANALYST_BUCKETS.map((bucket) => (
                <div key={bucket} className="text-xs font-mono px-3 py-1 rounded-full border border-[var(--border)]">
                  {bucket}: <span className="text-[var(--text)]">{analyst[bucket] ?? 0}</span>
                </div>
              ))}
            </div>
          )}
        </div>
      ) : <Skeleton lines={4} />}
    </GlassCard>
  );
}

export function PeersCard({ peers }) {
  return (
    <GlassCard eyebrow="// peers" title="Direct competitors" testId="peers-card">
      {peers.length > 0 ? (
        <div className="space-y-2">
          {peers.map((p) => (
            <Link key={p.ticker} to={`/research/${p.ticker}`}
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
  );
}

export function NewsCard({ news }) {
  return (
    <GlassCard eyebrow="// the tape" title="Latest news" testId="news-card">
      {news.length > 0 ? (
        <div className="grid md:grid-cols-2 gap-3">
          {news.slice(0, 8).map((n) => (
            <a key={n.url || n.title} href={n.url} target="_blank" rel="noreferrer"
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
  );
}

export function LogCard({ steps }) {
  return (
    <GlassCard eyebrow="// pipeline log" title="Reasoning trace" testId="log-card">
      <div className="font-mono text-xs space-y-1 max-h-60 overflow-auto">
        {steps.length === 0 && <div className="text-[var(--text-faint)]">connecting…</div>}
        {steps.map((s) => (
          <div key={`${s.t}-${s.text}`} className="text-[var(--text-dim)]">
            <span className="text-[var(--text-faint)]">[{new Date(s.t).toLocaleTimeString()}]</span> {s.text}
          </div>
        ))}
      </div>
    </GlassCard>
  );
}
