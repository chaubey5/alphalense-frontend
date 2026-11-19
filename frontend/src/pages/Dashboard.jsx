import { Link, useParams } from "react-router-dom";
import {
  AlertTriangle, ArrowLeft, TrendingDown, TrendingUp,
} from "lucide-react";
import SearchBar from "@/components/SearchBar";
import GlassCard from "@/components/GlassCard";
import AgentPipelineStrip from "@/components/dashboard/AgentPipelineStrip";
import VerdictHero from "@/components/dashboard/VerdictHero";
import { BullCard, BearCard } from "@/components/dashboard/BullBearCards";
import {
  OverviewCard, PriceChartCard, RevenueChartCard, ValuationCard,
  ResearchCard, MacroCard, AnalystCard, PeersCard, NewsCard, LogCard,
} from "@/components/dashboard/Sections";
import useResearchPipeline from "@/hooks/useResearchPipeline";
import { AGENT_LABELS } from "@/lib/agents";
import { fmtNum } from "@/lib/format";

function buildRevenueChart(incomeRows = []) {
  return incomeRows.slice().reverse().map((r) => ({
    year: (r.date || "").slice(0, 4),
    revenue: r.revenue ?? null,
    netIncome: r.netIncome ?? null,
  }));
}

function PriceBlock({ quote, loading }) {
  if (!quote && loading) return <span className="shimmer inline-block w-32 h-10 rounded" />;
  if (!quote) return <span className="text-sm text-[var(--text-faint)]">Quote unavailable</span>;
  const change = Number(quote.change);
  const hasChange = Number.isFinite(change);
  const isUp = hasChange && change >= 0;
  const Icon = isUp ? TrendingUp : TrendingDown;
  const color = !hasChange
    ? "text-[var(--text-dim)]"
    : isUp ? "text-[var(--accent)]" : "text-[var(--danger)]";
  return (
    <div className="text-right">
      <div className="h-display text-5xl">{fmtNum(quote.price, { digits: 2 })}</div>
      <div className={`mt-1 font-mono text-sm flex items-center justify-end gap-2 ${color}`}>
        {hasChange && <Icon className="w-4 h-4" />}
        {hasChange ? `${fmtNum(change)} (${fmtNum(quote.changesPercentage)}%)` : "Change unavailable"}
      </div>
    </div>
  );
}

export default function Dashboard() {
  const { ticker } = useParams();
  const { marketData, agents, steps, status, error, done, loading } =
    useResearchPipeline(ticker, AGENT_LABELS);

  const moderator = agents.moderator || {};
  const quote     = marketData?.quote;
  const profile   = marketData?.profile;
  const ratios    = marketData?.ratios;
  const peers     = marketData?.peers   || [];
  const news      = marketData?.news    || [];
  const history   = marketData?.history || [];
  const analyst   = marketData?.analyst;
  const revChart  = buildRevenueChart(
    Array.isArray(marketData?.financials?.income) ? marketData.financials.income : [],
  );

  return (
    <div className="min-h-screen grid-bg pb-20" data-testid="research-dashboard">
      <header className="px-6 md:px-12 py-5 flex items-center gap-6 border-b border-[var(--border)] sticky top-0 z-30 backdrop-blur-xl bg-[rgba(6,7,11,0.6)]">
        <Link to="/" data-testid="back-home-btn"
              className="flex items-center gap-2 text-sm text-[var(--text-dim)] hover:text-[var(--text)]">
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
          <PriceBlock quote={quote} loading={loading} />
        </div>

        {error && (
          <GlassCard glow="glow-orange">
            <div className="flex items-center gap-3 text-[var(--danger)]">
              <AlertTriangle className="w-5 h-5" /> {error}
            </div>
          </GlassCard>
        )}

        <AgentPipelineStrip status={status} />

        <VerdictHero moderator={moderator} loading={loading} />

        <div className="grid lg:grid-cols-3 gap-6">
          <OverviewCard profile={profile} loading={loading} />
          <PriceChartCard history={history} quote={quote} loading={loading} />
        </div>

        <div className="grid lg:grid-cols-3 gap-6">
          <RevenueChartCard revChart={revChart} financial={agents.financial} loading={loading} />
          <ValuationCard ratios={ratios} fairValue={agents.valuation} loading={loading} />
        </div>

        <div className="grid lg:grid-cols-2 gap-6">
          <BullCard bull={agents.bull} loading={loading} />
          <BearCard bear={agents.bear} loading={loading} />
        </div>

        <div className="grid lg:grid-cols-2 gap-6">
          <ResearchCard research={agents.research} loading={loading} />
          <MacroCard macro={agents.macro} loading={loading} />
        </div>

        <div className="grid lg:grid-cols-2 gap-6">
          <AnalystCard analyst={analyst} loading={loading} />
          <PeersCard peers={peers} loading={loading} />
        </div>

        <NewsCard news={news} loading={loading} />

        <LogCard steps={steps} loading={loading} />
      </div>
    </div>
  );
}
