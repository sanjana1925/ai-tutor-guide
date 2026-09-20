import { DecoStar } from "./DecorativeShapes";

export default function EmptyState({ icon: Icon, title, body, actions, className = "" }) {
  return (
    <div className={`relative text-center py-16 px-6 ${className}`}>
      <DecoStar className="hidden sm:block" color="#8B5CF6" size={28} style={{ right: "28%", bottom: "8%" }} />

      <div className="relative z-10 flex flex-col items-center gap-4">
        {Icon && (
          <div className="w-16 h-16 rounded-lg bg-violet/10 border-2 border-ink grid place-items-center shadow-std">
            <Icon size={30} strokeWidth={2.5} className="text-violet" />
          </div>
        )}
        <h3 className="font-heading text-2xl font-extrabold text-fg">{title}</h3>
        <p className="max-w-md text-muted-fg font-body">{body}</p>
        {actions && <div className="flex flex-wrap items-center justify-center gap-3 mt-2">{actions}</div>}
      </div>
    </div>
  );
}
