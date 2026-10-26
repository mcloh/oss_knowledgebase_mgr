from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal


@dataclass(frozen=True)
class SourceObject:
    bucket: str
    key: str
    content: bytes
    etag: str | None = None
    content_type: str | None = None


@dataclass(frozen=True)
class ExtractedDocument:
    text: str
    pages: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class Chunk:
    ordinal: int
    content: str
    heading_path: tuple[str, ...]
    kind: Literal["section", "chunk"]
    parent_ordinal: int | None = None
    page_start: int | None = None
    page_end: int | None = None


@dataclass(frozen=True)
class SearchHit:
    chunk_id: str
    document_id: str
    content: str
    heading_path: tuple[str, ...]
    lexical_rank: int | None = None
    semantic_rank: int | None = None
    score: float | None = None


@dataclass(frozen=True)
class Enrichment:
    """Texto derivado para recuperação; nunca substitui ``Chunk.content`` como fonte."""
    title: str
    summary: str
    keywords: tuple[str, ...]
    questions: tuple[str, ...]
    hypothetical_answer: str
    search_text: str
    model: str
    prompt_version: str
