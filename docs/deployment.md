# Operação e deploy

## Componentes Docker

| Serviço | Papel |
|---|---|
| control-db | PostgreSQL do control plane |
| api | FastAPI administrativa e serving |
| worker | Consome jobs de ingestão por polling |
| admin-ui | Nginx com console estático |

O compose do control plane pressupõe uma rede Docker externa chamada traefik-net para exposição HTTPS por Traefik. Adapte labels e ADMIN_ORIGIN ao seu domínio.

## Variáveis obrigatórias

| Variável | Uso |
|---|---|
| CONTROL_DB_NAME, CONTROL_DB_USER, CONTROL_DB_PASSWORD | Banco do control plane |
| CONTROL_PLANE_JWT_SECRET | Assinatura de sessão |
| CONTROL_PLANE_FERNET_KEY | Cifra de configurações armazenadas |
| SMTP_HOST, SMTP_PORT, SMTP_USER, SMTP_PASSWORD, SMTP_FROM | Bootstrap de SMTP |

Gere a chave Fernet uma única vez e armazene-a em secret manager:

~~~bash
python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
~~~

## Migrações

Para uma instalação nova, o container inicializa 002_admin_multitenant.sql. Para instalações existentes, aplique 003_control_plane_evolution.sql uma vez:

~~~bash
docker compose --env-file .env.control -f docker-compose.control-plane.yml +  exec -T control-db psql -U "$CONTROL_DB_USER" -d "$CONTROL_DB_NAME" +  -f /caminho/para/003_control_plane_evolution.sql
~~~

## Backup e recuperação

- Faça dump diário do control plane e de cada database de data plane.
- Faça backup do object storage; o RAW replica bytes necessários à reprodutibilidade, mas a origem S3 deve continuar sendo a custódia.
- Guarde a chave Fernet junto do procedimento de recuperação, em canal protegido.
- Teste restore em ambiente isolado antes de depender de backups.

## Checklist pré-produção

- [ ] DNS, TLS e ADMIN_ORIGIN corretos.
- [ ] Segredos fora do repositório e acesso mínimo por serviço.
- [ ] Usuário PostgreSQL da KB limitado ao schema derivado.
- [ ] pgvector disponível e dimensão do modelo confirmada.
- [ ] SMTP autenticado e ativação testada.
- [ ] Observabilidade de contêineres, banco e worker configurada.
- [ ] Backup/restauração testados.
- [ ] Avaliação de recuperação com documentos e consultas representativas.
