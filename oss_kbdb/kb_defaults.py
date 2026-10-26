"""Perfis default internos para reduzir a superfície do cadastro de uma KB."""
from __future__ import annotations

import os
from typing import Any
from urllib.parse import quote, urlsplit, urlunsplit

from oss_kbdb.config import Settings

_LOCAL_MODEL = "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"


def _value(name: str, fallback: str = "") -> str:
    return os.getenv(name, fallback).strip()


def database_url(config: dict[str, Any]) -> str:
    """Completa URL sem credencial sem persistir a URL completa no payload recebido."""
    url = config["url"]
    credentials = config.get("credentials", {})
    if not credentials.get("username") or not credentials.get("password"):
        return url
    parsed = urlsplit(url)
    if parsed.username is not None:
        return url
    if not parsed.hostname:
        raise ValueError("URL PostgreSQL inválida")
    netloc = f"{quote(credentials['username'], safe='')}:{quote(credentials['password'], safe='')}@{parsed.hostname}"
    if parsed.port:
        netloc += f":{parsed.port}"
    return urlunsplit((parsed.scheme, netloc, parsed.path, parsed.query, parsed.fragment))


def default_database() -> dict[str, Any]:
    settings = Settings.from_env()
    url = _value("DEFAULT_KB_DATABASE_URL", settings.database_url)
    if not url:
        raise ValueError("DEFAULT_KB_DATABASE_URL ou DATABASE_URL deve ser configurada")
    return {
        "url": url,
        "credentials": {},
        "vector_dimensions": int(_value("DEFAULT_EMBEDDING_DIMENSIONS", str(settings.embedding_dimensions))),
        "sslmode": _value("DEFAULT_KB_DATABASE_SSLMODE", "require"),
    }


def default_embedding() -> dict[str, Any]:
    settings = Settings.from_env()
    provider = _value("DEFAULT_EMBEDDING_PROVIDER", settings.embedding_provider or "local")
    model = _value("DEFAULT_EMBEDDING_MODEL", settings.embedding_model or _LOCAL_MODEL)
    dimensions = int(_value("DEFAULT_EMBEDDING_DIMENSIONS", str(settings.embedding_dimensions)))
    config = {
        "provider": provider,
        "model": model,
        "dimensions": dimensions,
        "credentials": {},
    }
    if provider == "openai_compatible":
        url = _value("DEFAULT_EMBEDDING_BASE_URL", settings.embedding_base_url or "")
        if not url:
            raise ValueError("DEFAULT_EMBEDDING_BASE_URL é obrigatória para embedding OpenAI-compatible")
        config["url"] = url
        api_key = _value("DEFAULT_EMBEDDING_API_KEY", settings.embedding_api_key or "")
        if api_key:
            config["credentials"] = {"api_key": api_key}
    else:
        config["url"] = "local://sentence-transformers"
    return config


def default_enrichment() -> dict[str, Any]:
    settings = Settings.from_env()
    provider = _value("DEFAULT_ENRICHMENT_PROVIDER", settings.enrichment_provider or "deterministic")
    model = _value("DEFAULT_ENRICHMENT_MODEL", settings.enrichment_model or "deterministic-v1")
    config = {"provider": provider, "model": model, "credentials": {}, "dimensions": 0}
    if provider == "openai_compatible":
        url = _value("DEFAULT_ENRICHMENT_BASE_URL", settings.enrichment_base_url or "")
        if not url:
            raise ValueError("DEFAULT_ENRICHMENT_BASE_URL é obrigatória para enrichment OpenAI-compatible")
        config["url"] = url
        api_key = _value("DEFAULT_ENRICHMENT_API_KEY", settings.enrichment_api_key or "")
        if api_key:
            config["credentials"] = {"api_key": api_key}
    else:
        config["url"] = "local://deterministic"
    return config


def default_chunk_config() -> dict[str, int]:
    settings = Settings.from_env()
    return {
        "max_tokens": int(_value("DEFAULT_CHUNK_MAX_TOKENS", str(settings.chunk_max_tokens))),
        "overlap_tokens": int(_value("DEFAULT_CHUNK_OVERLAP_TOKENS", str(settings.chunk_overlap_tokens))),
        "min_tokens": int(_value("DEFAULT_CHUNK_MIN_TOKENS", str(settings.chunk_min_tokens))),
    }
