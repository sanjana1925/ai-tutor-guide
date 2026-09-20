import { DecoSquiggle } from "./DecorativeShapes";

export default function SectionHeader({ eyebrow, title, subtitle }) {
  return (
    <div className="relative mb-8 pt-2">
      {eyebrow && (
        <span className="inline-flex items-center gap-1.5 px-3 py-1 rounded-pill border-2 border-ink bg-white text-xs font-bold uppercase tracking-wide mb-3">
          {eyebrow}
        </span>
      )}
      {title && (
        <div className="relative inline-block">
          <h2 className="font-heading text-3xl sm:text-4xl font-extrabold">{title}</h2>
          <DecoSquiggle color="#1E293B" className="hidden sm:block" style={{ left: "2px", top: "100%" }} />
        </div>
      )}
      {subtitle && <p className={`text-muted-fg max-w-xl ${title ? "mt-7" : ""}`}>{subtitle}</p>}
    </div>
  );
}
