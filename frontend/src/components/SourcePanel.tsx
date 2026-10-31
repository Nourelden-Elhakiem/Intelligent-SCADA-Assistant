import { BookOpenText, ExternalLink, Image as ImageIcon, X } from "lucide-react";
import { api } from "../api";
import type { ChatMessage, RelatedImage } from "../types";

interface SourcePanelProps {
  documentKey: string;
  documentName: string;
  message: ChatMessage | null;
  onClose: () => void;
  onImage: (image: RelatedImage) => void;
}

export function SourcePanel({ documentKey, documentName, message, onClose, onImage }: SourcePanelProps) {
  if (!message) return null;
  return (
    <aside className="source-panel" aria-label="Answer evidence">
      <div className="source-panel-header">
        <div>
          <span className="eyebrow">Evidence</span>
          <h2>Retrieved sources</h2>
        </div>
        <button className="icon-button" type="button" onClick={onClose} aria-label="Close evidence">
          <X size={18} />
        </button>
      </div>

      <div className="source-panel-scroll">
        {message.sources?.map((source, index) => (
          <article className="source-card" key={source.chunk_id}>
            <div className="source-card-topline">
              <span className="source-index">S{index + 1}</span>
              <span className="score">Similarity {source.score.toFixed(3)}</span>
            </div>
            <h3>{source.section_title || "Untitled section"}</h3>
            <div className="source-document">{documentName}</div>
            <div className="source-meta">
              <BookOpenText size={14} />
              <span>
                {source.page_start === source.page_end
                  ? `Page ${source.page_start}`
                  : `Pages ${source.page_start}–${source.page_end}`}
              </span>
            </div>
            {source.section_path.length > 0 && (
              <div className="breadcrumbs">{source.section_path.join(" / ")}</div>
            )}
            <p>{source.text}</p>
          </article>
        ))}

        {!!message.images?.length && (
          <section className="visual-evidence">
            <div className="section-label">
              <ImageIcon size={15} /> Visual references
            </div>
            <div className="image-grid">
              {message.images.map((image) => (
                <button
                  type="button"
                  className="image-tile"
                  key={image.filename}
                  onClick={() => onImage(image)}
                >
                  <img src={api.imageUrl(documentKey, image.filename)} alt={`Manual page ${image.page}`} />
                  <span>Page {image.page}</span>
                  <ExternalLink size={13} />
                </button>
              ))}
            </div>
          </section>
        )}
      </div>
    </aside>
  );
}
