# Referência da API

Base pública: https://api.osskbdb.xptoai.com.br/v1

Todos os endpoints administrativos usam Authorization: Bearer <JWT>. O endpoint de serving usa X-API-Key.

## Autenticação administrativa

### POST /auth/login

~~~json
{"email":"admin@example.com","password":"senha"}
~~~

Resposta: access_token JWT com papel admin ou tenant.

### POST /auth/activate

~~~json
{"token":"token-do-link","password":"senha-com-16-ou-mais-caracteres"}
~~~

## Administração de tenants

### POST /tenants

Exclusivo de platform-admin.

~~~json
{"slug":"cliente-a","name":"Cliente A","admin_email":"admin@cliente-a.example"}
~~~

### POST /tenants/{tenant_id}/activation/resend

Exclusivo de platform-admin. Invalida o token anterior e envia uma nova ativação.

### GET /tenants

Platform-admin recebe todos; tenant-admin recebe somente o próprio.

## SMTP

### GET /admin/smtp

Exclusivo de platform-admin. Retorna estado, host, porta, usuário e remetente; nunca retorna senha.

### POST /admin/smtp

~~~json
{"host":"mail.example","port":465,"username":"mailer","password":"segredo","sender":"mailer@example.com"}
~~~

Para manter a senha previamente configurada, omita password ou envie string vazia.

## KBs

### POST /knowledge-bases

O tenant_id é aceito para platform-admin. Para tenant-admin ele é ignorado e inferido do token.

~~~json
{
  "tenant_id":"uuid-opcional",
  "slug":"manuais",
  "name":"Manuais",
  "database":{"url":"postgresql://db.example:5432/rag","credentials":{"username":"kb_user","password":"..."},"vector_dimensions":384},
  "s3":{"url":"https://s3.example","credentials":{"access_key_id":"...","secret_access_key":"..."}},
  "embedding":{"url":"https://models.example/v1","model":"bge-m3","provider":"openai_compatible","dimensions":1024,"credentials":{"api_key":"..."}},
  "enrichment":{"url":"https://models.example/v1","model":"llm","provider":"openai_compatible","credentials":{"api_key":"..."}},
  "chunk_config":{"max_tokens":450,"overlap_tokens":60,"min_tokens":30},
  "webhook_url":"https://consumer.example/rejections"
}
~~~

### POST /knowledge-bases/{kb_id}/provision

Cria o schema exclusivo e instala o modelo medallion.

### POST /knowledge-bases/{kb_id}/ingestion-jobs

~~~json
{"source_uri":"s3://bucket/prefixo/documento.pdf","document_type":"manual"}
~~~

### POST /knowledge-bases/{kb_id}/api-keys

~~~json
{"client_name":"portal-rag","scopes":["serve"]}
~~~

Guarde api_key da resposta imediatamente.

### GET /knowledge-bases e GET /metrics/usage

Aplicam o mesmo isolamento do tenant.

## Serving

### POST /serve/search

Header: X-API-Key: kb_...

~~~json
{"query":"como redefinir senha","mode":"hybrid","document_type":"manual","limit":10}
~~~

Modos válidos: lexical, semantic e hybrid. A resposta devolve chunks seed e expansion, incluindo pai e vizinhos estruturais quando existem.

## Erros

| Status | Significado |
|---|---|
| 401 | Token ou API key ausente/inválida |
| 403 | Papel ou scope insuficiente |
| 404 | Recurso fora do escopo do tenant ou inexistente |
| 422 | Configuração/entrada inválida ou provisionamento falhou |
| 502 | Tenant criado, mas a entrega do e-mail de ativação falhou; use reenvio |
| 503 | SMTP ainda não foi configurado |
