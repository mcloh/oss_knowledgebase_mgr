from __future__ import annotations

import argparse
import json

from oss_kbdb.adapters.embeddings import LocalEmbedder, OpenAICompatibleEmbedder
from oss_kbdb.adapters.postgres import PostgresRepository
from oss_kbdb.adapters.s3 import S3ObjectStore
from oss_kbdb.config import Settings
from oss_kbdb.services.enrichment import DeterministicEnricher, OpenAICompatibleEnricher
from oss_kbdb.services.ingestion import IngestionService


def _embedder(settings: Settings):
    if settings.embedding_provider == "local":
        obj = LocalEmbedder(settings.embedding_model, settings.embedding_dimensions)
    else:
        if not settings.embedding_base_url:
            raise ValueError("EMBEDDING_BASE_URL é obrigatório para openai_compatible")
        obj = OpenAICompatibleEmbedder(settings.embedding_base_url, settings.embedding_api_key,
                                      settings.embedding_model, settings.embedding_dimensions)
    obj.model = settings.embedding_model
    return obj


def _enricher(settings: Settings):
    if settings.enrichment_provider == "deterministic":
        return DeterministicEnricher(settings.enrichment_model)
    if settings.enrichment_provider == "openai_compatible" and settings.enrichment_base_url:
        return OpenAICompatibleEnricher(settings.enrichment_base_url, settings.enrichment_api_key, settings.enrichment_model)
    raise ValueError("ENRICHMENT_PROVIDER deve ser deterministic ou openai_compatible com ENRICHMENT_BASE_URL")


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="OSS-KBDB")
    sub = parser.add_subparsers(dest="command", required=True)
    ingest = sub.add_parser("ingest")
    ingest.add_argument("--uri", required=True, help="s3://bucket/object-key")
    ingest.add_argument("--document-type", required=True)
    search = sub.add_parser("search")
    search.add_argument("query")
    search.add_argument("--mode", choices=("lexical", "semantic", "hybrid"), default="hybrid")
    search.add_argument("--document-type")
    search.add_argument("--limit", type=int, default=10)
    return parser


def main(argv=None) -> int:
    args = _parser().parse_args(argv)
    settings = Settings.from_env()
    repo = PostgresRepository(settings.database_url, fts_language=settings.fts_language)
    try:
        if args.command == "ingest":
            store = S3ObjectStore(endpoint_url=settings.s3_endpoint_url, region=settings.s3_region,
                                  access_key_id=settings.s3_access_key_id, secret_access_key=settings.s3_secret_access_key,
                                  addressing_style=settings.s3_addressing_style)
            bucket, key = store.parse_uri(args.uri)
            service = IngestionService(repo, _embedder(settings), _enricher(settings), max_tokens=settings.chunk_max_tokens,
                                       overlap_tokens=settings.chunk_overlap_tokens, min_tokens=settings.chunk_min_tokens)
            print(json.dumps(service.ingest(store.get(bucket, key), document_type=args.document_type), ensure_ascii=False))
        else:
            embedder = _embedder(settings) if args.mode != "lexical" else None
            vector = embedder.embed([args.query])[0] if embedder else None
            hits = repo.search(args.query, mode=args.mode, document_type=args.document_type, vector=vector, limit=args.limit)
            context = repo.expand([hit.chunk_id for hit in hits], siblings=settings.expansion_siblings)
            print(json.dumps([hit.__dict__ | {"heading_path": list(hit.heading_path), "expansion": context.get(hit.chunk_id)}
                              for hit in hits], ensure_ascii=False))
    finally:
        repo.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
