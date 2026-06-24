export default function Skeleton({ lines = 4 }) {
  return (
    <div className="space-y-2">
      {Array.from({ length: lines }).map((_, idx) => (
        <div
          key={`sk-${idx}`}
          className="h-3 rounded shimmer"
          style={{ width: `${60 + ((idx * 13) % 35)}%` }}
        />
      ))}
    </div>
  );
}
