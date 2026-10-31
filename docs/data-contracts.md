# Data contracts

These contracts preserve the original notebook field names. JSON page values are one-based
physical PDF page numbers. Additional fields require a documented compatibility change.

## Image manifest

One record per successfully extracted embedded image:

```json
{
  "filename": "page0048_img001_w1278_h0576.png",
  "page": 48,
  "img_index": 1,
  "xref": 302,
  "width": 1278,
  "height": 576,
  "source_ext": "png",
  "file_size_bytes": 306688,
  "md5": "hexadecimal-source-image-digest"
}
```

The MD5 value preserves the original duplicate-detection behavior. It is not used as a security
checksum.

## Filter manifest

Automatic filtering adds:

```json
{"decision": "keep", "reasons": []}
```

Allowed decisions are `keep`, `discard`, and `missing`. Manual review uses
`"source": "manual_review"`; `reasons` is optional so historical manifests remain readable.

## PDF structure

Top-level fields:

| Field | Type | Meaning |
|---|---|---|
| `total_pages` | integer | Physical PDF page count |
| `toc_entries` | integer | Number of built-in TOC entries |
| `toc` | array | `{level, title, page}` records |
| `empty_pages` | integer array | Pages with no extracted text |
| `page_stats` | array | Page length/first-line/last-line diagnostics |
| `heading_candidates_count` | integer | Exploratory regex candidate count |

## Raw pages

```json
{
  "page": 50,
  "raw_text": "...",
  "raw_char_count": 2094,
  "raw_word_count": 350
}
```

## Clean pages

Clean records retain every raw field and add:

| Field | Type |
|---|---|
| `clean_text` | string |
| `clean_char_count` | integer |
| `clean_word_count` | integer |
| `removed_lines` | string array |
| `has_text` | boolean |

Only exact configured header/footer lines and matching page-number lines are removed. Internal
line breaks, non-breaking spaces, hyphenation, warnings, and chapter labels are preserved.

## Text chunks

```json
{
  "chunk_id": "chunk_000000",
  "chunk_index": 0,
  "text": "Section: Safety Precautions\n\n...",
  "char_count": 1773,
  "word_count": 260,
  "page_start": 33,
  "page_end": 34,
  "source_pages": [33, 34],
  "toc_level": 1,
  "section_title": "Safety Precautions",
  "section_path": ["Safety Precautions"],
  "section_start_page": 33,
  "section_end_page": 34,
  "part_index": 1,
  "part_count": 1
}
```

`source_pages`, `page_start` and `page_end` describe text actually present in each part, including overlap; section start/end retain the parent section span. Legacy paragraphs may exceed the body maximum; targeted splitting bounds the body before the Section prefix. Empty/no-TOC/no-extractable-text inputs are rejected.

`chunk_index` is zero-based; `part_index` is one-based. The section path is included in the
embedding input through the `Section:` prefix.

## Chunk-image links

One link record exists per chunk, including chunks with zero images. Each nested image contains
`filename`, `page`, `width`, `height`, and `file_size_bytes`.

## Embeddings

- `chunk_embeddings.npy`: two-dimensional `float32` array.
- `chunk_embeddings_metadata.json`: row-aligned metadata records.
- `embedding_run.json` (artifact version 2): model name, requested/resolved revision and identity, dimension, normalization, dtype, count, UTC timestamp, ordered chunk-ID and ID/text digests, vector-file SHA-256 and metadata-file SHA-256.

Version 1 stage manifests under `manifests/` bind relevant settings, source SHA-256, upstream content hashes and every required output. Missing/stale/unsigned checkpoints are not reusable. Production indexing validates all dependencies and embedding provenance before SQL replacement.

Embedding rows and chunks must have equal counts, the configured dimension, and sequential
`chunk_index` values. Metadata must match every ordered chunk, vectors must be finite normalized float32, and the schema dimension is fixed to 768. Model identity is checked before retrieval.

## Retrieval result

```json
{
  "chunk_id": "chunk_000123",
  "text": "...",
  "page_start": 500,
  "page_end": 501,
  "source_pages": [500, 501],
  "section_title": "Adding a diagram",
  "section_path": ["Configure", "Web Applications", "Adding a diagram"],
  "score": 0.82
}
```

`score` is cosine similarity computed as `1 - cosine_distance`.
The RAG service keeps only results at or above `SCADA_MIN_RETRIEVAL_SCORE` for answer evidence.

## Citation

