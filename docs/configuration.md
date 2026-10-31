# Configuration

`Settings` is the canonical configuration owner. Copy `.env.example` to a private `.env`; never commit credentials, source manuals or derivatives.

## Paths and precedence

An explicit `project_root` argument wins. Otherwise the process `SCADA_PROJECT_ROOT` or current working directory chooses the initial root. Exactly one `.env` is loaded from that root (or the explicit env_file). Process variables win by default. If no explicit root was passed, that file can relocate the root when no process root exists; `env_override=True` also permits its root to override the process root. A relocated root does not trigger loading another `.env`.

Notebooks explicitly use `env_override=True` to reload their local configuration. CLI/API use process precedence. Relative `SCADA_DATA_DIR` and `--data-dir` resolve against the resolved project root. Relative `SCADA_DEFAULT_PDF_PATH` also resolves against the project root; an absolute override can point to an authorized external PDF. Primary-manual notebooks call `require_default_pdf()`. A safe runtime hint returns a relative path or basename, not an absolute external host path.

CLI stages use one selected root per document. Uploads create isolated roots under `data/documents/<key>/`. `SCADA_PDF_FILENAME` accepts only a basename; use the default-PDF override for paths.

## Environment reference

Defaults below describe application settings unless identified as Compose-only. Empty provider values permit ingestion and direct conversational replies but cannot generate a grounded answer. Boolean values `1`, `true`, `yes`, `on` enable a flag; other values disable it. Comma-separated CORS origins are trimmed. Provider aliases apply only when the corresponding SCADA value is empty.

| Variable | Default / purpose |
|---|---|
| `GEMINI_API_KEY` | `legacy answer key fallback` |
| `GEMINI_BASE_URL` | `legacy answer URL fallback` |
| `GEMINI_MODEL` | `legacy answer model fallback` |
| `HF_TOKEN` | `unset; optional private Hub access` |
| `OPENROUTER_API_KEY` | `legacy router key fallback` |
| `OPENROUTER_BASE_URL` | `legacy router URL fallback` |
| `OPENROUTER_MODEL` | `legacy router model fallback` |
| `PG_CONN_STR` | `unset; database required for indexing/retrieval/memory` |
| `POSTGRES_PASSWORD` | `required by Compose; no default` |
| `POSTGRES_PORT` | `5433 (Compose host port)` |
| `SCADA_ANSWER_API_KEY` | `unset; provider secret` |
| `SCADA_ANSWER_BASE_URL` | `unset; OpenAI-compatible base URL` |
| `SCADA_ANSWER_MODEL` | `gemini-2.5-flash` |
| `SCADA_API_HOST` | `127.0.0.1` |
| `SCADA_API_PORT` | `8000` |
| `SCADA_API_RELOAD` | `False` |
| `SCADA_API_WORKERS` | `1` |
| `SCADA_AUTO_INIT_DB` | `True` |
| `SCADA_BLANK_BRIGHTNESS_HIGH` | `245.0` |
| `SCADA_BLANK_BRIGHTNESS_LOW` | `10.0` |
| `SCADA_BLANK_STD_THRESHOLD` | `5.0` |
| `SCADA_CHUNKING_STRATEGY` | `legacy` |
| `SCADA_CHUNK_MAX_SIZE` | `3500` |
| `SCADA_CHUNK_OVERLAP` | `200` |
| `SCADA_CHUNK_TARGET_SIZE` | `2500` |
| `SCADA_CORS_ORIGINS` | `('http://localhost:3000', 'http://localhost:5173')` |
| `SCADA_DATA_DIR` | `<project root>/data` |
| `SCADA_DEFAULT_DOCUMENT_KEY` | `slug of default document name` |
| `SCADA_DEFAULT_DOCUMENT_NAME` | `Power SCADA Operation 2020 System Guide` |
| `SCADA_DEFAULT_PDF_PATH` | `data/pdf/Power SCADA Operation 2020 System Guide.pdf` |
| `SCADA_DEFAULT_TOP_K` | `6` |
| `SCADA_DOCUMENT_KEY` | `slug of document name` |
| `SCADA_DOCUMENT_NAME` | `default document name` |
| `SCADA_EMBEDDING_BATCH_SIZE` | `64` |
| `SCADA_EMBEDDING_DIMENSION` | `768` |
| `SCADA_EMBEDDING_MODEL` | `sentence-transformers/all-mpnet-base-v2` |
| `SCADA_EMBEDDING_REVISION` | `unset; resolved Hub commit recorded` |
| `SCADA_INGESTION_WORKERS` | `1` |
| `SCADA_LOG_LEVEL` | `INFO` |
| `SCADA_MAX_PENDING_JOBS` | `4` |
| `SCADA_MAX_TOP_K` | `12` |
| `SCADA_MAX_UPLOAD_MB` | `250` |
| `SCADA_MEMORY_SUMMARY_THRESHOLD` | `12` |
| `SCADA_MIN_COMBINED_HEIGHT` | `150` |
| `SCADA_MIN_COMBINED_WIDTH` | `200` |
| `SCADA_MIN_IMAGE_HEIGHT` | `80` |
| `SCADA_MIN_IMAGE_WIDTH` | `80` |
| `SCADA_MIN_RETRIEVAL_SCORE` | `0.25` |
| `SCADA_OUTPUT_IMAGE_FORMAT` | `png` |
| `SCADA_PDF_FILENAME` | `primary PDF basename (legacy stage setting)` |
| `SCADA_PROJECT_ROOT` | `current working directory` |
| `SCADA_RETAINED_JOBS` | `100` |
| `SCADA_ROUTER_API_KEY` | `unset; provider secret` |
| `SCADA_ROUTER_BASE_URL` | `unset; OpenAI-compatible base URL` |
| `SCADA_ROUTER_ENABLED` | `False` |
| `SCADA_ROUTER_MODEL` | `openai/gpt-4.1-mini` |

