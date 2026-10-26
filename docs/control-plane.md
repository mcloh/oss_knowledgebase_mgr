# Control plane e bancos por KB

O OSS-KBDB opera em dois planos separados:

| Plano | Banco | Conteúdo |
|---|---|---|
| Control plane | PostgreSQL central | tenants, RBAC, configurações cifradas, jobs, API keys, auditoria e uso |
| Data plane de cada KB | PostgreSQL + pgvector próprio | RAW, SILVER, GOLD, vetores, índices, chunks e documentos daquele KB |

Ao criar uma KB, o administrador informa URL do PostgreSQL/pgvector, credencial, dimensão vetorial e política TLS. O control plane **deriva** o schema (`kb_<tenant>_<kb>`); o chamador não escolhe `public` nem um schema de outra KB. Essa configuração é cifrada no control plane. O worker a usa somente durante a execução e não a envia ao cliente RAG.

`provision_kb_database()` valida o formato, cria `pgvector` uma vez no database, cria o schema exclusivo e aplica `001_schema.sql` com `search_path` transacional. O usuário do worker deve receber privilégios somente no schema da KB; não use superusuário compartilhado entre tenants.
