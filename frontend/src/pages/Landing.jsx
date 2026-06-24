import { Link } from "react-router-dom";
import { motion } from "framer-motion";
import { Sparkles, Activity, ShieldCheck, Layers, Zap, BarChart3 } from "lucide-react";
import SearchBar from "@/components/SearchBar";

const FEATURES = [
  { id: "council",   icon: Sparkles,    title: "6-Agent AI Council", desc: "Research, Financial, Valuation, Bull, Bear, Macro analysts debate every stock." },
  { id: "providers", icon: Layers,      title: "Multi-Provider Data", desc: "FMP + Finnhub + Alpha Vantage + GNews — failover and cross-validation built in." },
  { id: "fairvalue", icon: BarChart3,   title: "Fair-Value Modeling", desc: "DCF, P/E, EV/EBITDA, Graham Number — triangulated into a single fair-value range." },
  { id: "streaming", icon: Activity,    title: "Streaming Analysis", desc: "SSE-powered live updates. Watch every agent reason in real time." },
  { id: "verdict",   icon: ShieldCheck, title: "Transparent Verdict", desc: "INVEST / HOLD / PASS with confidence score and exact reasoning behind it." },
  { id: "speed",     icon: Zap,         title: "Built for Speed", desc: "Parallel agent execution. Most reports complete in under 60 seconds." },
];

const SUGGESTIONS = ["AAPL", "NVDA", "TSLA", "MSFT", "GOOGL", "AMZN", "META"];

const AGENTS = [
  { id: "research",  label: "Research",  blurb: "Business model, moat, market position." },
  { id: "financial", label: "Financial", blurb: "Income, balance sheet, FCF, margins, ROE." },
  { id: "valuation", label: "Valuation", blurb: "DCF, P/E, EV/EBITDA, Graham, fair-value range." },
  { id: "bull",      label: "Bull",      blurb: "The strongest possible case to buy." },
  { id: "bear",      label: "Bear",      blurb: "The strongest possible case to avoid." },
  { id: "macro",     label: "Macro",     blurb: "Fed cycle, FX, sector phase, headwinds." },
];

const STATS = [
  { id: "agents",    value: "6",    label: "AI analyst agents" },
  { id: "providers", value: "4",    label: "data providers" },
  { id: "time",      value: "~50s", label: "average report time" },
  { id: "trans",     value: "100%", label: "transparent reasoning" },
];

const HIDDEN = { opacity: 0, y: 20 };
const SHOWN  = { opacity: 1, y: 0 };
const SHOWN_24 = { opacity: 1, y: 0 };
const HIDDEN_24 = { opacity: 0, y: 24 };
const HIDDEN_30 = { opacity: 0, y: 30 };
const VP_ONCE = { once: true, margin: "-60px" };
const T_BASE  = { duration: 0.7 };
const T_05    = { duration: 0.8, delay: 0.05 };
const T_15    = { duration: 0.8, delay: 0.15 };
const T_25    = { duration: 0.8, delay: 0.25 };
const T_40    = { duration: 0.8, delay: 0.40 };

function featureTransition(idx) {
  return { duration: 0.5, delay: idx * 0.05 };
}