```json
{
  "source_id": "S1",
  "chunk_id": "chunk_000123",
  "label": "Configure > Web Applications > Adding a diagram — pp. 500-501",
  "page_start": 500,
  "page_end": 501,
  "section_path": ["Configure", "Web Applications", "Adding a diagram"]
}
```

Recognized `[S1]` and grouped `[S1, S2]` markers must belong to the supplied source map. Unknown markers trigger a safe failure. `citations` includes only markers actually used; `sources` lists retrieved evidence. No-marker answers have no citations. This does not prove factual support.

## Answer response

The service returns `answer`, `citations`, `sources`, `related_images`, `session_id`, and
`routing`. Routing includes `intent`, `requires_retrieval`, `needs_images`, and `is_followup`
alongside the existing retrieval controls. Direct responses have empty source/citation/image
arrays. Images are metadata references only; they are not sent to the answer model.

## FastAPI contracts

The canonical machine-readable contract is `/api/openapi.json`. Pydantic rejects unknown
request fields for JSON models and validates bounds before service code runs.

### Upload request

`POST /api/v1/documents/upload` uses `multipart/form-data`:

| Field | Type | Required | Meaning |
|---|---|---:|---|
| `file` | PDF file | yes | Source manual; validated by suffix, signature, and size |
| `document_name` | string | no | Display name; defaults to PDF stem |
| `document_key` | string | no | Stable lowercase key; defaults from the name |
| `include_images` | boolean | no | Extract/filter/link embedded images; default `true` |
| `resume` | boolean | no | Reuse valid existing stage outputs; default `false` |
| `force` | boolean | no | Regenerate outputs despite resume; default `false` |

Document keys contain 1–80 lowercase letters/digits separated by single hyphens; names have 1–200 characters. The response is HTTP 202 with a job record. Atomic ownership conflicts return 409; full admission returns 503. The ingress body limit is the PDF byte ceiling plus 64 KiB multipart overhead, including chunked requests; oversized bodies return 413.

### Ingestion job

```json
{
  "job_id": "7ab77d90-c531-499b-83d1-cef695d9a061",
  "document_key": "controller-guide",
  "document_name": "Controller Guide",
  "status": "running",
  "stage": "chunking",
  "progress": 0.5,
  "message": "Building TOC-aware semantic chunks",
  "created_at": "2026-08-01T10:00:00Z",
  "started_at": "2026-08-01T10:00:01Z",
  "finished_at": null,
  "result": null,
  "error": null
}
```

Allowed status values are `queued`, `running`, `succeeded`, and `failed`. `result` uses the
pipeline summary after success. `error` is a generic failure message only after failure. Logs use the job ID, stage and error class without echoing raw exception payloads. Successful summaries use the PDF basename, not its absolute host path.

### Document summary

Document list entries contain `document_key`, `document_name`, `source_filename`,
`embedding_model`, `embedding_dimension`, `chunk_count`, `image_count`, `created_at`, and
`updated_at`. The API adds `is_default` so clients can mark the primary manual without
hard-coding its key.

### Ask request

```json
{
  "question": "How is the controller configured?",
  "document_key": null,
  "session_id": null,
  "memory_enabled": true,
  "include_images": true,
  "top_k": 6
}
```

`document_key` is optional/null for the primary Power SCADA manual. Send an explicit key only
when querying another indexed manual. Session identifiers must be UUIDs; invalid identifiers return 422 before SQL. Memory off bypasses all memory reads/writes/summaries, including with an old session ID. The response is the existing answer contract.
`related_images` contain metadata; the frontend constructs a document-scoped image endpoint URL
rather than trusting an arbitrary path.

### Runtime readiness

`GET /api/v1/health` reports database, answer-provider, default-PDF, default-document, and
knowledge-base state without exposing secrets. `GET /api/v1/runtime` exposes the safe default
manual identity/path and retrieval threshold so the frontend can describe real configuration.

### Error envelope

Unhandled and validation errors use:

```json
{
  "error": {
    "code": "validation_error",
    "message": "body.question: Field required",
    "request_id": "de820b65-e033-42cb-b257-3a7c5d48673c"
  }
}
```

Framework-generated HTTP errors may use FastAPI's standard `detail` field; the frontend API
client handles both shapes. Provider errors are sanitized: malformed/upstream failures map to 502, rate limits/unavailability to 503, and timeouts to 504.

## Database records

The database adds a `documents` record and internal numeric `document_id`. Existing `chunk_id`
and `filename` values are preserved and become composite document-scoped keys. See
`database/schema.sql` for exact types, constraints, indexes, and cascade behavior.
