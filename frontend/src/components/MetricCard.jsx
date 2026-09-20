import StickerCard from "./StickerCard";

export default function MetricCard({ icon: Icon, label, value, sub, color = "#8B5CF6" }) {
  return (
    <StickerCard rotateOnHover className="p-5 flex flex-col gap-3">
      <div
        className="w-12 h-12 rounded-md border-2 border-ink grid place-items-center"
        style={{ background: `${color}33` }}
      >
        <Icon size={22} strokeWidth={2.5} style={{ color }} />
      </div>
      <div>
        <p className="text-sm font-semibold text-muted-fg">{label}</p>
        <p className="font-heading text-3xl font-extrabold leading-tight">{value}</p>
        {sub && <p className="text-xs text-muted-fg mt-1">{sub}</p>}
      </div>
    </StickerCard>
  );
}
