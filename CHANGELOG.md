# Changelog

The numbered sections below describe supplied candidate milestones, not verified published tags or release dates.

## Unreleased

- Added source/settings/output provenance and validated indexing, actual chunk part-page spans, model revision compatibility, and empty-input protection.
- Added atomic bounded job admission, upload limits, safe errors, local deployment defaults, UUID/configuration guards and document-safe frontend responses.
- Corrected memory-off behavior, summary failure isolation, citation validation, router types/vocabulary and provider response handling.
- Removed runtime/manual-derived publication artifacts; preserved eight clean notebooks and the historical diagram.
- Added synthetic and database regressions, schema parity, configuration documentation and corrected schema graphics.
- Patched the compatible nanoid dependency resolution and documented source-only/full-UI builds.

## 0.3.1 - Production polish

### Changed

- Centralized document scoping, database-schema resolution, embedding construction, and
  notebook environment reload behavior through `intelligent_scada.config.Settings`.
- Standardized the eight pipeline notebooks as production-module demonstrations.
- Refined the SCADA specialist prompt for concise Markdown, strict source grounding, safety,
  and natural courtesy without rigid domain-refusal phrasing.
- Expanded deterministic conversational routing for common English, Arabic, and German-style
  greetings and small talk while keeping embeddings and pgvector entirely bypassed.
- Upgraded answer rendering with GitHub-flavored Markdown, tables, grouped citations, and
  syntax-highlighted code blocks.
- Shifted the interface accent from purple to a restrained industrial blue/teal palette and
  removed frontend fallbacks for backend-configured retrieval and upload limits.
- Split Markdown highlighting into a cached production bundle and disabled public source maps.

### Fixed

- Corrected notebook 08's TOC count display (`toc_entries` is an integer, not a list).
- Removed duplicated database schema path construction from the pipeline, API, CLI, jobs, and
  notebooks.

## 0.3.0 - Power SCADA default experience

### Added

- Central primary-manual identity/path configuration for **Power SCADA Operation 2020 System
  Guide**, with normal chat defaulting to its stable document key.
- `notebooks/08_prepare_power_scada_manual.ipynb`, which orchestrates the production pipeline,
  idempotent pgvector indexing, retrieval verification, and an optional RAG smoke test.
- Deterministic conversational routing for greetings, thanks, assistant questions, noise,
  abuse-only messages, out-of-scope requests, technical image intent, and contextual follow-ups.
- Configurable retrieval evidence floor (`SCADA_MIN_RETRIEVAL_SCORE`) and no-evidence responses
  that do not fabricate citations or invoke the answer model.
- Truthful default-manual/runtime readiness fields and a Vite-ready `valve-101.png` asset hook.
- Warm neutral React chat redesign with InteractiveDots, default-manual badges, secondary manual
  uploads, responsive source evidence, and inline related-image previews.

### Preserved

- The original seven notebooks, artifact field names, chunking behavior, MPNet 768-dimensional
  embeddings, pgvector HNSW retrieval, document isolation, uploads, image links, sessions,
  LangChain answer composition, CLI, FastAPI, and Docker/PostgreSQL workflows.

### Intentional behavior changes

- `/api/v1/chat/ask` now accepts an omitted `document_key` and resolves the configured primary
  manual in `RAGService`.
- Obvious nontechnical messages no longer create query embeddings, search pgvector, or return
  citations. Optional router-model calls are limited to ambiguous messages.
- Retrieved chunks below the configured evidence threshold are excluded before generation.
- The default manual cannot be mistaken for an upload prerequisite in the frontend; additional
  PDF ingestion is presented as an optional secondary action.
- Document/readiness counts now use per-document indexed counts instead of a chunk/image
  Cartesian join; returned document-summary fields and counts are unchanged.

## 0.2.0 - Complete web application

### Added

- FastAPI application factory, versioned routes, Pydantic HTTP contracts, OpenAPI docs, request
  IDs, security headers, CORS configuration, and health/runtime endpoints.
- Validated PDF uploads and isolated per-document artifact directories.
- Background ingestion jobs with live stage progress. Atomic admission and bounded retention are recorded under Unreleased.
- Document listing/deletion, chat, transcript, and DB-authorized image endpoints.
- LangChain `ChatPromptTemplate`, runnable, and output-parser execution for answers and memory
  summaries while retaining the existing provider adapter.
- React/TypeScript/Vite frontend with responsive navigation, manual management, ingestion
  progress, chat controls, citation evidence, and visual-reference lightbox.
- Multi-stage production Docker image and full API/PostgreSQL Compose stack.
- FastAPI, upload, and LangChain chain tests.

### Preserved

- Existing artifact field names, filenames, page numbering, chunk rules, embedding model,
  retrieval SQL, answer prompts, citation formatting, and database replacement semantics.
- All original notebooks and their production-module demonstrations.

### Operational notes

- API-created artifacts now live under `data/documents/<document-key>/`; direct CLI artifact
  paths retain their previous layout.
- Ingestion progress records are process-local and are not a durable job queue.
- The frontend requires a build step locally; Docker performs it automatically and Python
  package builds include the static bundle only when it has been built first.

## 0.1.0 - Production refactor

### Added

- `src/intelligent_scada` package with typed settings and contracts.
- Atomic artifact I/O and resumable pipeline orchestration.
- Individual-stage and end-to-end CLI commands.
- Focused unit tests and a cleaned-pages-to-records integration test.
- Document-scoped PostgreSQL schema, transactions, HNSW index, and deletion strategy.
- Semantic retrieval, citations, grounded answer generation, routing, memory, and image lookup.
- Modern packaging, Docker, Docker Compose, environment template, and developer documentation.

### Preserved

- Original notebook terminology and numbered processing order.
- JSON field names and one-based physical page numbering.
- Image filename format and filtering thresholds.
- Light text-cleaning rules.
- `Section:` embedding prefix, embedding model, dimension, normalization, and batch size.
- Page-overlap image links.
- Legacy chunking as the default compatibility strategy.
- All seven original notebook files, refactored as production-module demonstrations.

### Intentional behavior changes

- Page-number cleaning now accepts any `Page X of Y`, not only `Y=1314`.
- Automatic filtering removes a stale copy from the opposite review folder.
- Extraction failures are logged with page/index details instead of silently ignored.
- Artifact writes are atomic.
- Embedding runs record model and ordered-chunk provenance.
- Database keys are scoped by document; re-ingestion is a single replace transaction.
- Chunk section boundaries and part fields are retained in the database.
- A real cosine HNSW index is created.
- New application code provides the RAG path; the unavailable earlier RAG notebook was not reconstructed.

### Known compatibility notes

- The new database schema requires re-ingestion from the legacy single-document schema.
- `targeted` chunking changes chunk counts/IDs and must be selected explicitly.
- Answer prompts are new because the deleted RAG notebook was unavailable.
