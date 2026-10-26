from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from typing import Any

import psycopg

from oss_kbdb.domain.models import Chunk, Enrichment, SearchHit


class PostgresRepository:
    def __init__(self, dsn: str, *, fts_language: str = "portuguese", schema_name: str | None = None) -> None:
        self._conn = psycopg.connect(dsn)
        if schema_name:
            with self._conn.cursor() as cur:
                cur.execute(__import__('psycopg').sql.SQL('SET search_path TO {}, public').format(__import__('psycopg').sql.Identifier(schema_name)))
        self._fts_language = fts_language

    def close(self) -> None:
        self._conn.close()

    def ingest_raw(self, *, bucket: str, key: str, content: bytes, etag: str | None,
                   content_type: str | None, document_type: str) -> tuple[str, str, bool]:
        sha256 = hashlib.sha256(content).hexdigest()
        with self._conn.cursor() as cur:
            cur.execute("""
                INSERT INTO raw_documents (bucket, object_key, document_type)
                VALUES (%s, %s, %s)
                ON CONFLICT (bucket, object_key, document_type) DO UPDATE SET updated_at = now()
                RETURNING id
            """, (bucket, key, document_type))
            document_id = str(cur.fetchone()[0])
            cur.execute("SELECT id FROM raw_versions WHERE document_id=%s AND sha256=%s", (document_id, sha256))
            row = cur.fetchone()
            if row:
                self._conn.commit(); return document_id, str(row[0]), False
            cur.execute("""
                INSERT INTO raw_versions (document_id, etag, sha256, content_type, content)
                VALUES (%s,%s,%s,%s,%s) RETURNING id
            """, (document_id, etag, sha256, content_type, content))
            version_id = str(cur.fetchone()[0])
        self._conn.commit()
        return document_id, version_id, True

    def replace_silver(self, version_id: str, chunks: list[Chunk], metadata: dict[str, Any] | None = None) -> list[str]:
        ids: dict[int, str] = {}
        with self._conn.cursor() as cur:
            cur.execute("DELETE FROM silver_chunks WHERE version_id=%s", (version_id,))
            for chunk in chunks:
                parent_id = ids.get(chunk.parent_ordinal) if chunk.parent_ordinal is not None else None
                cur.execute("""
                    INSERT INTO silver_chunks (version_id, ordinal, parent_chunk_id, chunk_kind, heading_path, content, metadata)
                    VALUES (%s,%s,%s,%s,%s,%s,%s) RETURNING id
                """, (version_id, chunk.ordinal, parent_id, chunk.kind, list(chunk.heading_path), chunk.content,
                      json.dumps(metadata or {})))
                ids[chunk.ordinal] = str(cur.fetchone()[0])
        self._conn.commit()
        return [ids[c.ordinal] for c in chunks if c.kind == "chunk"]

    def publish_gold(self, *, version_id: str, enrichments: list[Enrichment], child_ids: list[str],
                     vectors: list[list[float]]) -> None:
        if len(child_ids) != len(vectors) or len(child_ids) != len(enrichments):
            raise ValueError("quantidade de chunks e embeddings diverge")
        with self._conn.cursor() as cur:
            cur.execute("DELETE FROM gold_enrichments WHERE version_id=%s", (version_id,))
            for chunk_id, enrichment, vector in zip(child_ids, enrichments, vectors, strict=True):
                cur.execute("""
                    INSERT INTO gold_enrichments
                    (version_id,chunk_id,enrichment_model,prompt_version,title,summary,keywords,questions,hypothetical_answer,search_text,embedding)
                    VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s::vector)
                """, (version_id, chunk_id, enrichment.model, enrichment.prompt_version, enrichment.title,
                      enrichment.summary, list(enrichment.keywords), list(enrichment.questions), enrichment.hypothetical_answer,
                      enrichment.search_text, "[" + ",".join(map(str, vector)) + "]"))
            cur.execute("""
                INSERT INTO gold_edges (version_id, from_chunk_id, to_chunk_id, edge_type)
                SELECT %s, child.id, parent.id, 'parent'
                FROM silver_chunks child JOIN silver_chunks parent ON parent.id=child.parent_chunk_id
                WHERE child.version_id=%s AND child.chunk_kind='chunk'
            """, (version_id, version_id))
            cur.execute("""
                INSERT INTO gold_edges (version_id, from_chunk_id, to_chunk_id, edge_type)
                SELECT %s, current.id, following.id, 'next'
                FROM silver_chunks current
                JOIN silver_chunks following
                  ON following.parent_chunk_id=current.parent_chunk_id AND following.ordinal=current.ordinal+1
                WHERE current.version_id=%s AND current.chunk_kind='chunk'
            """, (version_id, version_id))
            cur.execute("UPDATE raw_versions SET status='published', published_at=%s WHERE id=%s",
                        (datetime.now(timezone.utc), version_id))
        self._conn.commit()

    def search(self, query: str, *, mode: str, document_type: str | None, vector: list[float] | None,
               limit: int = 10, rrf_k: int = 60) -> list[SearchHit]:
        if mode not in {"lexical", "semantic", "hybrid"}:
            raise ValueError("mode deve ser lexical, semantic ou hybrid")
        if mode != "lexical" and vector is None:
            raise ValueError("busca semântica exige embedding da consulta")
        vector_literal = None if vector is None else "[" + ",".join(map(str, vector)) + "]"
        with self._conn.cursor() as cur:
            cur.execute("""
WITH candidate AS (
  SELECT s.id, d.id AS document_id, s.content, s.heading_path, g.search_vector, g.embedding
  FROM gold_enrichments g
  JOIN silver_chunks s ON s.id=g.chunk_id
  JOIN raw_versions v ON v.id=g.version_id AND v.status='published'
  JOIN raw_documents d ON d.id=v.document_id
  WHERE (%(dtype)s IS NULL OR d.document_type=%(dtype)s)
), lexical AS (
  SELECT id, row_number() OVER (ORDER BY ts_rank_cd(search_vector, websearch_to_tsquery(%(lang)s::regconfig, %(query)s)) DESC) AS lexical_rank
  FROM candidate WHERE search_vector @@ websearch_to_tsquery(%(lang)s::regconfig, %(query)s)
  ORDER BY ts_rank_cd(search_vector, websearch_to_tsquery(%(lang)s::regconfig, %(query)s)) DESC LIMIT %(candidate_limit)s
), semantic AS (
  SELECT id, row_number() OVER (ORDER BY embedding <=> %(vector)s::vector) AS semantic_rank
  FROM candidate WHERE %(vector)s IS NOT NULL
  ORDER BY embedding <=> %(vector)s::vector LIMIT %(candidate_limit)s
), merged AS (
  SELECT COALESCE(l.id, s.id) AS id, l.lexical_rank, s.semantic_rank
  FROM lexical l FULL OUTER JOIN semantic s USING (id)
), ranked AS (
  SELECT c.id, c.document_id, c.content, c.heading_path, m.lexical_rank, m.semantic_rank,
    CASE %(mode)s
      WHEN 'lexical' THEN 1.0 / (%(rrf)s + m.lexical_rank)
      WHEN 'semantic' THEN 1.0 / (%(rrf)s + m.semantic_rank)
      ELSE COALESCE(1.0 / (%(rrf)s + m.lexical_rank), 0) + COALESCE(1.0 / (%(rrf)s + m.semantic_rank), 0)
    END AS score
  FROM merged m JOIN candidate c ON c.id=m.id
  WHERE (%(mode)s <> 'lexical' OR m.lexical_rank IS NOT NULL)
    AND (%(mode)s <> 'semantic' OR m.semantic_rank IS NOT NULL)
)
SELECT id, document_id, content, heading_path, lexical_rank, semantic_rank, score
FROM ranked ORDER BY score DESC LIMIT %(limit)s
            """, {"lang": self._fts_language, "query": query, "vector": vector_literal, "dtype": document_type,
                  "mode": mode, "rrf": rrf_k, "limit": limit, "candidate_limit": max(limit * 10, 100)})
            return [SearchHit(chunk_id=str(r[0]), document_id=str(r[1]), content=r[2], heading_path=tuple(r[3]),
                              lexical_rank=r[4], semantic_rank=r[5], score=float(r[6])) for r in cur.fetchall()]

    def expand(self, seed_ids: list[str], *, siblings: int = 1) -> dict[str, dict[str, Any]]:
        """Hidrata o pai e vizinhos estruturais dos seeds, sem ampliar entre documentos."""
        if not seed_ids:
            return {}
        with self._conn.cursor() as cur:
            cur.execute("""
WITH seeds AS (
  SELECT id, parent_chunk_id, ordinal FROM silver_chunks WHERE id = ANY(%s::uuid[])
), expanded AS (
  SELECT seed.id AS seed_id, parent.content AS parent_content, child.id, child.ordinal, child.content
  FROM seeds seed
  JOIN silver_chunks parent ON parent.id=seed.parent_chunk_id
  JOIN silver_chunks child ON child.parent_chunk_id=parent.id
  WHERE abs(child.ordinal-seed.ordinal) <= %s
)
SELECT seed_id, parent_content,
 jsonb_agg(jsonb_build_object('chunk_id',id,'ordinal',ordinal,'content',content) ORDER BY ordinal) AS neighbors
FROM expanded GROUP BY seed_id,parent_content
            """, (seed_ids, siblings))
            return {str(r[0]): {"parent_content": r[1], "neighbors": r[2]} for r in cur.fetchall()}
