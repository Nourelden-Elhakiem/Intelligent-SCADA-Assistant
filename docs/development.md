# Development and release validation

Use Python 3.11–3.13, Node.js 20+, Git and PostgreSQL 16 with pgvector. A GPU is optional; the initial model download requires network access. Work from the repository root. Use authorized source data and a dedicated test database.

## Install

Bash:

```bash
python -m venv .venv
source .venv/bin/activate
python -m pip install -e '.[dev]'
cp .env.example .env
```

PowerShell:

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -e ".[dev]"
Copy-Item .env.example .env
```

Use the machine's normal local script policy for activation; no global bypass is required. Set private settings as described in [configuration](configuration.md). Start PostgreSQL with `docker compose up -d postgres` after setting an explicit password, then run `intelligent-scada init-db`.

## CLI reference

Global options precede the subcommand: `--data-dir PATH`, `--log-level LEVEL`. Use one data root per document. Run `intelligent-scada COMMAND --help` for parser help.

| Command | Arguments and options |
|---|---|
| `ingest` | `PDF`, `--document-name`, `--document-key`, `--resume`, `--force`, `--skip-images`, `--skip-index` |
| `extract-images` | `PDF`, `--resume`, `--force` |
| `analyze-pdf` | `PDF`, `--resume`, `--force` |
| `extract-text` | `PDF`, `--resume`, `--force` |
| `chunk` | `CLEAN_PAGES --structure STRUCTURE`, optional `--output`, `--strategy legacy\|targeted` |
| `link-images` | optional `--chunks`, `--manifest` |
| `embed` | optional `CHUNKS` |
| `init-db` | optional `--schema` |
| `index` | `PDF`, `--document-name`, `--document-key`, `--no-replace` |
| `ask` | `QUESTION`, `--document-key`, `--session-id`, `--no-memory`, `--images`, `--top-k`, `--json` |
| `delete-document` | `DOCUMENT_KEY` (database/cascades only) |
| `serve` | `--host`, `--port`, `--reload`, `--workers` (must be one) |

```bash
intelligent-scada --data-dir data/documents/controller-guide ingest /path/to/authorized.pdf --document-name 'Controller Guide' --document-key controller-guide --resume
intelligent-scada ask 'How are alarms configured?' --document-key controller-guide --no-memory --json
```

Production `index` requires matching source/dependent stage provenance and embedding metadata. Running `ingest --resume` is the supported way to rebuild unsigned/stale notebook artifacts. Custom chunk exports are exploratory and do not by themselves establish production stage provenance. `--no-replace` additionally requires the same source hash/model/dimension as existing data. Legacy single-document schemas require backup and deliberate re-ingestion; `database/reset.sql` destroys data and is never an automatic upgrade.

## Tests and checks

```bash
pytest
ruff check .
mypy
python -m compileall -q src
```

Tests use synthetic PDFs/text and fake provider/model boundaries. SPA tests create their own tiny temporary frontend fixtures and also verify the honest source-only fallback. No private manual, downloaded model or checked-in static build is needed for unit tests.

For database validation, use a dedicated disposable PostgreSQL/pgvector database:

```bash
export TEST_PG_CONN_STR='postgresql://test_user:YOUR_URL_ENCODED_PASSWORD@127.0.0.1:5433/scada_test'
pytest -m database
```

PowerShell uses `$env:TEST_PG_CONN_STR = '...'`. The integration tests apply the schema, use unique synthetic document keys, and clean their own records. They assert persisted replacement, unchanged data on failed/empty ingestion, rollback, document isolation, real cosine SQL ordering and transcript cascades. Do not point them at a production database. Without this variable, database checks are explicitly skipped.

## Frontend and packaging

```bash
cd frontend
npm ci
npm run typecheck
npm run build
npm audit
cd ..
python -m build
```

Vite writes to `src/intelligent_scada/static/`. Build it before the Python wheel for a full UI package. A wheel built without these generated files is backend-only and serves the root setup response. Neither generated static assets, dependency directories nor TypeScript build caches belong in the source snapshot. Docker's two stages perform the frontend build automatically.

For local UI development run `npm run dev` in `frontend` alongside `intelligent-scada serve`; Vite proxies API requests to the local backend. Dev/preview bind to loopback. Test delayed answers while switching documents, starting a new conversation and completing uploads; stale answers and session IDs must not cross conversations. Test source/image identity, upload selection errors and keyboard modal dismissal.

Install each release wheel in a fresh environment and run imports, CLI help, packaged SQL lookup and root/API behavior from outside the checkout. Verify the full wheel contains index/assets/icon and the backend-only wheel returns setup guidance. Run `python -m pip check`. Record the tested dependency environment; it is evidence, not a fabricated lockfile.

## Notebooks, privacy and release checks

Keep all [eight notebooks](../notebooks/README.md), with zero outputs and null execution counts. Compile every code cell and execute the sequence against a small authorized synthetic bookmarked PDF and disposable database. Notebook 08's external provider call remains explicit opt-in. Compare schema SQL ignoring heading comments and render the editable database diagram when SQL changes.

Before publication compare every approved path and SHA-256, verify exclusions, inspect all EDIT decisions, scan tracked content for credentials/absolute machine paths/manual derivatives, validate local documentation links and ensure the original research lineage remains. Do not publish runtime outputs or generated packaging artifacts in the repository. The optional GIF remains outside the core snapshot until separately supplied and reviewed.

Docker release checks require an available daemon: validate Compose interpolation with a private non-placeholder password, build/run the stack, verify DB health, loopback ports, non-root API and SPA. Provider credentials, real model downloads, Windows execution and private-manual evaluation require their respective environments; report unavailable checks as unverified rather than suppressing failures.
