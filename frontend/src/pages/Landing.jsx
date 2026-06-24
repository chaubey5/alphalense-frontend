import { Link } from "react-router-dom";
import { motion } from "framer-motion";
import { Sparkles, Activity, ShieldCheck, Layers, Zap, BarChart3 } from "lucide-react";
import SearchBar from "@/components/SearchBar";

const FEATURES = [
  { icon: Sparkles, title: "6-Agent AI Council", desc: "Research, Financial, Valuation, Bull, Bear, Macro analysts debate every stock." },
  { icon: Layers, title: "Multi-Provider Data", desc: "FMP + Finnhub + Alpha Vantage + GNews — failover and cross-validation built in." },
  { icon: BarChart3, title: "Fair-Value Modeling", desc: "DCF, P/E, EV/EBITDA, Graham Number — triangulated into a single fair-value range." },
  { icon: Activity, title: "Streaming Analysis", desc: "SSE-powered live updates. Watch every agent reason in real time." },
  { icon: ShieldCheck, title: "Transparent Verdict", desc: "INVEST / HOLD / PASS with confidence score and exact reasoning behind it." },
  { icon: Zap, title: "Built for Speed", desc: "Parallel agent execution. Most reports complete in under 60 seconds." },
];

const SUGGESTIONS = ["AAPL", "NVDA", "TSLA", "MSFT", "GOOGL", "AMZN", "META"];

export default function Landing() {
  return (
    <div className="min-h-screen relative grid-bg" data-testid="landing-page">
      {/* Nav */}
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
          <a href="#agents" className="hover:text-[var(--text)] transition">Agents</a>
          <a href="#data" className="hover:text-[var(--text)] transition">Data</a>
          <Link to="/research/NVDA" className="btn-ghost rounded-full px-4 py-2 text-xs" data-testid="nav-demo-btn">
            Try a demo →
          </Link>
        </nav>
      </header>

      {/* Hero */}
      <section className="px-8 md:px-14 pt-10 pb-24">
        <div className="max-w-6xl mx-auto">
          <motion.div
            initial={{ opacity: 0, y: 20 }} animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.7 }}
            className="label-eyebrow mb-6 flex items-center gap-2"
          >
            <span className="w-1.5 h-1.5 rounded-full bg-[var(--accent)] pulse-dot" />
            Live · multi-agent equity research engine
          </motion.div>

          <motion.h1
            initial={{ opacity: 0, y: 20 }} animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.8, delay: 0.05 }}
            className="h-display text-6xl md:text-8xl lg:text-9xl max-w-5xl"
          >
            Institutional-grade research, <span className="italic text-[var(--accent)]">in seconds.</span>
          </motion.h1>

          <motion.p
            initial={{ opacity: 0, y: 20 }} animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.8, delay: 0.15 }}
            className="mt-8 text-lg md:text-xl text-[var(--text-dim)] max-w-2xl"
          >
            Six specialist AI agents debate the bull case, the bear case, valuation models,
            and the macro backdrop — then deliver one transparent verdict.
          </motion.p>

          <motion.div
            initial={{ opacity: 0, y: 24 }} animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.8, delay: 0.25 }}
            className="mt-10 max-w-3xl"
          >
            <SearchBar size="lg" autoFocus />
            <div className="mt-4 flex flex-wrap items-center gap-2">
              <span className="label-eyebrow mr-2">Try</span>
              {SUGGESTIONS.map((t) => (
                <Link
                  key={t} to={`/research/${t}`}
                  data-testid={`suggest-${t}`}
                  className="font-mono text-xs px-3 py-1.5 rounded-full border border-[var(--border)] hover:border-[var(--border-strong)] hover:bg-white/[0.04] transition"
                >
                  {t}
                </Link>
              ))}
            </div>
          </motion.div>
        </div>

        {/* Hero stat ribbon */}
        <motion.div
          initial={{ opacity: 0, y: 30 }} animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.8, delay: 0.4 }}
          className="max-w-6xl mx-auto mt-24 glass glass-strong px-8 py-6 grid grid-cols-2 md:grid-cols-4 gap-6"
        >
          {[
            ["6", "AI analyst agents"],
            ["4", "data providers"],
            ["~50s", "average report time"],
            ["100%", "transparent reasoning"],
          ].map(([v, l], i) => (
            <div key={i} className="flex flex-col">
              <div className="h-display text-4xl md:text-5xl text-[var(--accent)]">{v}</div>
              <div className="label-eyebrow mt-2">{l}</div>
            </div>
          ))}
        </motion.div>
      </section>

      {/* Features */}
      <section id="features" className="px-8 md:px-14 py-24">
        <div className="max-w-6xl mx-auto">
          <div className="label-eyebrow mb-3">// 02 · capabilities</div>
          <h2 className="h-display text-4xl md:text-6xl mb-14 max-w-3xl">
            One platform. Six analysts. <span className="italic">Zero hand-waving.</span>
          </h2>
          <div className="grid md:grid-cols-2 lg:grid-cols-3 gap-5">
            {FEATURES.map((f, i) => (
              <motion.div
                key={i}
                initial={{ opacity: 0, y: 20 }}
                whileInView={{ opacity: 1, y: 0 }}
                viewport={{ once: true, margin: "-60px" }}
                transition={{ duration: 0.5, delay: i * 0.05 }}
                className="glass p-7 tilt"
              >
                <f.icon className="w-6 h-6 text-[var(--accent)] mb-5" />
                <div className="text-lg font-medium mb-2">{f.title}</div>
                <div className="text-sm text-[var(--text-dim)] leading-relaxed">{f.desc}</div>
              </motion.div>
            ))}
          </div>
        </div>
      </section>

      {/* Agents row */}
      <section id="agents" className="px-8 md:px-14 py-24">
        <div className="max-w-6xl mx-auto">
          <div className="label-eyebrow mb-3">// 03 · the council</div>
          <h2 className="h-display text-4xl md:text-6xl mb-14 max-w-3xl">
            Six specialists. One <span className="italic text-[var(--accent)]">verdict.</span>
          </h2>
          <div className="grid md:grid-cols-3 gap-4">
            {[
              ["Research", "Business model, moat, market position."],
              ["Financial", "Income, balance sheet, FCF, margins, ROE."],
              ["Valuation", "DCF, P/E, EV/EBITDA, Graham, fair-value range."],
              ["Bull", "The strongest possible case to buy."],
              ["Bear", "The strongest possible case to avoid."],
              ["Macro", "Fed cycle, FX, sector phase, headwinds."],
            ].map(([n, d], i) => (
              <div key={n} className="glass p-6">
                <div className="flex items-center gap-3 mb-3">
                  <span className="font-mono text-xs text-[var(--accent)]">A.{String(i + 1).padStart(2, "0")}</span>
                  <span className="text-xl font-medium">{n} Agent</span>
                </div>
                <div className="text-sm text-[var(--text-dim)]">{d}</div>
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
