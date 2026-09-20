import { Menu, FileText, UploadCloud } from "lucide-react";
import { useApp } from "../store";
import { PrimaryButton } from "./Button";

export default function TopHeader({ title, onMenuClick, onManageDocuments }) {
  const { currentDocument } = useApp();

  return (
    <header className="flex items-center justify-between gap-4 py-4 border-b-2 border-border mb-6">
      <div className="flex items-center gap-3 min-w-0">
        <button
          className="lg:hidden p-2 rounded-sm border-2 border-ink shrink-0"
          onClick={onMenuClick}
          aria-label="Open navigation"
        >
          <Menu size={20} strokeWidth={2.5} />
        </button>
        <h1 className="font-heading text-xl sm:text-2xl font-extrabold truncate">{title}</h1>
      </div>

      <div className="flex items-center gap-3 shrink-0">
        {currentDocument && (
          <span className="hidden sm:inline-flex items-center gap-1.5 px-3 py-1.5 rounded-pill border-2 border-ink bg-white text-sm font-semibold max-w-[220px]">
            <FileText size={14} strokeWidth={2.5} className="shrink-0" />
            <span className="truncate">{currentDocument}</span>
          </span>
        )}
        <PrimaryButton icon={UploadCloud} onClick={onManageDocuments} className="text-sm px-4 py-2 min-h-[40px]">
          <span className="hidden sm:inline">Manage documents</span>
          <span className="sm:hidden">Upload</span>
        </PrimaryButton>
      </div>
    </header>
  );
}
