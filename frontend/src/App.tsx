import { useEffect, useMemo, useRef, useState } from "react";
import {
  AlertTriangle,
  BookOpen,
  BookOpenCheck,
  CircleHelp,
  Database,
  FileSearch,
  Gauge,
  Image as ImageIcon,
  Layers3,
  Menu,
  MessageSquarePlus,
  Plus,
  Send,
  Settings2,
  Trash2,
  X,
} from "lucide-react";
import { api } from "./api";
import { AnswerText } from "./components/AnswerText";
import { InteractiveDots } from "./components/InteractiveDots";
import { SourcePanel } from "./components/SourcePanel";
import { UploadModal } from "./components/UploadModal";
import type {
  ChatMessage,
  Citation,
  DocumentSummary,
  Health,
  Job,
  RelatedImage,
  Runtime,
} from "./types";

const SUGGESTIONS = [
  "How do I configure the controller?",
  "How are alarms configured?",
  "Explain the system architecture.",
  "Show information about communication configuration.",
];

function newId() {
  return `${Date.now()}-${Math.random().toString(16).slice(2)}`;
}

function formatCount(value: number) {
  return new Intl.NumberFormat("en", {
    notation: value > 9999 ? "compact" : "standard",
  }).format(value);
}

function storedSessions(): Record<string, string> {
  try {
    return JSON.parse(localStorage.getItem("scada-session-map") || "{}") as Record<
      string,
      string
    >;
  } catch {
    return {};
  }
}

function routingUsesRetrieval(message: ChatMessage) {
  return message.routing?.requires_retrieval === true;
}

function statusCopy(health: Health | null, activeJob: Job | null) {
  if (activeJob && ["queued", "running"].includes(activeJob.status)) {
    return { tone: "working", title: "Ingestion in progress", detail: activeJob.message };
  }
  if (!health) {
    return { tone: "neutral", title: "Checking system", detail: "Reading backend status…" };
  }
  if (health.database === "not_configured") {
    return { tone: "warning", title: "Database not configured", detail: "Set PG_CONN_STR to continue" };
  }
  if (health.database === "unavailable") {
    return { tone: "danger", title: "Database unavailable", detail: "Check PostgreSQL and pgvector" };
  }
  if (health.default_document !== "indexed" && health.default_pdf === "missing") {
    return { tone: "warning", title: "Manual missing", detail: "Copy the PDF to its configured default path" };
  }
  if (health.default_document !== "indexed") {
    return { tone: "warning", title: "Default manual not indexed", detail: "Run notebook 08 to prepare it" };
  }
  if (health.answer_model !== "configured") {
    return { tone: "warning", title: "Knowledge base ready", detail: "Answer provider not configured" };
  }
  return { tone: "ready", title: "Knowledge base ready", detail: "Power SCADA 2020 is indexed" };
}

function AppIcon({ small = false }: { small?: boolean }) {
  return (
    <span className={`app-icon ${small ? "small" : ""}`} aria-hidden="true">
      <Gauge size={small ? 16 : 19} />
      <img
        src="/valve-101.png"
        alt=""
        onError={(event) => {
          event.currentTarget.hidden = true;
        }}
      />
    </span>
  );
}

