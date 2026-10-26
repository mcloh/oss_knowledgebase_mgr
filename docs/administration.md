# Guia do platform-admin

## Acesso

Entre no console com a conta platform-admin criada pelo bootstrap. Essa conta não pertence a um tenant e tem acesso a todos os tenants e KBs.

O token de sessão tem duração de uma hora. A interface é uma conveniência; a autorização é novamente aplicada pela API em cada rota.

## Configurar SMTP

Abra **Configurações → Configurar SMTP** e informe host, porta, usuário, senha e remetente.

- A senha não é devolvida pela API depois de salva.
- Ao editar uma configuração existente, deixe o campo senha vazio para preservá-la.
- A configuração é cifrada no banco de control plane.
- Antes de criar tenants, valide conectividade SMTP no ambiente de operação.

## Criar tenant

Em **Tenants → Criar tenant**, informe:

| Campo | Regra |
|---|---|
| Nome | Nome de exibição do cliente |
| Slug | 2 a 50 caracteres: minúsculas, números e hífen |
| E-mail do tenant-admin | Destino do link de ativação |

Ao confirmar, a plataforma cria o tenant, registra seu usuário com papel tenant e envia um link de validade de 24 horas. Use **Reenviar ativação** caso o link expire; o link anterior é invalidado.

## Criar uma KB

Em **Nova base**, selecione o tenant e informe:

1. Nome e slug da KB.
2. URL, usuário e senha do PostgreSQL do data plane. Uma URL já autenticada também é aceita; credenciais separadas complementam uma URL sem usuário.
3. Endpoint/bucket S3, access key e secret.
4. Endpoint e modelo de embedding.
5. Endpoint e modelo de LLM de enrichment.
6. Webhook de rejeição, quando aplicável.

O servidor deriva o schema no formato kb_<tenant>_<slug>. O campo de schema não é aceito do cliente. Assim, várias KBs podem compartilhar a mesma instância PostgreSQL sem colidir em tabelas.

Depois do cadastro, chame o endpoint de provisionamento da KB. Ele instala pgvector (no database), cria o schema e aplica o modelo medallion. Em seguida, agende uma ingestão com URI s3://.

## Chaves de API

Crie uma chave por consumidor RAG, em vez de compartilhar uma única chave. A chave completa aparece somente na resposta da criação; guarde-a no secret manager do consumidor.

As métricas de serving ficam associadas à API key, KB e tenant. Revogação individual de chave é suportada no modelo de dados; a interface de revogação é um incremento futuro.

## Operação segura

- Use contas PostgreSQL com menor privilégio possível.
- Mantenha a CONTROL_PLANE_FERNET_KEY estável; perdê-la torna configurações antigas indecifráveis.
- Faça backup do control plane e de cada data plane.
- Não use o tenant de um cliente para guardar dados de outro, mesmo que o schema seja separado.
- Troca de modelo/dimensão de embedding requer reprocessamento planejado.
