import { useEffect, useState, useCallback } from "react";
import { Target, ListChecks, CheckCircle2, Trophy, Sparkles } from "lucide-react";
import Shell from "../components/Shell";
import SectionHeader from "../components/SectionHeader";
import MetricCard from "../components/MetricCard";
import StickerCard from "../components/StickerCard";
import ProgressBar from "../components/ProgressBar";
import StatusBadge, { statusFromAccuracy } from "../components/Badge";
import EmptyState from "../components/EmptyState";
import { useApp } from "../store";
import { fetchDashboard } from "../lib/api";

const DIFFICULTIES = [
  { key: "simple_accuracy", label: "Simple", color: "#8B5CF6" },
  { key: "medium_accuracy", label: "Medium", color: "#F472B6" },
  { key: "high_accuracy", label: "High", color: "#FBBF24" },
];

export default function DashboardPage() {
  const { currentDocument, sessionId } = useApp();
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  const load = useCallback(() => {
    if (!currentDocument) return;
    setLoading(true);
    setError("");
    fetchDashboard(currentDocument, sessionId)
      .then(setData)
      .catch((err) => setError(err.message || "Could not load dashboard data"))
      .finally(() => setLoading(false));
  }, [currentDocument, sessionId]);

  useEffect(load, [load]);

  return (
    <Shell title="Dashboard">
      <SectionHeader
        title="Welcome Aboard to Your Learning Forum"
        subtitle="See your progress, performance, and what to learn next."
      />

      {!currentDocument && (
        <EmptyState
          icon={Target}
          title="No document yet"
          body="Upload a study PDF to start your first quiz and see progress here."
        />
      )}

      {currentDocument && loading && <p className="text-muted-fg">Loading dashboard…</p>}
      {currentDocument && error && <p className="text-pink font-semibold">{error}</p>}

      {currentDocument && data && (data.status === "no_data" || data.total_attempted === 0) && (
        <EmptyState
          icon={Sparkles}
          title="Start learning to see your progress here"
          body="Take an adaptive quiz to populate performance metrics for this document."
        />
      )}

      {currentDocument && data && data.status !== "no_data" && data.total_attempted > 0 && (
        <>
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-5 mb-10">
            <MetricCard icon={Target} label="Overall Accuracy" value={`${data.overall_accuracy}%`} color="#8B5CF6" />
            <MetricCard icon={ListChecks} label="Questions Attempted" value={data.total_attempted} color="#F472B6" />
            <MetricCard icon={CheckCircle2} label="Questions Correct" value={data.total_correct} color="#34D399" />
            <MetricCard
              icon={Trophy}
              label="Topics Mastered"
              value={(data.strong_topics || []).length}
              sub={`Current phase: ${data.current_phase}`}
              color="#FBBF24"
            />
          </div>

          <section className="mb-10">
            <h3 className="font-heading text-xl font-extrabold mb-4">Difficulty Performance</h3>
            <div className="grid grid-cols-1 sm:grid-cols-3 gap-5">
              {DIFFICULTIES.map(({ key, label, color }) => (
                <StickerCard key={key} className="p-5">
                  <div className="flex items-center justify-between mb-3">
                    <span
                      className="px-3 py-1 rounded-pill border-2 border-ink text-xs font-bold uppercase"
                      style={{ background: `${color}33` }}
                    >
                      {label}
                    </span>
                    {data.current_phase?.toLowerCase() === label.toLowerCase() && (
                      <span className="text-xs font-bold text-muted-fg">Current</span>
                    )}
                  </div>
                  <p className="font-heading text-3xl font-extrabold mb-3">{data[key]}%</p>
                  <ProgressBar percent={data[key]} color={color} label={`${label} accuracy`} />
                </StickerCard>
              ))}
            </div>
          </section>

          <section className="mb-10">
            <h3 className="font-heading text-xl font-extrabold mb-4">Learning Progress</h3>
            <StickerCard className="p-6 relative overflow-hidden diagonal-stripes">
              <p className="text-xs font-bold uppercase tracking-wide text-muted-fg mb-1">Current Phase</p>
              <p className="font-heading text-3xl font-extrabold mb-4">{data.current_phase}</p>
              <ProgressBar percent={data.overall_accuracy} label="Overall accuracy progress" />
              <div className="flex flex-wrap gap-6 mt-4 text-sm font-semibold">
                <span>{data.total_attempted} questions completed</span>
                <span>{Object.keys(data.topic_stats || {}).length} topics covered</span>
              </div>
            </StickerCard>
          </section>

          <section className="mb-10">
            <h3 className="font-heading text-xl font-extrabold mb-4">Topic Performance</h3>
            {Object.keys(data.topic_stats || {}).length === 0 ? (
              <p className="text-muted-fg">No topic data yet.</p>
            ) : (
              <StickerCard className="overflow-x-auto">
                <table className="w-full text-left border-collapse min-w-[520px]">
                  <thead>
                    <tr className="border-b-2 border-ink text-xs uppercase font-bold text-muted-fg">
                      <th className="px-4 py-3">Topic</th>
                      <th className="px-4 py-3">Questions</th>
                      <th className="px-4 py-3">Accuracy</th>
                      <th className="px-4 py-3">Status</th>
                    </tr>
                  </thead>
                  <tbody>
                    {Object.entries(data.topic_stats).map(([topic, stats]) => (
                      <tr key={topic} className="border-b border-border last:border-0">
                        <td className="px-4 py-3 font-semibold">{topic}</td>
                        <td className="px-4 py-3">{stats.attempts}</td>
                        <td className="px-4 py-3">{stats.accuracy.toFixed(1)}%</td>
                        <td className="px-4 py-3">
                          <StatusBadge status={statusFromAccuracy(stats.accuracy)} />
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </StickerCard>
            )}
          </section>
        </>
      )}
    </Shell>
  );
}
