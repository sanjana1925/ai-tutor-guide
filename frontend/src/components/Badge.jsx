import { CheckCircle2, TrendingUp, AlertTriangle } from "lucide-react";

// Accuracy thresholds mirror the backend's own weak (<60%) / strong (>=70%) split
// (see quiz_engine.py WEAK_TOPIC_THRESHOLD / get_strong_topics) — this only decides
// how to *label* numbers the API already returns, it doesn't compute new ones.
export function statusFromAccuracy(accuracy) {
  if (accuracy >= 70) return "strong";
  if (accuracy >= 60) return "improving";
  return "needs-practice";
}

const STYLES = {
  strong: { icon: CheckCircle2, label: "Strong", classes: "bg-emerald/15 text-emerald border-emerald" },
  improving: { icon: TrendingUp, label: "Improving", classes: "bg-amber/15 text-amber-900 border-amber" },
  "needs-practice": { icon: AlertTriangle, label: "Needs Practice", classes: "bg-pink/15 text-pink border-pink" },
};

export default function StatusBadge({ status, className = "" }) {
  const s = STYLES[status] || STYLES.improving;
  const Icon = s.icon;
  return (
    <span
      className={`inline-flex items-center gap-1.5 px-3 py-1 rounded-pill border-2 font-body font-bold text-xs uppercase tracking-wide ${s.classes} ${className}`}
    >
      <Icon size={14} strokeWidth={2.5} />
      {s.label}
    </span>
  );
}
