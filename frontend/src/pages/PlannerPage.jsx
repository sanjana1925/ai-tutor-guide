import { useEffect, useState, useCallback } from "react";
import { CalendarCheck, Clock, ArrowRight } from "lucide-react";
import Shell from "../components/Shell";
import SectionHeader from "../components/SectionHeader";
import Markdown from "../components/Markdown";
import StickerCard from "../components/StickerCard";
import EmptyState from "../components/EmptyState";
import { useApp } from "../store";
import { fetchPlanner } from "../lib/api";

const PRIORITY_STYLES = {
  High: "bg-pink/15 text-pink border-pink",
  Medium: "bg-amber/15 text-amber-900 border-amber",
  Low: "bg-emerald/15 text-emerald border-emerald",
};

export default function PlannerPage() {
  const { currentDocument, sessionId } = useApp();
  const [plan, setPlan] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  const load = useCallback(() => {
    if (!currentDocument) return;
    setLoading(true);
    setError("");
    fetchPlanner(currentDocument, sessionId)
      .then(setPlan)
      .catch((err) => setError(err.message || "Could not load study plan"))
      .finally(() => setLoading(false));
  }, [currentDocument, sessionId]);

  useEffect(load, [load]);

  return (
    <Shell title="Study Planner">
      <SectionHeader
        subtitle="A simple plan to help you learn what matters next."
      />

      {!currentDocument && (
        <EmptyState
          icon={CalendarCheck}
          title="Complete some learning activities to build your study plan"
          body="Upload a document and take a quiz to unlock personalized recommendations."
        />
      )}

      {currentDocument && loading && <p className="text-muted-fg">Loading study plan…</p>}
      {currentDocument && error && <p className="text-pink font-semibold">{error}</p>}

      {currentDocument && plan && (
        <>
          <StickerCard className="p-5 mb-8 bg-amber/10">
            <Markdown className="font-body font-semibold">{plan.general_summary}</Markdown>
          </StickerCard>

          <div className="flex flex-col gap-4">
            {plan.items.map((item, idx) => (
              <StickerCard key={`${item.topic}-${idx}`} className="p-6 flex flex-col sm:flex-row gap-5">
                <span className="font-heading text-3xl font-extrabold text-border shrink-0">
                  {String(idx + 1).padStart(2, "0")}
                </span>
                <div className="flex-1">
                  <div className="flex flex-wrap items-center gap-2 mb-2">
                    <h3 className="font-heading text-lg font-extrabold">{item.topic}</h3>
                    <span
                      className={`px-3 py-1 rounded-pill border-2 text-xs font-bold uppercase ${
                        PRIORITY_STYLES[item.priority] || PRIORITY_STYLES.Medium
                      }`}
                    >
                      {item.priority} priority
                    </span>
                    <span className="text-xs text-muted-fg font-semibold">Accuracy: {item.accuracy}</span>
                  </div>
                  <p className="text-fg mb-1">{item.recommendation}</p>
                  <p className="text-sm text-muted-fg italic mb-3">{item.reason}</p>
                  <div className="flex items-center gap-2 text-sm font-semibold">
                    <Clock size={16} strokeWidth={2.5} />
                    {item.estimated_study_time}
                  </div>
                </div>
                <ArrowRight size={20} strokeWidth={2.5} className="hidden sm:block self-center text-muted-fg" />
              </StickerCard>
            ))}
          </div>
        </>
      )}
    </Shell>
  );
}
