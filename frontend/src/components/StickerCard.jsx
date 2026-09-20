export default function StickerCard({ children, className = "", rotateOnHover = false, as: Tag = "div", ...props }) {
  return (
    <Tag
      className={`bg-card border-2 border-ink rounded-lg shadow-card tactile
        ${rotateOnHover ? "hover:scale-[1.02] hover:-rotate-1" : "hover:-translate-y-0.5"}
        ${className}`}
      {...props}
    >
      {children}
    </Tag>
  );
}
