import { ThumbsDown, ThumbsUp } from "lucide-react";
import GlassCard from "@/components/GlassCard";
import Skeleton from "@/components/dashboard/Skeleton";

function ThesisList({ items, sign, accentClass }) {
  return (
    <>
      {items.map((point, idx) => (
        <li key={point} className="flex gap-3 text-sm">
          <span className={`${accentClass} font-mono`}>
            {sign}{(idx + 1).toString().padStart(2, "0")}
          </span>
          <span className="text-[var(--text-dim)]">{point}</span>
        </li>
      ))}
    </>
  );
}

function TagRow({ label, items, accentClass, borderClass }) {
  if (!items?.length) return null;
  return (
    <li className="pt-3 border-t border-[var(--border)]">
      <div className="label-eyebrow mb-2">{label}</div>
      <div className="flex flex-wrap gap-2">
        {items.map((c) => (
          <span key={c}
            className={`text-xs px-3 py-1 rounded-full ${accentClass} ${borderClass}`}>
            {c}
          </span>
        ))}
      </div>
    </li>
  );
}

export function BullCard({ bull }) {
  return (
    <GlassCard glow="glow-mint" testId="bull-card">
      <div className="flex items-center gap-3 mb-4">
        <ThumbsUp className="w-5 h-5 text-[var(--accent)]" />
        <div className="label-eyebrow">// bull case</div>
      </div>
      <h3 className="font-serif text-2xl mb-4 italic">Why you&apos;d buy this</h3>
      {bull ? (
        <ul className="space-y-3">
          <ThesisList items={bull.thesis_points || []} sign="+" accentClass="text-[var(--accent)]" />
          <TagRow label="Catalysts" items={bull.catalysts}
                  accentClass="bg-[var(--accent)]/10 text-[var(--accent)]"
                  borderClass="border border-[var(--accent)]/30" />
        </ul>
      ) : <Skeleton lines={5} />}
    </GlassCard>
  );
}

export function BearCard({ bear }) {
  return (
    <GlassCard glow="glow-orange" testId="bear-card">
      <div className="flex items-center gap-3 mb-4">
        <ThumbsDown className="w-5 h-5 text-[var(--danger)]" />
        <div className="label-eyebrow">// bear case</div>
      </div>
      <h3 className="font-serif text-2xl mb-4 italic">Why you&apos;d pass</h3>
      {bear ? (
        <ul className="space-y-3">
          <ThesisList items={bear.thesis_points || []} sign="-" accentClass="text-[var(--danger)]" />
          <TagRow label="Risks" items={bear.risks}
                  accentClass="bg-[var(--danger)]/10 text-[var(--danger)]"
                  borderClass="border border-[var(--danger)]/30" />
        </ul>
      ) : <Skeleton lines={5} />}
    </GlassCard>
  );
}
