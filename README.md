# OSS-KBDB

OSS-KBDB é uma plataforma open-source para construir e servir bases de conhecimento RAG multi-tenant. Ela recebe documentos de object storage compatível com S3, preserva o histórico em um pipeline medallion e oferece recuperação lexical, semântica ou híbrida com contexto hierárquico.

> Estado da versão: **0.1.0**. O projeto entrega pipeline, control plane, interface administrativa, autenticação por tenant, API de serving e implantação Docker. Consulte as limitações antes de operar em produção crítica.

## Capacidades

- Ingestão de URIs s3://bucket/chave usando API S3 padrão: AWS S3, MinIO, Ceph RGW e OCI Object Storage S3-compatible.
- Camadas RAW, SILVER e GOLD, com hash SHA-256 e versões imutáveis do objeto.
- Segmentação configurável, preservando árvore de seções e relação pai/filhos.
- Enriquecimento de busca: título, resumo, termos, perguntas e resposta hipotética compõem o search_text.
- Embeddings locais via sentence-transformers ou endpoint OpenAI-compatible configurável.
- Busca lexical (PostgreSQL FTS), semântica (pgvector) e híbrida (RRF).
- Recuperação seed → expansion: cada seed retorna seção-pai e vizinhos estruturais do mesmo documento.
- Control plane com platform-admin, tenant-admin, API keys por KB, métricas de uso, jobs e credenciais cifradas.
- Cada KB ocupa schema próprio (kb_tenant_kb) mesmo quando compartilha uma instância PostgreSQL.
- Onboarding de tenant por e-mail: criação, ativação e definição de senha.

## Arquitetura

~~~text
Object storage S3
       │
       ▼
RAW: objeto, ETag, hash e versão
       │
       ▼
SILVER: extração, seções, chunks pai/filho
       │
       ▼
GOLD: enrichment, FTS, embeddings, edges
       │
       ▼
PostgreSQL FTS + pgvector ──► lexical / semantic / hybrid
                                      │
                                      ▼
                                seeds + expansion

Control plane (PostgreSQL central)
  tenants · usuários · credenciais cifradas · jobs · API keys · uso
~~~

Há dois planos de dados. O **control plane** guarda configuração e governança; o **data plane** de cada KB guarda conteúdo, chunks e vetores. Consulte [docs/control-plane.md](docs/control-plane.md).

## Início rápido local

Pré-requisitos: Python 3.11+, Docker e Docker Compose.

~~~bash
cp .env.example .env
docker compose up -d db minio
python -m pip install -e '.[dev,local]'
psql "$DATABASE_URL" -f sql/001_schema.sql

oss-kbdb ingest --uri s3://knowledge/manual.pdf --document-type manuals
oss-kbdb search "como ativar roaming" --mode hybrid --document-type manuals
~~~

O compose local disponibiliza somente PostgreSQL/pgvector e MinIO para desenvolvimento. O control plane completo utiliza docker-compose.control-plane.yml.

## Implantação do control plane

1. Crie um PostgreSQL com pgcrypto para o control plane e uma instância PostgreSQL 16+ com pgvector para cada data plane. As duas funções podem compartilhar a mesma instância física, mas não o schema.
2. Crie um arquivo .env.control fora do Git com:

~~~dotenv
CONTROL_DB_NAME=osskbdb_control
CONTROL_DB_USER=...
CONTROL_DB_PASSWORD=...
CONTROL_PLANE_JWT_SECRET=<segredo-aleatório-longo>
CONTROL_PLANE_FERNET_KEY=<chave-gerada-por-Fernet>
SMTP_HOST=...
SMTP_PORT=465
SMTP_USER=...
SMTP_PASSWORD=...
SMTP_FROM=...
~~~

3. Suba os serviços:

~~~bash
docker compose --env-file .env.control -f docker-compose.control-plane.yml up -d --build
~~~

4. Crie o primeiro platform-admin no contêiner da API:

~~~bash
docker compose --env-file .env.control -f docker-compose.control-plane.yml exec api oss-kbdb-bootstrap-admin
~~~

5. Publique admin-ui atrás de HTTPS e configure ADMIN_ORIGIN na API para a origem exata da interface.

As migrações 002_admin_multitenant.sql e 003_control_plane_evolution.sql são necessárias para bancos de control plane existentes. A segunda é idempotente.

## Perfis e fluxo operacional

| Perfil | Permissões |
|---|---|
| Platform-admin | Configura SMTP, cria tenants, escolhe tenant ao criar KB, cria API keys e administra todas as KBs |
| Tenant-admin | Vê apenas seu tenant e suas KBs; o tenant é determinado pelo token e não pode ser alterado no cadastro |
| Cliente RAG | Usa API key da KB exclusivamente no endpoint de serving |

Fluxo recomendado:

1. Platform-admin configura SMTP.
2. Cria tenant e e-mail do tenant-admin.
3. Tenant-admin abre o link recebido e registra senha.
4. Um administrador cria a KB, informando S3, PostgreSQL, embedding, enriquecimento e política de chunk.
5. Provisiona o schema da KB e agenda a ingestão.
6. Cria uma ou mais API keys, uma por consumidor RAG.

Guias detalhados: [administração](docs/administration.md), [tenant-admin](docs/tenant.md), [API](docs/api.md) e [operação/deploy](docs/deployment.md).

## Busca e enrichment

O chunk-filho é a unidade indexada. O chunk-pai representa a seção. O enrichment é derivado, versionado e usado para recuperação; a SILVER continua sendo a fonte de citação/grounding.

| Modo | Implementação |
|---|---|
| lexical | tsvector + websearch_to_tsquery |
| semantic | distância de cosseno no pgvector |
| hybrid | Reciprocal Rank Fusion (RRF), sem somar scores de escalas diferentes |

A troca de dimensão de embedding requer re-embedding e recriação do índice. Não altere a dimensão de uma KB publicada como se fosse uma configuração inócua.

## Segurança

- Nunca versione .env, .env.control, credenciais de bucket, conexão de banco ou chaves de API.
- As configurações sensíveis de KB e SMTP são cifradas no control plane com Fernet.
- API keys são apresentadas uma única vez; apenas seu hash é persistido.
- Use TLS no PostgreSQL e no endpoint de modelos em produção.
- Restrinja o usuário de data plane ao schema da KB; não use public nem superusuário compartilhado entre tenants.

## Limitações da v0.1.0

- Extratores implementados: PDF textual, Markdown, HTML e texto. OCR e tabelas estruturadas ainda não fazem parte do pipeline.
- O worker usa polling do banco; não há broker/fila distribuída nem dashboard de retentativas nesta versão.
- Webhook de rejeição é configurável e armazenado, mas entrega assíncrona com retentativas auditáveis é um incremento posterior.
- Não há OAuth/SSO, MFA, ACL por documento, rate limit distribuído ou auditoria imutável.
- Métricas atuais cobrem eventos de serving; custos de provedores e métricas de qualidade exigem instrumentação adicional.

## Desenvolvimento e testes

~~~bash
python -m pip install -e '.[dev,local]'
python -m pytest -q
python -m compileall -q oss_kbdb
node --check admin-ui/dist/app.js
~~~

## Licença

Defina a licença antes de distribuir ou aceitar contribuições externas.
