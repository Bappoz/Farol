# Política de segurança

## Modelo de ameaça

O Farol é um aplicativo local. O servidor escuta em `127.0.0.1` e não possui
autenticação, sessão ou controle de acesso, porque parte do princípio de que o
único cliente é a pessoa sentada na máquina.

Isso tem uma consequência prática: **expor a porta do Farol na rede entrega a
base inteira a quem alcançar o endereço.** A base contém dados pessoais — nome,
e-mail, telefone, histórico de candidaturas e currículos. Quem quiser acessar o
aplicativo de outra máquina deve colocar na frente um proxy reverso com
autenticação, e nunca publicar a porta diretamente.

Dados em repouso não são cifrados. Quem tem acesso ao sistema de arquivos do
usuário tem acesso ao banco; use cifragem de disco se isso importa no seu caso.

## Superfícies consideradas no projeto

| Superfície | Tratamento |
|---|---|
| Descrição de vaga vinda de portal de terceiro | Escapada antes de qualquer marcação (`farol.markup`); nunca é inserida como HTML. |
| Consultas ao banco | Sempre parametrizadas. Nenhum valor de usuário é concatenado em SQL. |
| PDF enviado pelo usuário | Validado pelo cabeçalho do arquivo, limitado a 15 MB, gravado com nome derivado e servido apenas de dentro do diretório de dados (`pdfs.path_for` recusa caminho que escape dele). |
| Chave da API Anthropic | Guardada no banco local e enviada somente para `api.anthropic.com`, quando o usuário aciona um dos botões de revisão. |
| Requisições aos portais | Somente leitura, sem credencial, com `User-Agent` identificando o aplicativo. |

O assistente por inteligência artificial é opcional e desligado por padrão. Sem
chave configurada, o aplicativo não faz nenhuma requisição além da coleta de
vagas: pontuação, currículo e roadmap são calculados localmente.

## Versões com suporte

| Versão | Suporte |
|---|---|
| 1.x | sim |
| < 1.0 | não |

## Como relatar uma vulnerabilidade

Use o canal privado do GitHub:
**Security → Report a vulnerability**, em https://github.com/Bappoz/Tunel/security.

Não abra issue pública para falha de segurança.

Inclua a versão afetada, o sistema operacional, os passos para reproduzir e o
impacto que você identificou. A confirmação de recebimento sai em até sete dias.
Este é um projeto pessoal mantido em tempo livre: não há acordo de nível de
serviço para correção, mas todo relato é lido e respondido.
