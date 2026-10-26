from __future__ import annotations

from oss_kbdb.adapters.extractors import extract
from oss_kbdb.domain.models import SourceObject
from oss_kbdb.services.chunker import hierarchical_chunks


class IngestionService:
    def __init__(self, repository, embedder, enricher, *, max_tokens: int, overlap_tokens: int, min_tokens: int) -> None:
        self._repo, self._embedder, self._enricher = repository, embedder, enricher
        self._max_tokens, self._overlap_tokens, self._min_tokens = max_tokens, overlap_tokens, min_tokens

    def ingest(self, source: SourceObject, *, document_type: str) -> dict:
        document_id, version_id, is_new = self._repo.ingest_raw(
            bucket=source.bucket, key=source.key, content=source.content, etag=source.etag,
            content_type=source.content_type, document_type=document_type)
        if not is_new:
            return {"document_id": document_id, "version_id": version_id, "status": "unchanged"}
        extracted = extract(source.content, source.key, source.content_type)
        chunks = hierarchical_chunks(extracted.text, max_tokens=self._max_tokens,
                                     overlap_tokens=self._overlap_tokens, min_tokens=self._min_tokens)
        child_chunks = [c for c in chunks if c.kind == "chunk"]
        if not child_chunks:
            raise ValueError("documento não gerou chunks indexáveis")
        child_ids = self._repo.replace_silver(version_id, chunks, {"pages": len(extracted.pages)})
        enrichments = [self._enricher.enrich(chunk) for chunk in child_chunks]
        vectors = self._embedder.embed([item.search_text for item in enrichments])
        self._repo.publish_gold(version_id=version_id, enrichments=enrichments, child_ids=child_ids, vectors=vectors)
        return {"document_id": document_id, "version_id": version_id, "status": "published",
                "sections": len(chunks) - len(child_chunks), "chunks": len(child_chunks)}
