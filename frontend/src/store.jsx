import { createContext, useContext, useEffect, useMemo, useState, useCallback } from "react";
import { uploadDocument, deleteDocument } from "./lib/api";

const AppContext = createContext(null);

function getSessionId() {
  let sid = localStorage.getItem("tg_session_id");
  if (!sid) {
    sid = crypto.randomUUID();
    localStorage.setItem("tg_session_id", sid);
  }
  return sid;
}

function loadState(sessionId) {
  try {
    const raw = localStorage.getItem(`tg_state_${sessionId}`);
    if (raw) return JSON.parse(raw);
  } catch {
    /* corrupt local state, fall through to default */
  }
  return { documents: {}, currentDocument: null };
}

export function AppProvider({ children }) {
  const [sessionId] = useState(getSessionId);
  const [documents, setDocuments] = useState(() => loadState(getSessionId()).documents);
  const [currentDocument, setCurrentDocument] = useState(() => loadState(getSessionId()).currentDocument);
  const [uploading, setUploading] = useState(false);
  const [uploadError, setUploadError] = useState("");

  useEffect(() => {
    localStorage.setItem(`tg_state_${sessionId}`, JSON.stringify({ documents, currentDocument }));
  }, [sessionId, documents, currentDocument]);

  const addMessage = useCallback((filename, message) => {
    setDocuments((prev) => {
      const existing = prev[filename] || [];
      return { ...prev, [filename]: [...existing, message] };
    });
  }, []);

  const removeLastMessage = useCallback((filename) => {
    setDocuments((prev) => ({ ...prev, [filename]: (prev[filename] || []).slice(0, -1) }));
  }, []);

  const setMessages = useCallback((filename, messages) => {
    setDocuments((prev) => ({ ...prev, [filename]: messages }));
  }, []);

  const upload = useCallback(
    async (file) => {
      setUploading(true);
      setUploadError("");
      try {
        const data = await uploadDocument(file, sessionId);
        setDocuments((prev) => ({ ...prev, [data.filename]: prev[data.filename] || [] }));
        setCurrentDocument(data.filename);
        return data;
      } catch (err) {
        setUploadError(err.message || "Upload failed");
        throw err;
      } finally {
        setUploading(false);
      }
    },
    [sessionId]
  );

  const removeCurrentDocument = useCallback(async () => {
    if (!currentDocument) return;
    const target = currentDocument;
    try {
      await deleteDocument(target, sessionId);
    } catch {
      /* best-effort: still clear it locally even if the API call failed */
    }
    setDocuments((prev) => {
      const next = { ...prev };
      delete next[target];
      return next;
    });
    setCurrentDocument((prevDoc) => {
      if (prevDoc !== target) return prevDoc;
      const remaining = Object.keys(documents).filter((d) => d !== target);
      return remaining[0] || null;
    });
  }, [currentDocument, sessionId, documents]);

  const value = useMemo(
    () => ({
      sessionId,
      documents,
      currentDocument,
      setCurrentDocument,
      addMessage,
      removeLastMessage,
      setMessages,
      upload,
      uploading,
      uploadError,
      removeCurrentDocument,
      documentNames: Object.keys(documents),
    }),
    [sessionId, documents, currentDocument, addMessage, removeLastMessage, setMessages, upload, uploading, uploadError, removeCurrentDocument]
  );

  return <AppContext.Provider value={value}>{children}</AppContext.Provider>;
}

export function useApp() {
  const ctx = useContext(AppContext);
  if (!ctx) throw new Error("useApp must be used within AppProvider");
  return ctx;
}
