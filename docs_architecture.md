# Decisões de arquitetura

## 1. Medallion no PostgreSQL

O S3 é sistema de origem e custódia; não é banco de estado do pipeline. `raw_documents` identifica o objeto lógico e `raw_versions` preserva versões imutáveis por SHA-256. As tabelas SILVER e GOLD referenciam uma versão RAW, o que permite reprocessar sem perder rastreabilidade.

## 2. Hierarquia de chunks

Cada seção é um chunk pai, sem embedding. Seus filhos são janelas token-aware com sobreposição e são as únicas unidades indexadas. O resultado da busca contém o filho preciso e seu `parent_chunk_id` permite hidratar a seção inteira para geração de resposta.

## 3. Enriquecimento e busca

O embedding não é gerado somente sobre o fragmento literal. Cada chunk filho recebe um enriquecimento
versionado: título, resumo, palavras-chave, perguntas que ele responde e resposta hipotética. O
`search_text` é a composição desses campos e é a entrada comum do índice vetorial e do FTS. A SILVER
continua sendo a citação/grounding; o enriquecimento nunca é apresentado como fonte factual.

- `lexical`: `tsvector` + `websearch_to_tsquery` do PostgreSQL.
- `semantic`: distância de cosseno `pgvector`.
- `hybrid`: RRF sobre posições de cada pista, não sobre os scores brutos.

O fluxo é `retrieve seeds → expand`. Seeds são os melhores filhos por recuperação; a expansão devolve
o pai e vizinhos com o mesmo pai. `gold_edges` materializa relações `parent` agora e reserva
`next`/`reference` para extensões. Cross-document não é habilitado por inferência: requer contrato de
referência, resolução de identidade e métricas próprias, tal como uma feature separada.

O banco aceita vetor de qualquer dimensão para manter o modelo configurável. Para índice HNSW/IVFFlat, PostgreSQL exige dimensão fixa; a operação deve fixar `EMBEDDING_DIMENSIONS` por ambiente/coleção e criar o índice correspondente. Trocar a dimensão é migração com re-embedding, não troca transparente de `.env`.

## 4. Próximos incrementos naturais

1. fila (Celery/Arq/Temporal) para ingestão em lote e retentativas;
2. extrator Docling/Unstructured e OCR como adapters adicionais;
3. filtros por metadados, ACL por documento e tombstone/despublicação;
4. avaliação com golden probes, reranking e observabilidade de recall/latência;
5. OAuth/SSO, rate limiting distribuído e trilha de auditoria imutável.
