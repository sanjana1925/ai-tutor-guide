import { useEffect, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import { FileText, KeyRound, Sparkles, BookOpen, Brain, Send, MessageCircleQuestion } from "lucide-react";
import Shell from "../components/Shell";
import ChatBubble from "../components/ChatBubble";
import { Pill } from "../components/Button";
import EmptyState from "../components/EmptyState";
import { useApp } from "../store";
import { sendAgentMessage } from "../lib/api";

const QUICK_ACTIONS = [
  { mode: "summary", label: "Summarize", icon: FileText },
  { mode: "key_points", label: "Key Points", icon: KeyRound },
  { mode: "eli5", label: "Explain Simply", icon: Sparkles },
  { mode: "glossary", label: "Glossary", icon: BookOpen },
];

export default function TutorPage() {
  const { currentDocument, sessionId, documents, addMessage } = useApp();
  const navigate = useNavigate();
  const messages = currentDocument ? documents[currentDocument] || [] : [];
  const [input, setInput] = useState("");
  const [busy, setBusy] = useState(false);
  const scrollRef = useRef(null);

  useEffect(() => {
    scrollRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, busy]);

  async function runMode(mode, label) {
    if (!currentDocument || busy) return;
    setBusy(true);
    addMessage(currentDocument, { role: "user", content: `${label} — ${currentDocument}` });
    try {
      const resp = await sendAgentMessage({ message: label, filename: currentDocument, sessionId, mode });
      addMessage(currentDocument, { role: "assistant", content: resp.reply });
    } catch (err) {
      addMessage(currentDocument, { role: "assistant", content: `Error: ${err.message}` });
    } finally {
      setBusy(false);
    }
  }

  async function handleSend(e) {
    e.preventDefault();
    const question = input.trim();
    if (!question || !currentDocument || busy) return;
    const history = messages.slice(-6);
    setInput("");
    addMessage(currentDocument, { role: "user", content: question });
    setBusy(true);
    try {
      const resp = await sendAgentMessage({ message: question, filename: currentDocument, sessionId, history });
      addMessage(currentDocument, { role: "assistant", content: resp.reply, sources: resp.retrieved_chunks });
    } catch (err) {
      addMessage(currentDocument, { role: "assistant", content: `Error: ${err.message}` });
    } finally {
      setBusy(false);
    }
  }

  return (
    <Shell title="AI Tutor">
      {!currentDocument ? (
        <EmptyState
          icon={Brain}
          title="Upload a document to start chatting"
          body="Once you index a PDF, your tutor can summarize it, explain it simply, or answer questions."
        />
      ) : (
        <div className="flex flex-col h-[calc(100vh-140px)]">
          <div className="flex flex-wrap gap-2 mb-4">
            {QUICK_ACTIONS.map(({ mode, label, icon }) => (
              <Pill key={mode} icon={icon} disabled={busy} onClick={() => runMode(mode, label)}>
                {label}
              </Pill>
            ))}
            <Pill icon={Brain} onClick={() => navigate("/quiz")}>
              Quiz Me
            </Pill>
          </div>

          <div className="flex-1 overflow-y-auto rounded-lg border-2 border-ink bg-white/40 p-4 sm:p-6 flex flex-col gap-4">
            {messages.length === 0 ? (
              <EmptyState
                icon={MessageCircleQuestion}
                title="Ready to learn?"
                body={`Ask me anything about ${currentDocument}.`}
                actions={
                  <>
                    <Pill icon={Sparkles} onClick={() => runMode("eli5", "Explain Simply")}>
                      Explain a Topic
                    </Pill>
                    <Pill icon={FileText} onClick={() => runMode("summary", "Summarize")}>
                      Summarize Document
                    </Pill>
                  </>
                }
              />
            ) : (
              messages.map((msg, i) => <ChatBubble key={i} role={msg.role} content={msg.content} sources={msg.sources} />)
            )}
            {busy && <ChatBubble role="assistant" content="Thinking…" />}
            <div ref={scrollRef} />
          </div>

          <form onSubmit={handleSend} className="mt-4 flex items-center gap-3">
            <input
              className="flex-1 min-h-[52px] px-5 rounded-md border-2 border-[#CBD5E1] bg-input font-body
                focus:border-focus focus:shadow-std-violet outline-none"
              placeholder={`Ask your tutor about ${currentDocument}…`}
              value={input}
              onChange={(e) => setInput(e.target.value)}
              disabled={busy}
            />
            <button
              type="submit"
              disabled={busy || !input.trim()}
              className="min-h-[52px] px-5 rounded-pill bg-violet text-white border-2 border-ink shadow-std
                tactile hover:-translate-y-0.5 hover:shadow-hover disabled:opacity-50"
              aria-label="Send message"
            >
              <Send size={20} strokeWidth={2.5} />
            </button>
          </form>
        </div>
      )}
    </Shell>
  );
}
