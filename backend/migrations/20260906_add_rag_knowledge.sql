CREATE EXTENSION IF NOT EXISTS vector;

CREATE TABLE IF NOT EXISTS rag_documents (
    id SERIAL PRIMARY KEY,
    source_uri VARCHAR(512) NOT NULL,
    source_hash VARCHAR(64) NOT NULL,
    version VARCHAR(64) NOT NULL,
    access_scope VARCHAR(32) NOT NULL,
    title VARCHAR(255),
    created_at TIMESTAMP WITHOUT TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITHOUT TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE UNIQUE INDEX IF NOT EXISTS ux_rag_documents_source_hash
    ON rag_documents (source_hash);

CREATE TABLE IF NOT EXISTS rag_chunks (
    id SERIAL PRIMARY KEY,
    document_id INTEGER NOT NULL REFERENCES rag_documents (id),
    chunk_index INTEGER NOT NULL,
    content TEXT NOT NULL,
    content_hash VARCHAR(64) NOT NULL,
    embedding VECTOR(512) NOT NULL,
    created_at TIMESTAMP WITHOUT TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT uq_rag_chunks_document_index UNIQUE (document_id, chunk_index)
);

CREATE INDEX IF NOT EXISTS ix_rag_chunks_document_id
    ON rag_chunks (document_id);

CREATE INDEX IF NOT EXISTS ix_rag_chunks_content_hash
    ON rag_chunks (content_hash);

CREATE TABLE IF NOT EXISTS rag_query_logs (
    id SERIAL PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES users (id),
    ticket_id INTEGER REFERENCES tickets (id),
    access_scope VARCHAR(32) NOT NULL,
    query_summary TEXT NOT NULL,
    hit_document_ids JSON NOT NULL DEFAULT '[]',
    created_at TIMESTAMP WITHOUT TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS ix_rag_query_logs_user_id
    ON rag_query_logs (user_id);

CREATE INDEX IF NOT EXISTS ix_rag_query_logs_ticket_id
    ON rag_query_logs (ticket_id);
