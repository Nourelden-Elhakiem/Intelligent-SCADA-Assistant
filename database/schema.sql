-- Intelligent SCADA Assistant - PostgreSQL + pgvector schema
-- Safe for repeated execution on a fresh/refactored database.

CREATE EXTENSION IF NOT EXISTS vector;

DO $$
BEGIN
    IF to_regclass('public.chunks') IS NOT NULL
       AND NOT EXISTS (
           SELECT 1 FROM information_schema.columns
           WHERE table_schema = 'public'
             AND table_name = 'chunks'
             AND column_name = 'document_id'
       ) THEN
        RAISE EXCEPTION
            'Legacy SCADA schema detected. Re-ingest after running database/reset.sql.';
    END IF;
END $$;

CREATE TABLE IF NOT EXISTS documents (
    id BIGSERIAL PRIMARY KEY,
    document_key TEXT UNIQUE NOT NULL,
    document_name TEXT NOT NULL,
    source_filename TEXT NOT NULL,
    source_sha256 TEXT,
    embedding_model TEXT NOT NULL,
    embedding_dimension INTEGER NOT NULL CHECK (embedding_dimension > 0),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS chunks (
    id BIGSERIAL PRIMARY KEY,
    document_id BIGINT NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
    chunk_id TEXT NOT NULL,
    chunk_index INTEGER NOT NULL,
    text TEXT NOT NULL,
    page_start INTEGER,
    page_end INTEGER,
    source_pages JSONB NOT NULL DEFAULT '[]'::jsonb,
    toc_level INTEGER,
    section_title TEXT,
    section_path JSONB NOT NULL DEFAULT '[]'::jsonb,
    section_start_page INTEGER,
    section_end_page INTEGER,
    part_index INTEGER NOT NULL DEFAULT 1,
    part_count INTEGER NOT NULL DEFAULT 1,
    char_count INTEGER,
    word_count INTEGER,
    embedding VECTOR(768),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (document_id, chunk_id)
);

CREATE TABLE IF NOT EXISTS images (
    id BIGSERIAL PRIMARY KEY,
    document_id BIGINT NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
    filename TEXT NOT NULL,
    page INTEGER,
    width INTEGER,
    height INTEGER,
    file_size_bytes INTEGER,
    image_path TEXT,
    md5 TEXT,
    decision TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (document_id, filename)
);

CREATE TABLE IF NOT EXISTS chunk_images (
    id BIGSERIAL PRIMARY KEY,
    document_id BIGINT NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
    chunk_id TEXT NOT NULL,
    image_filename TEXT NOT NULL,
    link_reason TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (document_id, chunk_id, image_filename),
    FOREIGN KEY (document_id, chunk_id)
        REFERENCES chunks(document_id, chunk_id) ON DELETE CASCADE,
    FOREIGN KEY (document_id, image_filename)
        REFERENCES images(document_id, filename) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS chat_sessions (
    session_id UUID PRIMARY KEY,
    document_id BIGINT NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
    summary TEXT NOT NULL DEFAULT '',
    memory_enabled BOOLEAN NOT NULL DEFAULT TRUE,
    useful_message_count INTEGER NOT NULL DEFAULT 0,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS chat_messages (
    id BIGSERIAL PRIMARY KEY,
    session_id UUID NOT NULL REFERENCES chat_sessions(session_id) ON DELETE CASCADE,
    role TEXT NOT NULL CHECK (role IN ('user', 'assistant')),
    content TEXT NOT NULL,
    is_context_useful BOOLEAN NOT NULL DEFAULT TRUE,
    citations JSONB NOT NULL DEFAULT '[]'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS chunks_document_idx ON chunks(document_id, chunk_index);
CREATE INDEX IF NOT EXISTS images_document_page_idx ON images(document_id, page);
CREATE INDEX IF NOT EXISTS chat_messages_session_idx
    ON chat_messages(session_id, created_at DESC);
CREATE INDEX IF NOT EXISTS chunks_embedding_hnsw_idx
    ON chunks USING hnsw (embedding vector_cosine_ops);
