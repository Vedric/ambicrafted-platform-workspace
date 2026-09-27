import { ExternalLink } from "lucide-react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
export default function MarkdownRenderer({ texte }: { texte: string }) {
  return (
    <div className="markdown">
      <ReactMarkdown
        remarkPlugins={[remarkGfm]}
        components={{
          img: ({ alt }) => <span>{alt}</span>,
          a: ({ children, href }) => (
            <a href={href} target="_blank" rel="noopener noreferrer">
              {children}
              <ExternalLink size={12} />
            </a>
          ),
        }}
      >
        {texte}
      </ReactMarkdown>
    </div>
  );
}