export default function App() {
  const [documents, setDocuments] = useState<DocumentSummary[]>([]);
  const [selectedKey, setSelectedKey] = useState("");
  const [health, setHealth] = useState<Health | null>(null);
  const [runtime, setRuntime] = useState<Runtime | null>(null);
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [question, setQuestion] = useState("");
  const [asking, setAsking] = useState(false);
  const [loading, setLoading] = useState(true);
  const [globalError, setGlobalError] = useState("");
  const [showUpload, setShowUpload] = useState(false);
  const [uploading, setUploading] = useState(false);
  const [activeJob, setActiveJob] = useState<Job | null>(null);
  const [sourceMessage, setSourceMessage] = useState<ChatMessage | null>(null);
  const [lightboxImage, setLightboxImage] = useState<(RelatedImage & { documentKey: string; documentName: string }) | null>(null);
  const [sidebarOpen, setSidebarOpen] = useState(false);
  const [memoryEnabled, setMemoryEnabled] = useState(true);
  const [imagesEnabled, setImagesEnabled] = useState(true);
  const [topK, setTopK] = useState<number | null>(null);
  const [sessions, setSessions] = useState<Record<string, string>>(storedSessions);
  const bottomRef = useRef<HTMLDivElement>(null);
  const conversationRef = useRef({ documentKey: "", generation: 0 });
  const requestRef = useRef<AbortController | null>(null);

  function resetConversation(documentKey: string) {
    conversationRef.current = { documentKey, generation: conversationRef.current.generation + 1 };
    requestRef.current?.abort();
    requestRef.current = null;
    setAsking(false);
    setMessages([]);
    setSourceMessage(null);
    setLightboxImage(null);
  }

  useEffect(() => {
    localStorage.setItem("scada-session-map", JSON.stringify(sessions));
  }, [sessions]);

  useEffect(() => () => requestRef.current?.abort(), []);

  const defaultKey =
    runtime?.default_document_key ||
    documents.find((document) => document.is_default)?.document_key ||
    "";
  const defaultName =
    runtime?.default_document_name ||
    documents.find((document) => document.is_default)?.document_name ||
    "Default Power SCADA manual";

  const selectedDocument = useMemo(
    () => documents.find((document) => document.document_key === selectedKey) ?? null,
    [documents, selectedKey],
  );
  const selectedName = selectedDocument?.document_name || (selectedKey === defaultKey ? defaultName : "SCADA manual");
  const selectedIsDefault = selectedKey === defaultKey || selectedDocument?.is_default === true;
  const defaultIndexed = documents.some((document) => document.document_key === defaultKey);
  const sortedDocuments = useMemo(
    () => [...documents].sort((a, b) => Number(b.is_default) - Number(a.is_default)),
    [documents],
  );
  const systemStatus = statusCopy(health, activeJob);

  async function refreshDocuments(preferredKey?: string) {
    const next = await api.documents();
    setDocuments(next);
    const current = conversationRef.current.documentKey;
    const nextKey = preferredKey && next.some((document) => document.document_key === preferredKey)
      ? preferredKey
      : current && (current === defaultKey || next.some((document) => document.document_key === current))
        ? current
        : defaultKey || next.find((document) => document.is_default)?.document_key || next[0]?.document_key || "";
    chooseDocument(nextKey);
  }

  useEffect(() => {
    let active = true;
    Promise.allSettled([api.health(), api.runtime(), api.documents()]).then((results) => {
      if (!active) return;
      const [healthResult, runtimeResult, documentsResult] = results;
      const runtimeValue = runtimeResult.status === "fulfilled" ? runtimeResult.value : null;
      const documentValues = documentsResult.status === "fulfilled" ? documentsResult.value : [];

      if (healthResult.status === "fulfilled") setHealth(healthResult.value);
      if (runtimeValue) {
        setRuntime(runtimeValue);
        setTopK(runtimeValue.default_top_k);
      }
      setDocuments(documentValues);
      const primaryKey =
        runtimeValue?.default_document_key ||
        documentValues.find((document) => document.is_default)?.document_key ||
        documentValues[0]?.document_key ||
        "";
      chooseDocument(primaryKey);
      if (documentsResult.status === "rejected") {
        setGlobalError("The knowledge base is unavailable. Verify PostgreSQL and refresh.");
      }
      setLoading(false);
    });

    const healthTimer = window.setInterval(() => {
      api.health().then(setHealth).catch(() => setHealth(null));
    }, 15000);
    return () => {
      active = false;
      window.clearInterval(healthTimer);
    };
  }, []);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, asking]);

  useEffect(() => {
    if (!activeJob || !["queued", "running"].includes(activeJob.status)) return;
    const timer = window.setInterval(async () => {
      try {
        const nextJob = await api.job(activeJob.job_id);
        setActiveJob(nextJob);
        if (nextJob.status === "succeeded") {
          await refreshDocuments(nextJob.document_key);
        }
      } catch (error) {
        setGlobalError(error instanceof Error ? error.message : "Could not read ingestion progress");
      }
    }, 1200);
    return () => window.clearInterval(timer);
  }, [activeJob?.job_id, activeJob?.status, defaultKey]);

  function chooseDocument(key: string) {
    if (key !== conversationRef.current.documentKey) {
      resetConversation(key);
      setSelectedKey(key);
    }
    setSidebarOpen(false);
  }

  async function submitQuestion(suggested?: string) {
    const cleanQuestion = (suggested ?? question).trim();
    if (!cleanQuestion || requestRef.current) return;
    if (!selectedDocument) {
      setGlobalError(
        selectedIsDefault
          ? `The default manual is not indexed yet. Prepare ${defaultName} with notebook 08 first.`
          : "Select an indexed manual before asking a question.",
      );
      return;
    }

    const sessionKey = selectedDocument.document_key;
    const documentName = selectedDocument.document_name;
    const generation = conversationRef.current.generation;
    const controller = new AbortController();
    requestRef.current = controller;
    const ownsConversation = () => !controller.signal.aborted
      && generation === conversationRef.current.generation
      && sessionKey === conversationRef.current.documentKey;
    const userMessage: ChatMessage = {
      id: newId(),
      role: "user",
      documentKey: sessionKey,
      documentName,
      content: cleanQuestion,
      createdAt: new Date(),
    };
    setMessages((current) => [...current, userMessage]);
    setQuestion("");
    setAsking(true);
    setGlobalError("");
    try {
      const response = await api.ask({
        question: cleanQuestion,
        document_key: sessionKey,
        session_id: sessions[sessionKey] || null,
        memory_enabled: memoryEnabled,
        include_images: imagesEnabled,
        top_k: topK,
      }, controller.signal);
      if (!ownsConversation()) return;
      if (response.session_id) {
        const sessionId = response.session_id;
        setSessions((current) => ({ ...current, [sessionKey]: sessionId }));
      }
      const assistantMessage: ChatMessage = {
        id: newId(),
        role: "assistant",
        documentKey: sessionKey,
        documentName,
        content: response.answer,
        createdAt: new Date(),
        citations: response.citations,
        sources: response.sources,
        images: response.related_images,
        routing: response.routing,
      };
      setMessages((current) => [...current, assistantMessage]);
    } catch (error) {
      if (!ownsConversation()) return;
      setMessages((current) => [
        ...current,
        {
          id: newId(),
          role: "assistant",
          documentKey: sessionKey,
          documentName,
          content: error instanceof Error ? error.message : "The answer could not be generated.",
          createdAt: new Date(),
          error: true,
        },
      ]);
    } finally {
      if (ownsConversation()) {
        requestRef.current = null;
        setAsking(false);
      }
    }
  }

  async function upload(form: FormData) {
    setUploading(true);
    try {
      const job = await api.upload(form);
      setActiveJob(job);
      setShowUpload(false);
    } finally {
      setUploading(false);
    }
  }

  async function removeDocument(document: DocumentSummary) {
    if (document.is_default) return;
    const confirmed = window.confirm(
      `Delete “${document.document_name}” from PostgreSQL and remove its generated artifacts?`,
    );
    if (!confirmed) return;
    try {
      await api.deleteDocument(document.document_key);
      if (conversationRef.current.documentKey === document.document_key) {
        resetConversation(document.document_key);
      }
      setSessions((current) => {
        const next = { ...current };
        delete next[document.document_key];
        return next;
      });
      await refreshDocuments();
    } catch (error) {
      setGlobalError(error instanceof Error ? error.message : "Document deletion failed");
    }
  }

  function openCitation(message: ChatMessage, _citation: Citation) {
    setSourceMessage(message);
  }

  function startNewChat() {
    resetConversation(selectedKey);
    setSessions((current) => {
      const next = { ...current };
      delete next[selectedKey];
      return next;
    });
  }

  return (
    <div className="app-shell">
      <InteractiveDots />

      <aside className={`sidebar ${sidebarOpen ? "open" : ""}`} aria-label="Manual navigation">
        <div className="brand">
          <AppIcon />
          <div>
            <strong>Intelligent SCADA</strong>
            <span>Power SCADA Assistant</span>
          </div>
          <button className="mobile-close" type="button" onClick={() => setSidebarOpen(false)} aria-label="Close manuals">
            <X size={19} />
          </button>
        </div>

        <button className="button primary new-chat" type="button" onClick={startNewChat}>
          <MessageSquarePlus size={17} /> New conversation
        </button>

        <div className="sidebar-section-title">
          <span>Manuals</span>
          <button type="button" onClick={() => setShowUpload(true)} aria-label="Add manual" disabled={!runtime}><Plus size={16} /></button>
        </div>
        <div className="document-list">
          {loading && <div className="sidebar-skeleton" />}
          {!loading && defaultKey && !defaultIndexed && (
            <div className={`document-item unavailable ${selectedKey === defaultKey ? "active" : ""}`}>
              <button className="document-select" type="button" onClick={() => chooseDocument(defaultKey)}>
                <BookOpen size={17} />
                <span>
                  <strong>{defaultName}</strong>
                  <small>Not indexed</small>
                </span>
                <em>Default</em>
              </button>
            </div>
          )}
          {sortedDocuments.map((document) => (
            <div className={`document-item ${document.document_key === selectedKey ? "active" : ""}`} key={document.document_key}>
              <button className="document-select" type="button" onClick={() => chooseDocument(document.document_key)}>
                <BookOpen size={17} />
                <span>
                  <strong>{document.document_name}</strong>
                  <small>{formatCount(document.chunk_count)} chunks · {formatCount(document.image_count)} visuals</small>
                </span>
                {document.is_default && <em>Default</em>}
              </button>
              {!document.is_default && (
                <button className="document-delete" type="button" onClick={() => removeDocument(document)} aria-label={`Delete ${document.document_name}`}>
                  <Trash2 size={14} />
                </button>
              )}
            </div>
          ))}
        </div>

        <button className="button secondary add-manual" type="button" onClick={() => setShowUpload(true)} disabled={!runtime}>
          <Plus size={16} /> Add manual
        </button>

        <div className="retrieval-settings">
          <div className="sidebar-section-title"><span>Answer preferences</span><Settings2 size={15} /></div>
          <label className="range-row">
            <span>Maximum sources <strong>{topK ?? runtime?.default_top_k ?? "—"}</strong></span>
            <input
              type="range"
              min="1"
              max={runtime?.max_top_k ?? 1}
              value={topK ?? runtime?.default_top_k ?? 1}
              disabled={!runtime}
              onChange={(event) => setTopK(Number(event.target.value))}
            />
          </label>
          <label className="compact-toggle">
            <span><Layers3 size={15} /> Conversation memory</span>
            <input type="checkbox" checked={memoryEnabled} onChange={(event) => setMemoryEnabled(event.target.checked)} />
            <i />
          </label>
          <label className="compact-toggle">
            <span><ImageIcon size={15} /> Related images</span>
            <input type="checkbox" checked={imagesEnabled} onChange={(event) => setImagesEnabled(event.target.checked)} />
            <i />
          </label>
        </div>

        <div className={`system-status ${systemStatus.tone}`}>
          <span className="status-dot" />
          <div>
            <strong>{systemStatus.title}</strong>
            <span>{systemStatus.detail}</span>
          </div>
        </div>
      </aside>

      {sidebarOpen && <button className="mobile-overlay" onClick={() => setSidebarOpen(false)} aria-label="Close manuals" />}

      <main className="main-area">
        <header className="topbar">
          <div className="topbar-left">
            <button className="menu-button" type="button" onClick={() => setSidebarOpen(true)} aria-label="Open manuals"><Menu size={20} /></button>
            <AppIcon small />
            <div className="topbar-brand-copy">
              <strong>Power SCADA Assistant</strong>
              <span>{selectedName}</span>
            </div>
          </div>
          <div className="topbar-actions">
            {health?.knowledge_base === "ready" && (
              <span className="ready-badge"><BookOpenCheck size={15} /> Knowledge Base Ready</span>
            )}
            <button className="header-manuals" type="button" onClick={() => setShowUpload(true)} disabled={!runtime}><Plus size={15} /> Add manual</button>
            <a className="icon-button" href="/api/docs" target="_blank" rel="noreferrer" aria-label="API documentation"><CircleHelp size={18} /></a>
          </div>
        </header>

        {activeJob && (
          <div className={`job-banner ${activeJob.status}`}>
            <div className="job-icon">{activeJob.status === "failed" ? <AlertTriangle size={18} /> : <Database size={18} />}</div>
            <div className="job-details">
              <div><strong>{activeJob.document_name}</strong><span>{activeJob.message}</span></div>
              <div className="progress-track"><div style={{ width: `${Math.max(2, activeJob.progress * 100)}%` }} /></div>
            </div>
            <span className="job-percent">{activeJob.status === "failed" ? "Failed" : `${Math.round(activeJob.progress * 100)}%`}</span>
            {!['queued', 'running'].includes(activeJob.status) && (
              <button type="button" onClick={() => setActiveJob(null)} aria-label="Dismiss"><X size={17} /></button>
            )}
          </div>
        )}

        {globalError && (
          <div className="global-error" role="alert"><AlertTriangle size={17} /><span>{globalError}</span><button type="button" onClick={() => setGlobalError("")} aria-label="Dismiss error"><X size={15} /></button></div>
        )}

        <div className={`workspace ${sourceMessage ? "with-sources" : ""}`}>
          <section className="conversation" aria-label="SCADA assistant conversation">
            <div className="conversation-scroll">
              {messages.length === 0 ? (
                <div className="welcome">
                  <div className="welcome-kicker"><BookOpenCheck size={16} /> Manual-grounded engineering assistant</div>
                  <h1>Intelligent assistance for Power SCADA</h1>
                  <p>
                    {selectedIsDefault ? (
                      <>Ask technical questions grounded in <strong>{defaultName}</strong>. The assistant searches the manual only when your question needs it, then returns source-backed answers and related images when available.</>
                    ) : (
                      <>Ask technical questions grounded in the selected manual, <strong>{selectedName}</strong>. Retrieval, citations, images, and session context remain isolated to this document.</>
                    )}
                  </p>
                  <div className="welcome-status-row">
                    <span>{selectedIsDefault ? "Power SCADA 2020" : selectedName}</span>
                    <span>Manual grounded</span>
                    {!!selectedDocument?.chunk_count && <span className="ready">Indexed</span>}
                  </div>
                  {!selectedDocument && selectedIsDefault && !loading && (
                    <div className="setup-notice">
                      <AlertTriangle size={17} />
                      <span>
                        <strong>The default manual is not ready yet.</strong>
                        Place it at <code>{runtime?.default_pdf_path ?? "the configured default PDF path"}</code> and run notebook 08 to prepare the knowledge base.
                      </span>
                    </div>
                  )}
                  <div className="suggestion-grid" aria-label="Starter questions">
                    {SUGGESTIONS.map((suggestion, index) => (
                      <button type="button" onClick={() => submitQuestion(suggestion)} key={suggestion} disabled={!selectedDocument || asking}>
                        {index === 2 ? <BookOpen size={18} /> : index === 3 ? <ImageIcon size={18} /> : <Settings2 size={18} />}
                        <span>{suggestion}</span>
                        <Send size={14} />
                      </button>
                    ))}
                  </div>
                </div>
              ) : (
                <div className="message-list">
                  {messages.map((message) => (
                    <article className={`message ${message.role} ${message.error ? "error" : ""}`} key={message.id}>
                      <div className="avatar">{message.role === "assistant" ? <AppIcon small /> : "You"}</div>
                      <div className="message-body">
                        <div className="message-label">
                          <strong>{message.role === "assistant" ? "Power SCADA Assistant" : "You"}</strong>
                          <time>{message.createdAt.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" })}</time>
                        </div>
                        {message.role === "assistant" ? (
                          <AnswerText text={message.content} citations={message.citations} onCitation={(citation) => openCitation(message, citation)} />
                        ) : <p>{message.content}</p>}

                        {message.role === "assistant" && routingUsesRetrieval(message) && !!message.sources?.length && (
                          <div className="grounded-label"><BookOpenCheck size={14} /> Retrieved from {message.documentName}</div>
                        )}

                        {message.role === "assistant" && !!message.images?.length && (
                          <div className="message-images">
                            {message.images.slice(0, 4).map((image) => (
                              <button type="button" key={image.filename} onClick={() => setLightboxImage({ ...image, documentKey: message.documentKey, documentName: message.documentName })}>
                                <img src={api.imageUrl(message.documentKey, image.filename)} alt={`Related manual visual from page ${image.page}`} />
                                <span>Page {image.page}</span>
                              </button>
                            ))}
                          </div>
                        )}

                        {message.role === "assistant" && !!message.sources?.length && (
                          <button className="evidence-button" type="button" onClick={() => setSourceMessage(message)}>
                            <FileSearch size={15} /> {message.sources.length} retrieved {message.sources.length === 1 ? "source" : "sources"}
                            {!!message.images?.length && <span><ImageIcon size={13} /> {message.images.length} images</span>}
                          </button>
                        )}
                      </div>
                    </article>
                  ))}
                  {asking && (
                    <article className="message assistant thinking" aria-live="polite">
                      <div className="avatar"><AppIcon small /></div>
                      <div className="message-body">
                        <div className="message-label"><strong>Power SCADA Assistant</strong></div>
                        <div className="thinking-row"><span /><span /><span /> Preparing response…</div>
                      </div>
                    </article>
                  )}
                </div>
              )}
              <div ref={bottomRef} />
            </div>

            <div className="composer-wrap">
              <div className="composer">
                <textarea
                  value={question}
                  onChange={(event) => setQuestion(event.target.value)}
                  onKeyDown={(event) => {
                    if (event.key === "Enter" && !event.shiftKey) {
                      event.preventDefault();
                      submitQuestion();
                    }
                  }}
                  rows={1}
                  aria-label="Ask the Power SCADA Assistant"
                  placeholder={selectedDocument ? "Ask a Power SCADA question…" : "Prepare or select an indexed manual to begin"}
                  disabled={!selectedDocument || asking}
                />
                <button className="send-button" type="button" onClick={() => submitQuestion()} disabled={!question.trim() || !selectedDocument || asking} aria-label="Send question">
                  <Send size={17} />
                </button>
              </div>
              <div className="composer-meta">
                <span>Smart routing · manual retrieval only when needed</span>
                <span>Enter to send · Shift + Enter for a new line</span>
              </div>
            </div>
          </section>

          <SourcePanel
            documentKey={sourceMessage?.documentKey || ""}
            documentName={sourceMessage?.documentName || ""}
            message={sourceMessage}
            onClose={() => setSourceMessage(null)}
            onImage={(image) => sourceMessage && setLightboxImage({ ...image, documentKey: sourceMessage.documentKey, documentName: sourceMessage.documentName })}
          />
        </div>
      </main>

      {showUpload && runtime && (
        <UploadModal
          maximumMb={runtime.max_upload_mb}
          busy={uploading}
          onClose={() => setShowUpload(false)}
          onUpload={upload}
        />
      )}

      {lightboxImage && (
        <div className="lightbox" role="dialog" aria-modal="true" aria-label="Related manual image" onMouseDown={(event) => {
          if (event.target === event.currentTarget) setLightboxImage(null);
        }}>
          <div className="lightbox-card">
            <button className="icon-button lightbox-close" type="button" onClick={() => setLightboxImage(null)} aria-label="Close image"><X size={19} /></button>
            <img src={api.imageUrl(lightboxImage.documentKey, lightboxImage.filename)} alt={`Manual visual from page ${lightboxImage.page}`} />
            <div><strong>{lightboxImage.documentName}</strong><span>Page {lightboxImage.page} · {lightboxImage.filename}</span></div>
          </div>
        </div>
      )}
    </div>
  );
}
