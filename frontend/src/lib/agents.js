import {
  Activity, Building2, Scale, Globe2, ThumbsUp, ThumbsDown, Gavel,
} from "lucide-react";

export const AGENT_META = {
  research:  { label: "Research",  icon: Building2, color: "var(--accent-3)" },
  financial: { label: "Financial", icon: Activity,  color: "var(--accent)" },
  valuation: { label: "Valuation", icon: Scale,     color: "var(--gold)" },
  macro:     { label: "Macro",     icon: Globe2,    color: "#b39ddb" },
  bull:      { label: "Bull",      icon: ThumbsUp,  color: "var(--accent)" },
  bear:      { label: "Bear",      icon: ThumbsDown,color: "var(--danger)" },
  moderator: { label: "Moderator", icon: Gavel,     color: "var(--accent-2)" },
};

export const AGENT_ORDER = ["research", "financial", "valuation", "macro", "bull", "bear", "moderator"];

export const AGENT_LABELS = Object.fromEntries(
  Object.entries(AGENT_META).map(([k, v]) => [k, v.label]),
);

// Status helpers — readable replacement for nested ternaries.
export function agentStatusText(status) {
  if (status === "done") return "complete";
  if (status === "running") return "thinking…";
  return "queued";
}
