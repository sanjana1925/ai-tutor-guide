import { useState } from "react";
import { Bot, User, RotateCcw } from "lucide-react";
import Markdown from "./Markdown";

function SourcePills({ sources }) {
  const [open, setOpen] = useState(null);
  return (
    <div className="mt-3 pt-3 border-t border-border/60">
      <div className="flex flex-wrap gap-2">
        {sources.map((_, i) => (
          <button
            key={i}
            type="button"
            aria-expanded={open === i}
            onClick={() => setOpen(open === i ? null : i)}
            className={`px-2.5 py-1 rounded-pill border text-xs font-semibold min-h-[28px] transition-colors
              ${open === i ? "bg-violet text-white border-ink" : "bg-muted text-muted-fg border-transparent hover:border-ink"}`}
          >
            Source {i + 1}
          </button>
        ))}
      </div>
      {open !== null && (
        <blockquote className="mt-3 p-3 rounded-md bg-muted border-l-4 border-violet text-sm text-fg whitespace-pre-wrap">
          {sources[open]}
        </blockquote>
      )}
    </div>
  );
}

export default function ChatBubble({ role, content, sources, isError, onRetry }) {
  const isUser = role === "user";
  return (
    <div className={`flex items-end gap-3 ${isUser ? "justify-end" : "justify-start"}`}>
      {!isUser && (
        <span className="w-9 h-9 rounded-full bg-violet/15 border-2 border-ink grid place-items-center shrink-0">
          <Bot size={18} strokeWidth={2.5} className="text-violet" />
        </span>
      )}
      <div
        className={`max-w-[85%] sm:max-w-[75%] px-5 py-3.5 border-2 border-ink shadow-sm break-words font-body leading-relaxed
          ${isUser ? "bg-violet text-white rounded-[20px_20px_4px_20px] whitespace-pre-wrap" : "bg-white text-fg rounded-[20px_20px_20px_4px]"}
          ${isError ? "border-pink" : ""}`}
      >
        {isUser ? content : <Markdown>{content}</Markdown>}
        {sources && sources.length > 0 && <SourcePills sources={sources} />}
        {isError && onRetry && (
          <button
            type="button"
            onClick={onRetry}
            className="mt-3 inline-flex items-center gap-1.5 px-4 py-2 min-h-[40px] rounded-pill border-2 border-ink bg-amber font-heading font-bold text-sm tactile"
          >
            <RotateCcw size={16} strokeWidth={2.5} /> Retry
          </button>
        )}
      </div>
      {isUser && (
        <span className="w-9 h-9 rounded-full bg-pink/15 border-2 border-ink grid place-items-center shrink-0">
          <User size={18} strokeWidth={2.5} className="text-pink" />
        </span>
      )}
    </div>
  );
}
