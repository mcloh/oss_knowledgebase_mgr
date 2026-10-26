CREATE EXTENSION IF NOT EXISTS vector;
CREATE EXTENSION IF NOT EXISTS pgcrypto;

CREATE TABLE IF NOT EXISTS raw_documents (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  bucket text NOT NULL,
  object_key text NOT NULL,
  document_type text NOT NULL,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now(),
  UNIQUE (bucket, object_key, document_type)
);

CREATE TABLE IF NOT EXISTS raw_versions (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  document_id uuid NOT NULL REFERENCES raw_documents(id) ON DELETE CASCADE,
  etag text,
  sha256 text NOT NULL,
  content_type text,
  content bytea NOT NULL,
  status text NOT NULL DEFAULT 'raw' CHECK (status IN ('raw','silver','published','failed')),
  created_at timestamptz NOT NULL DEFAULT now(),
  published_at timestamptz,
  UNIQUE (document_id, sha256)
);

CREATE TABLE IF NOT EXISTS silver_chunks (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  version_id uuid NOT NULL REFERENCES raw_versions(id) ON DELETE CASCADE,
  ordinal integer NOT NULL,
  parent_chunk_id uuid REFERENCES silver_chunks(id) ON DELETE CASCADE,
  chunk_kind text NOT NULL CHECK (chunk_kind IN ('section','chunk')),
  heading_path text[] NOT NULL DEFAULT ARRAY[]::text[],
  content text NOT NULL,
  metadata jsonb NOT NULL DEFAULT '{}'::jsonb,
  search_vector tsvector GENERATED ALWAYS AS (to_tsvector('portuguese', content)) STORED,
  UNIQUE (version_id, ordinal)
);
CREATE INDEX IF NOT EXISTS silver_chunks_fts_idx ON silver_chunks USING gin(search_vector);
CREATE INDEX IF NOT EXISTS silver_chunks_parent_idx ON silver_chunks(parent_chunk_id);

CREATE TABLE IF NOT EXISTS gold_enrichments (
  version_id uuid NOT NULL REFERENCES raw_versions(id) ON DELETE CASCADE,
  chunk_id uuid PRIMARY KEY REFERENCES silver_chunks(id) ON DELETE CASCADE,
  enrichment_model text NOT NULL,
  prompt_version text NOT NULL,
  title text NOT NULL,
  summary text NOT NULL,
  keywords text[] NOT NULL DEFAULT ARRAY[]::text[],
  questions text[] NOT NULL DEFAULT ARRAY[]::text[],
  hypothetical_answer text NOT NULL DEFAULT '',
  search_text text NOT NULL,
  search_vector tsvector GENERATED ALWAYS AS (to_tsvector('portuguese', search_text)) STORED,
  embedding vector NOT NULL,
  created_at timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS gold_enrichments_fts_idx ON gold_enrichments USING gin(search_vector);

CREATE TABLE IF NOT EXISTS gold_edges (
  version_id uuid NOT NULL REFERENCES raw_versions(id) ON DELETE CASCADE,
  from_chunk_id uuid NOT NULL REFERENCES silver_chunks(id) ON DELETE CASCADE,
  to_chunk_id uuid NOT NULL REFERENCES silver_chunks(id) ON DELETE CASCADE,
  edge_type text NOT NULL CHECK (edge_type IN ('parent','next','reference')),
  PRIMARY KEY (version_id, from_chunk_id, to_chunk_id, edge_type)
);

-- Crie o índice após definir a dimensão do modelo. Exemplo para 384 dimensões:
-- CREATE INDEX gold_enrichments_hnsw_idx ON gold_enrichments USING hnsw (embedding vector_cosine_ops);
-- O PostgreSQL exige vetor de dimensão fixa para o índice. A tabela aceita dimensões
-- configuráveis; em produção, mantenha uma coleção/banco por dimensão ou fixe a dimensão
-- no DDL e recrie o índice ao trocar de modelo.
