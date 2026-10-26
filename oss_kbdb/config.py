from __future__ import annotations

import os
from dataclasses import dataclass


def _env(key: str, default: str = "") -> str:
    return os.getenv(key, default).strip()


@dataclass(frozen=True)
class Settings:
    database_url: str
    s3_endpoint_url: str | None
    s3_region: str
    s3_access_key_id: str | None
    s3_secret_access_key: str | None
    s3_addressing_style: str
    embedding_provider: str
    embedding_model: str
    embedding_dimensions: int
    embedding_base_url: str | None
    embedding_api_key: str | None
    chunk_max_tokens: int
    chunk_overlap_tokens: int
    chunk_min_tokens: int
    fts_language: str
    enrichment_provider: str
    enrichment_model: str
    enrichment_base_url: str | None
    enrichment_api_key: str | None
    expansion_siblings: int

    @classmethod
    def from_env(cls) -> "Settings":
        try:
            from dotenv import load_dotenv
            load_dotenv()
        except ImportError:
            pass
        provider = _env("EMBEDDING_PROVIDER", "local")
        if provider not in {"local", "openai_compatible"}:
            raise ValueError("EMBEDDING_PROVIDER deve ser local ou openai_compatible")
        max_tokens, overlap, minimum = (int(_env(k, d)) for k, d in (
            ("CHUNK_MAX_TOKENS", "450"), ("CHUNK_OVERLAP_TOKENS", "60"), ("CHUNK_MIN_TOKENS", "30")))
        if minimum < 1 or overlap < 0 or max_tokens <= overlap:
            raise ValueError("configuração de chunk inválida")
        return cls(
            database_url=_env("DATABASE_URL"), s3_endpoint_url=_env("S3_ENDPOINT_URL") or None,
            s3_region=_env("S3_REGION", "us-east-1"), s3_access_key_id=_env("S3_ACCESS_KEY_ID") or None,
            s3_secret_access_key=_env("S3_SECRET_ACCESS_KEY") or None,
            s3_addressing_style=_env("S3_ADDRESSING_STYLE", "auto"), embedding_provider=provider,
            embedding_model=_env("EMBEDDING_MODEL"), embedding_dimensions=int(_env("EMBEDDING_DIMENSIONS", "384")),
            embedding_base_url=_env("EMBEDDING_BASE_URL") or None, embedding_api_key=_env("EMBEDDING_API_KEY") or None,
            chunk_max_tokens=max_tokens, chunk_overlap_tokens=overlap, chunk_min_tokens=minimum,
            fts_language=_env("FTS_LANGUAGE", "portuguese"),
            enrichment_provider=_env("ENRICHMENT_PROVIDER", "deterministic"),
            enrichment_model=_env("ENRICHMENT_MODEL", "deterministic-v1"),
            enrichment_base_url=_env("ENRICHMENT_BASE_URL") or None,
            enrichment_api_key=_env("ENRICHMENT_API_KEY") or None,
            expansion_siblings=int(_env("SEARCH_EXPANSION_SIBLINGS", "1")),
        )