## Constraints and model identity

The schema is fixed at 768 dimensions. Batch size and summary threshold must be positive; `1 <= default_top_k <= max_top_k <= 100`; scores lie in [-1, 1]. Chunk target is positive and no greater than maximum; overlap is nonnegative and smaller than maximum. Legacy chunking preserves oversized paragraphs; targeted bounds body characters before the Section prefix.

Document keys have 1–80 lowercase letters/digits separated by single hyphens. Names have 1–200 nonblank characters. Session IDs must be UUIDs. Port range is 1–65535. API workers and ingestion workers must both equal one, including CLI overrides; pending-job, completed-record and upload limits are positive. Use a single process and replica, since jobs are process-local.

Hub models must expose a root `config.json`; its immutable snapshot commit is resolved before loading all model files and saved in the embedding identity. Pin `SCADA_EMBEDDING_REVISION` for reproducible installs. Local model directories should use an immutable explicit revision identifier and must not be changed in place. A model/revision mismatch requires re-ingestion, even if both models have 768 dimensions.

## Database and local exposure

Compose requires an explicit non-placeholder `POSTGRES_PASSWORD` and rejects common template placeholders. Use a URL-safe password for Compose's interpolated API URI. Local `PG_CONN_STR` uses host port **5433** (or `POSTGRES_PORT`); the container connection uses **postgres:5432**. For a separately managed server, use its actual port. URL-encode passwords in manually constructed URIs; keep the raw PostgreSQL password consistent with the decoded URI value. Never paste real connection strings into shared logs.

Compose publishes database and API only on 127.0.0.1. The API listens on 0.0.0.0 inside its container. Vite dev/preview bind to loopback. Exposing these services remotely requires an authenticated TLS gateway and appropriate firewall/CORS settings; CORS is not authentication. Do not raise API worker/replica counts. A gateway should cap upload bodies at the PDF limit plus 64 KiB multipart overhead.

Provider URLs, keys and models must match your chosen service. Questions, selected manual excerpts and memory context can leave the machine through configured providers. Notebook 08 requires explicit `RUN_PROVIDER_SMOKE=True` before its optional external call. No credentials alone trigger that notebook smoke test.

Cleaning patterns, image filename templates and skipped-section tuples retain their Settings defaults and can be passed through Python Settings construction; no undocumented environment overrides are implied.
