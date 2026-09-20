import { useEffect, useState } from "react";
import Sidebar from "./Sidebar";
import TopHeader from "./TopHeader";
import DocumentPanel from "./DocumentPanel";

export default function Shell({ title, children }) {
  const [navOpen, setNavOpen] = useState(false);
  const [docPanelOpen, setDocPanelOpen] = useState(false);

  useEffect(() => {
    document.title = title ? `${title} · AI Tutor Guide` : "AI Tutor Guide";
  }, [title]);

  return (
    <div className="min-h-screen flex bg-bg dot-grid">
      <Sidebar open={navOpen} onClose={() => setNavOpen(false)} />
      <div className="flex-1 min-w-0 px-4 sm:px-8 py-4">
        <div className="max-w-shell mx-auto">
          <TopHeader
            title={title}
            onMenuClick={() => setNavOpen(true)}
            onManageDocuments={() => setDocPanelOpen(true)}
          />
          <main>{children}</main>
        </div>
      </div>
      {docPanelOpen && <DocumentPanel onClose={() => setDocPanelOpen(false)} />}
    </div>
  );
}
