import { useEffect, useRef, useState } from "react";
import { FileText, UploadCloud, X } from "lucide-react";

interface UploadModalProps {
  maximumMb: number;
  busy: boolean;
  onClose: () => void;
  onUpload: (form: FormData) => Promise<void>;
}

function slugify(value: string) {
  return value
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, "-")
    .replace(/^-|-$/g, "")
    .slice(0, 80)
    .replace(/-+$/g, "");
}

export function UploadModal({ maximumMb, busy, onClose, onUpload }: UploadModalProps) {
  const dialogRef = useRef<HTMLElement>(null);
  const inputRef = useRef<HTMLInputElement>(null);
  const [file, setFile] = useState<File | null>(null);
  const [name, setName] = useState("");
  const [key, setKey] = useState("");
  const [includeImages, setIncludeImages] = useState(true);
  const [dragging, setDragging] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    const previous = document.activeElement as HTMLElement | null;
    dialogRef.current?.querySelector<HTMLButtonElement>("button:not(:disabled)")?.focus();
    return () => previous?.focus();
  }, []);

  function selectFile(selected?: File) {
    if (!selected) return;
    setError("");
    setFile(null);
    if (inputRef.current) inputRef.current.value = "";
    if (selected.type !== "application/pdf" && !selected.name.toLowerCase().endsWith(".pdf")) {
      setError("Choose a PDF manual.");
      return;
    }
    if (selected.size > maximumMb * 1024 * 1024) {
      setError(`The PDF must be smaller than ${maximumMb} MB.`);
      return;
    }
    const inferredName = selected.name.replace(/\.pdf$/i, "").slice(0, 200);
    setFile(selected);
    setName((current) => current || inferredName);
    setKey((current) => current || slugify(inferredName));
  }

  async function submit() {
    if (!file || !name.trim() || !key.trim()) {
      setError("Choose a PDF and provide its name and document key.");
      return;
    }
    const form = new FormData();
    form.append("file", file);
    form.append("document_name", name.trim());
    form.append("document_key", key.trim());
    form.append("include_images", String(includeImages));
    form.append("resume", "false");
    form.append("force", "false");
    try {
      setError("");
      await onUpload(form);
    } catch (uploadError) {
      setError(uploadError instanceof Error ? uploadError.message : "Upload failed");
    }
  }

  return (
    <div className="modal-backdrop" role="presentation" onMouseDown={(event) => {
      if (event.target === event.currentTarget && !busy) onClose();
    }}>
      <section ref={dialogRef} className="modal" role="dialog" aria-modal="true" aria-labelledby="upload-title" onKeyDown={(event) => {
        if (event.key === "Escape" && !busy) { event.preventDefault(); onClose(); }
        if (event.key !== "Tab") return;
        const focusable = Array.from(dialogRef.current?.querySelectorAll<HTMLElement>(
          'button:not(:disabled), input:not(:disabled):not([type="file"])',
        ) || []);
        const first = focusable[0];
        const last = focusable[focusable.length - 1];
        if (event.shiftKey && document.activeElement === first) { event.preventDefault(); last?.focus(); }
        if (!event.shiftKey && document.activeElement === last) { event.preventDefault(); first?.focus(); }
      }}>
        <div className="modal-header">
          <div>
            <span className="eyebrow">Knowledge base</span>
            <h2 id="upload-title">Add a SCADA manual</h2>
          </div>
          <button className="icon-button" type="button" onClick={onClose} disabled={busy} aria-label="Close">
            <X size={18} />
          </button>
        </div>

        <button
          className={`dropzone ${dragging ? "dragging" : ""} ${file ? "has-file" : ""}`}
          type="button"
          onClick={() => inputRef.current?.click()}
          onDragEnter={(event) => { event.preventDefault(); setDragging(true); }}
          onDragOver={(event) => event.preventDefault()}
          onDragLeave={() => setDragging(false)}
          onDrop={(event) => {
            event.preventDefault();
            setDragging(false);
            selectFile(event.dataTransfer.files[0]);
          }}
        >
          {file ? <FileText size={30} /> : <UploadCloud size={30} />}
          <strong>{file ? file.name : "Drop a PDF here or browse"}</strong>
          <span>{file ? `${(file.size / 1024 / 1024).toFixed(1)} MB` : `PDF only · up to ${maximumMb} MB`}</span>
        </button>
        <input
          ref={inputRef}
          className="visually-hidden"
          type="file"
          accept="application/pdf,.pdf"
          onChange={(event) => selectFile(event.target.files?.[0])}
        />

        <div className="form-grid">
          <label>
            <span>Document name</span>
            <input maxLength={200} value={name} onChange={(event) => {
              setName(event.target.value);
              setKey(slugify(event.target.value));
            }} placeholder="Power SCADA System Guide" />
          </label>
          <label>
            <span>Document key</span>
            <input maxLength={80} value={key} onChange={(event) => setKey(slugify(event.target.value))} placeholder="power-scada-system-guide" />
          </label>
        </div>

        <label className="toggle-row">
          <span>
            <strong>Extract visual references</strong>
            <small>Preserve diagrams and link them to relevant chunks.</small>
          </span>
          <input type="checkbox" checked={includeImages} onChange={(event) => setIncludeImages(event.target.checked)} />
          <span className="toggle" />
        </label>

        {error && <div className="form-error">{error}</div>}
        <div className="modal-actions">
          <button className="button secondary" type="button" onClick={onClose} disabled={busy}>Cancel</button>
          <button className="button primary" type="button" onClick={submit} disabled={busy || !file}>
            {busy ? <span className="spinner" /> : <UploadCloud size={17} />}
            {busy ? "Uploading…" : "Start ingestion"}
          </button>
        </div>
      </section>
    </div>
  );
}
