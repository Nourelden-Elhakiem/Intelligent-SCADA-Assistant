# Architecture

The numbered notebooks preserve the research sequence; the `intelligent_scada` package owns reusable behavior. Settings owns configuration and paths. The CLI, notebook 08 and API ingestion jobs orchestrate the same Pipeline. There is no agent framework or separate orchestration service.

## Ingestion and provenance

Image extraction/filtering, PDF analysis, text extraction/cleaning, TOC chunking, image linking and embedding write atomic artifacts. Version 1 stage manifests bind source SHA-256, relevant settings, upstream content hashes and required output hashes. Resume reuses only matching checkpoints. Missing dependencies invalidate dependent stages. Manual image review survives matching source images; force requests rebuild automatic decisions.

Production indexing validates source and all upstream checkpoints, ordered chunk content and metadata, finite normalized vectors and model identity before applying schema or replacing rows. Empty/no-TOC/no-text inputs fail before replacement. Notebook 01–06 outputs are exploratory; notebook 07 establishes the production boundary by running the validated pipeline.

Legacy chunking preserves paragraph boundaries, including an oversized paragraph. Targeted chunking bounds body characters before the Section prefix. Both now track the actual pages in each part, including overlap. Section boundaries are retained separately. No OCR or no-TOC fallback is provided.

## Storage and retrieval

PostgreSQL owns documents, chunks, images, chunk-image links, chat sessions and messages. Keys are scoped by document. Ingestion takes a document advisory transaction lock and replaces rows in one transaction; failures roll back replacement. SQL cascades remove dependent records. Filesystem writes remain separate and can survive a failed database stage.

The release schema is fixed to `VECTOR(768)` with an HNSW cosine index. EmbeddingService lazily loads the configured model, pins Hub files to one resolved revision, retains the Section prefix and emits normalized float32 vectors. Retriever locks the document metadata for its compatibility check and query, checks model identity/dimension before encoding, scopes SQL by document and returns cosine similarity. Changing a model or revision requires re-ingestion.

## Routing, answers and memory

DecisionRouter uses deterministic conversational/domain handling first, with an optional typed, bounded JSON classifier fallback. Valid first decisions are reused unless newly loaded follow-up context requires another routing decision. Retrieval scores below the configured floor are removed before generation. No evidence means no answer-model call.

LangChain core prompt/runnable/parser composition remains the answer path. Retrieved text and history are delimited as untrusted evidence. Stable S labels describe the source map; the response citations include only recognized markers used by the answer. Unknown markers produce a safe failure. This validates marker membership, not factual entailment. Provider timeouts, rate limits and malformed responses map to sanitized errors.

Memory off bypasses reads, writes and summaries even with an old session ID. Successful evidence-backed turns can update persistent document-scoped UUID sessions; summary failure does not discard the answer. New conversation does not erase transcripts. No automatic transcript expiry or session-delete UI is implemented.

## API and frontend

One API process/replica and one ingestion worker are required. JobManager reserves each document key under one lock before upload consumption. Admission is bounded by one worker plus the configured pending limit; completed records are pruned to the configured retention count. Unique staged uploads, worker failures and executor failures release reservations; deletion shares the same ownership. Jobs are process-local and disappear on restart.

UploadSizeLimitMiddleware checks both Content-Length and received bytes before multipart spooling exceeds the PDF limit plus 64 KiB overhead. The route separately validates PDF signature, suffix and bytes. An external gateway should enforce the same ingress ceiling.

The React client binds requests, sessions, messages, evidence and images to document identity and conversation generation. Switching, deleting or starting a new conversation invalidates and aborts pending client requests. This does not cancel server work already running. Remote Markdown images and raw HTML are disabled; related images use the document-scoped API and resolved data-root containment.

## Operational boundary

This is a single-user local application without authentication. Supplied host ports bind to loopback; container processes bind internally as needed. Remote exposure requires an authenticated TLS gateway and database isolation. Public failures contain safe messages and IDs; logs retain error classes/stages rather than raw provider/SQL payloads. Runtime responses do not disclose absolute external PDF paths.

CLI deletion removes database records; API deletion also removes the matching upload folder. Primary/manual CLI files and external source PDFs remain deliberate local responsibilities. Providers receive authorized excerpts and, when enabled, selected history. See [configuration](configuration.md), [contracts](data-contracts.md) and [data policy](../data/README.md).
