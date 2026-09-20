import { useEffect, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import { FileText, KeyRound, Sparkles, BookOpen, Brain, Send, MessageCircleQuestion } from "lucide-react";
import Shell from "../components/Shell";
import ChatBubble from "../components/ChatBubble";
import { Pill } from "../components/Button";
import EmptyState from "../components/EmptyState";
import { useApp } from "../store";
import { fetchChatHistory, sendAgentMessage } from "../lib/api";

const QUICK_ACTIONS = [
  { mode: "summary", label: "Summarize", icon: FileText },
  { mode: "key_points", label: "Key Points", icon: KeyRound },
  { mode: "eli5", label: "Explain Simply", icon: Sparkles },
  { mode: "glossary", label: "Glossary", icon: BookOpen },
];

const SLOW_AFTER_SECONDS = 15;

function useElapsedSeconds(active) {
  const [seconds, setSeconds] = useState(0);
  useEffect(() => {
    if (!active) {
      setSeconds(0);
      return undefined;
    }
    const started = Date.now();
    const id = setInterval(() => setSeconds(Math.floor((Date.now() - started) / 1000)), 1000);
    return () => clearInterval(id);
  }, [active]);
  return seconds;
}

export default function TutorPage() {
  const { currentDocument, sessionId, documents, addMessage, removeLastMessage, setMessages } = useApp();
  const navigate = useNavigate();
  const messages = currentDocument ? documents[currentDocument] || [] : [];
  const [input, setInput] = useState("");
  const [busy, setBusy] = useState(false);
  const [lastRequest, setLastRequest] = useState(null);
  const scrollRef = useRef(null);
  const elapsed = useElapsedSeconds(busy);

  useEffect(() => {
    scrollRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, busy]);

  // The server keeps the full conversation: when a document is opened, show that copy.
  useEffect(() => {
    if (!currentDocument) return undefined;
    let cancelled = false;
    fetchChatHistory(currentDocument, sessionId)
      .then((data) => {
        if (cancelled || !data.messages || data.messages.length === 0) return;
        setMessages(
          currentDocument,
          data.messages
            .filter((m) => m.role === "user" || m.role === "assistant")
            .map((m) => {
              const excerpts = (m.sources || []).flatMap((s) => s.excerpts || []);
              return { role: m.role, content: m.content, ...(excerpts.length ? { sources: excerpts } : {}) };
            })
        );
      })
      .catch(() => {
        /* offline or first visit: keep the copy saved in this browser */
      });
    return () => {
      cancelled = true;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [currentDocument, sessionId]);

  async function send(request, { addUser = true } = {}) {
    if (!currentDocument || busy) return;
    const history = messages.slice(-6).map(({ role, content }) => ({ role, content }));
    setLastRequest(request);
    if (addUser) addMessage(currentDocument, { role: "user", content: request.display });
    setBusy(true);
    try {
      const resp = await sendAgentMessage({
        message: request.message,
        filename: currentDocument,
        sessionId,
        mode: request.mode || "",
        history: request.mode ? [] : history,
      });
      addMessage(currentDocument, { role: "assistant", content: resp.reply, sources: resp.retrieved_chunks });
      setLastRequest(null);
    } catch (err) {
      addMessage(currentDocument, { role: "assistant", content: `Error: ${err.message}`, isError: true });
    } finally {
      setBusy(false);
    }
  }

  function runMode(mode, label) {
    send({ message: label, mode, display: `${label} — ${currentDocument}` });
  }

  function handleSend(e) {
    e.preventDefault();
    const question = input.trim();
    if (!question || !currentDocument || busy) return;
    setInput("");
    send({ message: question, display: question });
  }

  function retry() {
    if (!lastRequest || busy) return;
    removeLastMessage(currentDocument);
    send(lastRequest, { addUser: false });
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
              messages.map((msg, i) => (
                <ChatBubble
                  key={i}
                  role={msg.role}
                  content={msg.content}
                  sources={msg.sources}
                  isError={msg.isError}
                  onRetry={msg.isError && i === messages.length - 1 && !busy ? retry : undefined}
                />
              ))
            )}
            {busy && (
              <ChatBubble
                role="assistant"
                content={
                  elapsed >= SLOW_AFTER_SECONDS
                    ? `Still working (${elapsed}s). This is taking longer than usual, and the AI service may be busy. You can keep waiting, or try again in a moment.`
                    : "Thinking…"
                }
              />
            )}
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
