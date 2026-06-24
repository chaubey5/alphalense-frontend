// Number/text formatting helpers used across the dashboard.

export function fmtNum(n, opts = {}) {
  if (n === null || n === undefined || Number.isNaN(Number(n))) return "—";
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

export function verdictClass(v) {
  if (v === "INVEST") return "verdict-invest";
  if (v === "PASS")   return "verdict-pass";
  return "verdict-hold";
}

export function gaugeColor(v) {
  if (v > 70) return "var(--accent)";
  if (v > 45) return "var(--gold)";
  return "var(--danger)";
}

export function convictionText(v) {
  if (v > 70) return "High conviction.";
  if (v > 45) return "Moderate conviction.";
  return "Low conviction — proceed with care.";
}
