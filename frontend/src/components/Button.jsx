export function PrimaryButton({ children, className = "", icon: Icon, disabled, ...props }) {
  return (
    <button
      disabled={disabled}
      className={`inline-flex items-center justify-center gap-2 min-h-[48px] px-6 py-2.5 rounded-pill
        bg-violet text-white font-heading font-bold border-2 border-ink shadow-std
        tactile hover:-translate-x-0.5 hover:-translate-y-0.5 hover:shadow-hover
        active:translate-x-0.5 active:translate-y-0.5 active:shadow-active
        disabled:opacity-50 disabled:cursor-not-allowed disabled:hover:translate-x-0 disabled:hover:translate-y-0 disabled:hover:shadow-std
        ${className}`}
      {...props}
    >
      {Icon && <Icon size={18} strokeWidth={2.5} />}
      {children}
    </button>
  );
}

export function SecondaryButton({ children, className = "", icon: Icon, ...props }) {
  return (
    <button
      className={`inline-flex items-center justify-center gap-2 min-h-[48px] px-6 py-2.5 rounded-pill
        bg-transparent text-fg font-heading font-bold border-2 border-ink
        tactile hover:bg-amber
        ${className}`}
      {...props}
    >
      {Icon && <Icon size={18} strokeWidth={2.5} />}
      {children}
    </button>
  );
}

export function Pill({ children, className = "", icon: Icon, active = false, ...props }) {
  return (
    <button
      className={`inline-flex items-center gap-1.5 px-4 py-2 rounded-pill border-2 border-ink font-body font-semibold text-sm
        tactile hover:-translate-y-0.5
        ${active ? "bg-violet text-white shadow-sm" : "bg-white text-fg hover:bg-amber/40"}
        ${className}`}
      {...props}
    >
      {Icon && <Icon size={15} strokeWidth={2.5} />}
      {children}
    </button>
  );
}
