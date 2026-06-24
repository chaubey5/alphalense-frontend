import { CheckCircle2, Circle, Loader2 } from "lucide-react";
import GlassCard from "@/components/GlassCard";
import { AGENT_META, AGENT_ORDER, agentStatusText } from "@/lib/agents";

function StatusIcon({ status }) {
  if (status === "done")    return <CheckCircle2 className="w-4 h-4 text-[var(--accent)]" />;
  if (status === "running") return <Loader2 className="w-4 h-4 animate-spin text-[var(--accent-3)]" />;
  return <Circle className="w-4 h-4 text-[var(--text-faint)]" />;
}

function AgentPill({ agentKey, status }) {
  const meta = AGENT_META[agentKey];
  const Icon = meta.icon;
  return (
    <div
      data-testid={`agent-status-${agentKey}`}
      className="glass-strong glass p-3 rounded-xl flex items-center gap-3"
    >
      <div
        className="w-9 h-9 rounded-lg flex items-center justify-center"
        style={{ background: `${meta.color}1A`, color: meta.color }}
      >
        <Icon className="w-4 h-4" />
      </div>
      <div className="flex-1 min-w-0">
        <div className="text-sm">{meta.label}</div>
        <div className="text-[10px] font-mono uppercase tracking-widest text-[var(--text-faint)]">
          {agentStatusText(status)}
        </div>
      </div>
      <StatusIcon status={status} />
    </div>
  );
}

export default function AgentPipelineStrip({ status }) {
  return (
    <GlassCard testId="agent-pipeline" eyebrow="// agent pipeline" title="Live reasoning">
      <div className="grid grid-cols-2 md:grid-cols-7 gap-3">
        {AGENT_ORDER.map((key) => (
          <AgentPill key={key} agentKey={key} status={status[key]} />
        ))}
      </div>
    </GlassCard>
  );
}