export default function Landing() {
  return (
    <div className="min-h-screen relative grid-bg" data-testid="landing-page">
      <header className="px-8 md:px-14 py-6 flex items-center justify-between">
        <Link to="/" className="flex items-center gap-3" data-testid="logo">
          <div className="w-9 h-9 glass-strong glass rounded-xl flex items-center justify-center">
            <div className="w-3 h-3 rounded-full bg-[var(--accent)] pulse-dot" />
          </div>
          <div>
            <div className="font-serif text-xl leading-none">AlphaLens</div>
            <div className="label-eyebrow mt-1">Investment Intelligence</div>
          </div>
        </Link>
        <nav className="hidden md:flex items-center gap-7 text-sm text-[var(--text-dim)]">
          <a href="#features" className="hover:text-[var(--text)] transition">Features</a>
          <a href="#agents"   className="hover:text-[var(--text)] transition">Agents</a>
          <a href="#data"     className="hover:text-[var(--text)] transition">Data</a>
          <Link to="/research/NVDA" className="btn-ghost rounded-full px-4 py-2 text-xs" data-testid="nav-demo-btn">
            Try a demo →
          </Link>
        </nav>
      </header>

      <section className="px-8 md:px-14 pt-10 pb-24">
        <div className="max-w-6xl mx-auto">
          <motion.div
            initial={HIDDEN} animate={SHOWN} transition={T_BASE}
            className="label-eyebrow mb-6 flex items-center gap-2"
          >
            <span className="w-1.5 h-1.5 rounded-full bg-[var(--accent)] pulse-dot" />
            Live · multi-agent equity research engine
          </motion.div>

          <motion.h1
            initial={HIDDEN} animate={SHOWN} transition={T_05}
            className="h-display text-6xl md:text-8xl lg:text-9xl max-w-5xl"
          >
            Institutional-grade research, <span className="italic text-[var(--accent)]">in seconds.</span>
          </motion.h1>

          <motion.p
            initial={HIDDEN} animate={SHOWN} transition={T_15}
            className="mt-8 text-lg md:text-xl text-[var(--text-dim)] max-w-2xl"
          >
            Six specialist AI agents debate the bull case, the bear case, valuation models,
            and the macro backdrop — then deliver one transparent verdict.
          </motion.p>

          <motion.div
            initial={HIDDEN_24} animate={SHOWN_24} transition={T_25}
            className="mt-10 max-w-3xl"
          >
            <SearchBar size="lg" autoFocus />
            <div className="mt-4 flex flex-wrap items-center gap-2">
              <span className="label-eyebrow mr-2">Try</span>
              {SUGGESTIONS.map((t) => (
                <Link key={t} to={`/research/${t}`}
                  data-testid={`suggest-${t}`}
                  className="font-mono text-xs px-3 py-1.5 rounded-full border border-[var(--border)] hover:border-[var(--border-strong)] hover:bg-white/[0.04] transition"
                >
                  {t}
                </Link>
              ))}
            </div>
          </motion.div>
        </div>

        <motion.div
          initial={HIDDEN_30} animate={SHOWN_24} transition={T_40}
          className="max-w-6xl mx-auto mt-24 glass glass-strong px-8 py-6 grid grid-cols-2 md:grid-cols-4 gap-6"
        >
          {STATS.map((s) => (
            <div key={s.id} className="flex flex-col">
              <div className="h-display text-4xl md:text-5xl text-[var(--accent)]">{s.value}</div>
              <div className="label-eyebrow mt-2">{s.label}</div>
            </div>
          ))}
        </motion.div>
      </section>

      <section id="features" className="px-8 md:px-14 py-24">
        <div className="max-w-6xl mx-auto">
          <div className="label-eyebrow mb-3">// 02 · capabilities</div>
          <h2 className="h-display text-4xl md:text-6xl mb-14 max-w-3xl">
            One platform. Six analysts. <span className="italic">Zero hand-waving.</span>
          </h2>
          <div className="grid md:grid-cols-2 lg:grid-cols-3 gap-5">
            {FEATURES.map((f, idx) => {
              const FIcon = f.icon;
              return (
                <motion.div
                  key={f.id}
                  initial={HIDDEN} whileInView={SHOWN}
                  viewport={VP_ONCE} transition={featureTransition(idx)}
                  className="glass p-7 tilt"
                >
                  <FIcon className="w-6 h-6 text-[var(--accent)] mb-5" />
                  <div className="text-lg font-medium mb-2">{f.title}</div>
                  <div className="text-sm text-[var(--text-dim)] leading-relaxed">{f.desc}</div>
                </motion.div>
              );
            })}
          </div>
        </div>
      </section>

      <section id="agents" className="px-8 md:px-14 py-24">
        <div className="max-w-6xl mx-auto">
          <div className="label-eyebrow mb-3">// 03 · the council</div>
          <h2 className="h-display text-4xl md:text-6xl mb-14 max-w-3xl">
            Six specialists. One <span className="italic text-[var(--accent)]">verdict.</span>
          </h2>
          <div className="grid md:grid-cols-3 gap-4">
            {AGENTS.map((a, idx) => (
              <div key={a.id} className="glass p-6">
                <div className="flex items-center gap-3 mb-3">
                  <span className="font-mono text-xs text-[var(--accent)]">A.{String(idx + 1).padStart(2, "0")}</span>
                  <span className="text-xl font-medium">{a.label} Agent</span>
                </div>
                <div className="text-sm text-[var(--text-dim)]">{a.blurb}</div>
              </div>
            ))}
          </div>
        </div>
      </section>

      <footer className="px-8 md:px-14 py-10 border-t border-[var(--border)] flex items-center justify-between text-sm text-[var(--text-faint)]">
        <span>AlphaLens · institutional research, democratized.</span>
        <span className="font-mono">v1.0</span>
      </footer>
    </div>
  );
}
