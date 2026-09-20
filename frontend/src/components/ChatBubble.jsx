import { Bot, User } from "lucide-react";
import Markdown from "./Markdown";

export default function ChatBubble({ role, content, sources }) {
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
          ${isUser ? "bg-violet text-white rounded-[20px_20px_4px_20px] whitespace-pre-wrap" : "bg-white text-fg rounded-[20px_20px_20px_4px]"}`}
      >
        {isUser ? content : <Markdown>{content}</Markdown>}
        {sources && sources.length > 0 && (
          <div className="mt-3 pt-3 border-t border-border/60 flex flex-wrap gap-2">
            {sources.map((_, i) => (
              <span key={i} className="px-2.5 py-1 rounded-pill bg-muted text-xs font-semibold text-muted-fg">
                Source {i + 1}
              </span>
            ))}
          </div>
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
