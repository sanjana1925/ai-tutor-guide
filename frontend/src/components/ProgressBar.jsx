export default function ProgressBar({ percent, color = "#8B5CF6", height = 14, label }) {
  const clamped = Math.max(0, Math.min(100, percent || 0));
  return (
    <div>
      <div
        className="w-full border-2 border-ink rounded-pill overflow-hidden bg-white"
        style={{ height }}
        role="progressbar"
        aria-valuenow={Math.round(clamped)}
        aria-valuemin={0}
        aria-valuemax={100}
        aria-label={label}
      >
        <div className="h-full grow-bar rounded-pill" style={{ width: `${clamped}%`, background: color }} />
      </div>
    </div>
  );
}
