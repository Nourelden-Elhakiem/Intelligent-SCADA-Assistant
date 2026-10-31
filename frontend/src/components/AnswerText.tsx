import rehypeHighlight from "rehype-highlight";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";

import type { Citation } from "../types";

interface AnswerTextProps {
  text: string;
  citations?: Citation[];
  onCitation: (citation: Citation) => void;
}

export function AnswerText({ text, citations = [], onCitation }: AnswerTextProps) {
  const citationMap = new Map(citations.map((citation) => [citation.source_id, citation]));
  const markdown = text.replace(
    /\[((?:S\d+)(?:\s*,\s*S\d+)*)\]/g,
    (reference, sourceGroup: string) => {
      const sourceIds = sourceGroup.split(",").map((sourceId) => sourceId.trim());
      if (!sourceIds.every((sourceId) => citationMap.has(sourceId))) {
        return reference;
      }
      return sourceIds
        .map((sourceId) => `[${sourceId}](#scada-citation-${sourceId})`)
        .join(" ");
    },
  );

  return (
    <div className="answer-text">
      <ReactMarkdown
        remarkPlugins={[remarkGfm]}
        rehypePlugins={[[rehypeHighlight, { detect: true, ignoreMissing: true }]]}
        skipHtml
        components={{
          img: ({ alt }) => <span>{alt ? `[Image omitted: ${alt}]` : "[Image omitted]"}</span>,
          a: ({ href, children, ...props }) => {
            const sourceId = href?.match(/^#scada-citation-(S\d+)$/)?.[1];
            const citation = sourceId ? citationMap.get(sourceId) : undefined;

            if (citation && sourceId) {
              return (
                <button
                  type="button"
                  className="inline-citation"
                  title={citation.label}
                  aria-label={`Open source ${sourceId}: ${citation.label}`}
                  onClick={() => onCitation(citation)}
                >
                  {sourceId}
                </button>
              );
            }

            return (
              <a href={href} target="_blank" rel="noreferrer" {...props}>
                {children}
              </a>
            );
          },
        }}
      >
        {markdown}
      </ReactMarkdown>
    </div>
  );
}
