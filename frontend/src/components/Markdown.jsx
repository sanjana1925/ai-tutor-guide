import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";

// Renders the markdown the tutor writes (**bold**, *italic*, bullet/numbered lists incl. nested,
// headings, tables, code) as real formatting. react-markdown never renders raw HTML, and it
// sanitises link protocols, so model output cannot inject markup or scripts.
const components = {
  p: ({ node, ...props }) => <p className="mb-3 last:mb-0" {...props} />,
  strong: ({ node, ...props }) => <strong className="font-bold" {...props} />,
  em: ({ node, ...props }) => <em className="italic" {...props} />,
  ul: ({ node, ...props }) => <ul className="list-disc pl-5 mb-3 last:mb-0 space-y-1.5 marker:text-violet" {...props} />,
  ol: ({ node, ...props }) => <ol className="list-decimal pl-5 mb-3 last:mb-0 space-y-1.5 marker:font-bold" {...props} />,
  li: ({ node, ...props }) => <li className="pl-1 [&>ul]:mt-1.5 [&>ol]:mt-1.5 [&>p]:mb-1" {...props} />,
  h1: ({ node, ...props }) => <h3 className="font-heading text-xl font-extrabold mt-4 mb-2 first:mt-0" {...props} />,
  h2: ({ node, ...props }) => <h3 className="font-heading text-lg font-extrabold mt-4 mb-2 first:mt-0" {...props} />,
  h3: ({ node, ...props }) => <h4 className="font-heading text-base font-extrabold mt-3 mb-1.5 first:mt-0" {...props} />,
  h4: ({ node, ...props }) => <h4 className="font-heading text-base font-bold mt-3 mb-1.5 first:mt-0" {...props} />,
  hr: () => <hr className="my-4 border-t-2 border-border" />,
  blockquote: ({ node, ...props }) => (
    <blockquote className="border-l-4 border-violet pl-4 my-3 text-muted-fg italic" {...props} />
  ),
  code: ({ node, className, children, ...props }) =>
    className ? (
      <code className={`${className} font-mono text-sm`} {...props}>
        {children}
      </code>
    ) : (
      <code className="px-1.5 py-0.5 rounded-sm bg-muted border border-border font-mono text-[0.85em]" {...props}>
        {children}
      </code>
    ),
  pre: ({ node, ...props }) => (
    <pre className="my-3 p-4 rounded-md bg-muted border-2 border-border overflow-x-auto text-sm" {...props} />
  ),
  a: ({ node, ...props }) => (
    <a className="text-violet font-semibold underline" target="_blank" rel="noopener noreferrer" {...props} />
  ),
  table: ({ node, ...props }) => (
    <div className="my-3 overflow-x-auto">
      <table className="w-full text-left border-collapse border-2 border-border text-sm" {...props} />
    </div>
  ),
  th: ({ node, ...props }) => <th className="px-3 py-2 border-b-2 border-border font-bold bg-muted" {...props} />,
  td: ({ node, ...props }) => <td className="px-3 py-2 border-b border-border" {...props} />,
};

export default function Markdown({ children, className = "" }) {
  return (
    <div className={`break-words ${className}`}>
      <ReactMarkdown remarkPlugins={[remarkGfm]} components={components}>
        {children || ""}
      </ReactMarkdown>
    </div>
  );
}
