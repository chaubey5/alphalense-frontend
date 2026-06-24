export default function Stat({ label, value, small, good, bad }) {
  let tone = "";
  if (good) tone = "text-[var(--accent)]";
  else if (bad) tone = "text-[var(--danger)]";
  return (
    <div>
      <div className="label-eyebrow mb-1">{label}</div>
      <div className={`${small ? "text-sm" : "text-xl"} font-medium ${tone}`}>
        {value ?? "—"}
      </div>
    </div>
  );
}
