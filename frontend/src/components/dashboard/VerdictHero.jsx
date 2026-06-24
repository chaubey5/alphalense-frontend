import { motion } from "framer-motion";
import GlassCard from "@/components/GlassCard";
import { verdictClass, gaugeColor, convictionText } from "@/lib/format";

const HERO_INIT = { opacity: 0, y: 16 };
const HERO_ANIM = { opacity: 1, y: 0 };
const HERO_TRANS = { duration: 0.6 };
const STROKE_TRANS = { transition: "stroke-dashoffset 1.2s ease" };

function Stat({ label, value, good, bad }) {
  let tone = "";
  if (good) tone = "text-[var(--accent)]";
  else if (bad) tone = "text-[var(--danger)]";
  return (
    <div>
      <div className="label-eyebrow mb-1">{label}</div>
      <div className={`text-xl font-medium ${tone}`}>{value ?? "—"}</div>
    </div>
  );
}

function Gauge({ value }) {
  const v = Math.max(0, Math.min(100, value));
  const C = 2 * Math.PI * 48;
  const offset = C - (v / 100) * C;
  const stroke = gaugeColor(v);
  return (
    <div className="glass-strong glass rounded-2xl p-4 flex items-center gap-4" data-testid="gauge">
      <svg width="110" height="110" viewBox="0 0 110 110">
        <circle cx="55" cy="55" r="48" stroke="rgba(255,255,255,0.08)" strokeWidth="8" fill="none" />
        <circle
          cx="55" cy="55" r="48" stroke={stroke} strokeWidth="8" fill="none"
          strokeDasharray={C} strokeDashoffset={offset} strokeLinecap="round"
          transform="rotate(-90 55 55)" style={STROKE_TRANS}
        />
        <text x="55" y="58" textAnchor="middle" fontSize="22"
              fontFamily="JetBrains Mono" fill="#e7ecf3" data-testid="confidence-score">{v}</text>
        <text x="55" y="74" textAnchor="middle" fontSize="9"
              fontFamily="JetBrains Mono" fill="#5b6477" letterSpacing="2">CONF</text>
      </svg>
      <div className="flex-1">
        <div className="label-eyebrow">Confidence</div>
        <div className="text-sm text-[var(--text-dim)] mt-1">{convictionText(v)}</div>
      </div>
    </div>
  );
}

function glowFor(recommendation) {
  if (recommendation === "INVEST") return "glow-mint";
  if (recommendation === "PASS")   return "glow-orange";
  return "";
}

export default function VerdictHero({ moderator }) {
  if (!moderator?.recommendation) return null;

  return (
    <motion.div initial={HERO_INIT} animate={HERO_ANIM} transition={HERO_TRANS}>
      <GlassCard glow={glowFor(moderator.recommendation)} testId="recommendation-card">
        <div className="grid lg:grid-cols-3 gap-8 items-center">
          <div className="lg:col-span-2">
            <div className="label-eyebrow mb-3">// final verdict</div>
            <div className="flex items-center gap-4 mb-5">
              <span
                data-testid="verdict-badge"
                className={`px-5 py-2 rounded-full text-sm font-mono tracking-widest ${verdictClass(moderator.recommendation)}`}
              >
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
              {(moderator.key_reasons || []).map((r) => (
                <li key={r} className="flex gap-3 text-sm text-[var(--text-dim)]">
                  <span className="text-[var(--accent)] font-mono mt-0.5">→</span>{r}
                </li>
              ))}
            </ul>
          </div>
          <div className="space-y-4">
            <Gauge value={moderator.confidence_score || 0} />
            <div className="grid grid-cols-2 gap-3">
              <Stat label="Upside"   value={`${moderator.expected_upside_pct ?? "—"}%`} good />
              <Stat label="Downside" value={`${moderator.expected_downside_pct ?? "—"}%`} bad />
            </div>
          </div>
        </div>
      </GlassCard>
    </motion.div>
  );
}
