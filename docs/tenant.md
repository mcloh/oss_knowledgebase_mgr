# Guia do tenant-admin

## Ativação

Você receberá um e-mail com um link de ativação. Abra-o no navegador e defina uma senha com no mínimo 16 caracteres. O link vale por 24 horas e só pode ser usado uma vez.

Se o link expirar ou não chegar, solicite ao platform-admin o reenvio de ativação.

## Seu escopo

O tenant-admin enxerga somente o próprio tenant. Ao criar uma KB, o tenant é exibido no formulário, mas é fixado pela identidade do token; alterar o HTML ou enviar outro ID não concede acesso a outro tenant.

## Criar uma base

Informe os dados operacionais da base:

- PostgreSQL/pgvector do data plane;
- origem S3 e credenciais com acesso somente-leitura ao bucket/prefixo necessário;
- endpoint e modelo de embedding;
- endpoint e modelo de enrichment;
- política de chunk (quando exposta pela integração de cadastro);
- URL de webhook de rejeição.

Após provisionar, solicite a ingestão de um objeto ou prefixo usando URI s3://. O estado do job deve ser acompanhado até a publicação.

## Consumidores RAG

Crie uma API key para cada aplicação consumidora. Registre qual aplicação recebeu qual chave. A chave é exibida apenas uma vez; se for perdida, crie outra e revogue a anterior quando a tela de revogação estiver disponível.

## Responsabilidades

Você é responsável por:

- autorizar o acesso da plataforma ao bucket;
- confirmar que os documentos podem ser enviados ao endpoint de embedding/enrichment escolhido;
- respeitar licenças, confidencialidade e retenção dos documentos;
- validar qualidade da recuperação antes de conectar uma KB a uma experiência para usuários finais.
