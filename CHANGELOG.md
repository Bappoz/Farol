# Changelog

Formato baseado em [Keep a Changelog](https://keepachangelog.com/pt-BR/1.1.0/).
Versionamento conforme [SemVer](https://semver.org/lang/pt-BR/).

## [1.1.0] — 2026-09-24

### Adicionado

- **Assistente de IA por modelo local** (issue #15): em Ajustes dá para escolher
  entre nenhum assistente (o padrão), a API da Anthropic e um servidor que você
  mesmo subiu — Ollama, LM Studio, `llama-server` ou Jan, pela API compatível com
  a da OpenAI. O endereço só é aceito se resolver inteiramente para loopback ou
  rede privada, e a checagem roda **antes de cada requisição**, não só ao salvar:
  o que sai daqui é o currículo inteiro. O app não instala, não baixa e não sobe
  modelo nenhum; ele mede a RAM e a VRAM da máquina, marca no catálogo o que cabe
  e pergunta ao servidor quais modelos já estão instalados. Quando a memória não
  pode ser medida, nada é marcado como "cabe" — recomendar no escuro termina em
  swap. Decisão registrada em `docs/decisoes/0003-ia-local.md`.
- **Gerar currículo dirigido à vaga em um clique**, na tela da vaga: monta a
  partir do perfil e, com assistente configurado, passa resumo, marcadores e
  carta pelo modelo. O rascunho de base continua vindo do `resume.build`, então
  falha do modelo devolve um currículo completo, nunca uma página em branco — e
  uma etapa que falha não leva as outras junto. A instrução que proíbe inventar
  experiência é a mesma nos dois provedores.
- **Alertas de vaga nova** (issue #12): uma busca guardada — termos, nível,
  região, modelo de trabalho e fit mínimo — que passa a avisar quando a coleta
  traz vaga compatível. O casamento roda no fim da rodada, sobre o que a coleta
  já trouxe: nenhum alerta gera requisição própria, e a janela de descanso
  continua sendo o único regulador de tráfego. Cada vaga casa com cada alerta uma
  única vez (a chave de `alert_hits` é a deduplicação); alerta recém-criado entra
  com o acervo marcado como lido, para não abrir com trinta avisos de semanas
  atrás. Opt-out em dois níveis: pausar para de casar, e desmarcar o aviso mantém
  o resumo na tela e cala só o desktop.
- **Leituras** (issue #9): agregador de artigos técnicos por RSS/Atom, etiquetado
  com a mesma taxonomia de competências do fit score — o Roadmap diz o que
  estudar, esta tela ajuda a achar por onde começar. É um **índice**, não uma
  cópia: título, link, data e o resumo curto que o próprio feed publica, com o
  link levando ao site de quem escreveu. Os dez feeds embutidos nascem desligados
  e a busca só roda a pedido, então quem nunca abrir a tela não gera uma
  requisição sequer. Deduplicação no banco em duas camadas — o par (feed, guid) e
  a URL normalizada, que pega o mesmo artigo chegando por dois feeds. Artigo
  antigo ganha marca de possivelmente desatualizado e o acervo é podado pela
  janela em Ajustes. Estudo de custo-benefício em
  `docs/decisoes/0002-agregador-de-leituras.md`.
- **"Portais que não entram, e por quê"** em Ajustes: a ausência de um portal
  grande parece defeito, e quem procura o LinkedIn na lista de fontes e não acha
  conclui que o app está quebrado. A tela agora diz o critério, nomeia cada
  portal recusado com a evidência datada e o link para a decisão, e mostra ao
  lado o caminho que substitui a fonte — cadastrar a candidatura à mão no
  Pipeline e marcar no Roadmap a tecnologia que a vaga pede. Vagas e Pipeline
  apontam para lá. Os cinco feeds abertos equivalentes entram com um clique.
- **`docs/decisoes/`**: registro das escolhas que alguém reabriria sem elas,
  principalmente as que terminaram em *não fazer*.

- **Restaurar backup**, que não existia: o app exportava JSON desde a primeira
  versão e nunca soube lê-lo de volta. O backup passa a ser um ZIP com o
  manifesto e os PDFs de currículo enviados, porque o JSON sozinho referenciava
  arquivos que não estavam dentro dele. A chave da API não entra no arquivo.
- **`/agenda.ics`**: as próximas ações com data viram compromissos de dia
  inteiro em iCalendar, com alarme na véspera. Dá para baixar ou assinar a URL
  no calendário do celular.
- Vaga que para de aparecer nas coletas por três semanas passa a ser marcada
  como **fora do ar**: sai da lista, do roadmap e das métricas, mas continua no
  banco. Antes a base só crescia, e o roadmap calculava demanda sobre anúncio
  morto. A marcação nunca ocorre depois de uma rodada em que todas as fontes
  falharam.
- Reordenar cartão dentro da coluna do pipeline passa a funcionar: a coluna
  `position` existia no esquema e no `ORDER BY` desde o começo, mas nunca era
  escrita. Mudar de etapa também posiciona o cartão no fim da coluna de destino.
- Tela de **Métricas**: conversão entre etapas do funil, tempo mediano de cada
  passo, ritmo semanal de envios e respostas, candidaturas paradas, retorno por
  fonte, faixa salarial das vagas coletadas e a comparação entre o fit das vagas
  que responderam e o das que não responderam. Todo o dado já estava gravado em
  `events` desde a primeira versão e nunca era devolvido como informação.
- Coluna `events.to_status`, com backfill que relê o histórico já gravado a
  partir da frase "De → Para". Sem ela, as métricas teriam de adivinhar a etapa
  a partir de texto livre.
- Fonte **Vagas BR**: os murais que a comunidade brasileira mantém como issues
  do GitHub (`backend-br/vagas` e outros cinco). É a primeira fonte embutida em
  português e a primeira a trazer vaga híbrida e presencial em quantidade — o
  filtro por modelo de trabalho devolvia lista vazia porque todas as fontes
  eram portais de trabalho remoto.

### Decidido

- **LinkedIn não entra como fonte de vagas** (issue #10). O `robots.txt` do site
  proíbe acesso automatizado sem permissão expressa (`User-agent: *` /
  `Disallow: /`) e as únicas permissões autosserviço da API oficial são login e
  publicação — nenhuma lê anúncio. Ficou valendo o critério para as próximas
  fontes: só entra portal cujo `robots.txt` permita, ou que ofereça API ou feed
  público para este uso. As alternativas abertas verificadas estão listadas no
  README e em `docs/decisoes/0001-linkedin-como-fonte.md`.

### Corrigido

- **O instalador travava quando rodava sem terminal**, e com ele o mecanismo que
  deveria propagar ícone e atalho novos. `uv venv` sobre um `.venv` existente
  pergunta se pode substituí-lo; sem tty ele não pergunta, sai com erro, o
  `set -e` aborta o `install.sh` em 1/5 e o `_refresh_system_shortcut` do
  `farol update` — que chama o script com a saída capturada — nunca chegava à
  etapa do atalho. Ou seja: a correção de ícone da versão anterior não surtia
  efeito em nenhuma máquina que já tivesse o ambiente criado, que é toda máquina
  que já tinha o Farol. `uv venv --allow-existing` resolve, e de quebra reusar o
  ambiente deixa a reinstalação muito mais rápida.
- O filtro de nível da lista de vagas e o casamento dos alertas passam a ler a
  mesma lista de termos (`scoring.LEVEL_TERMS`). Mantê-las escritas à mão em dois
  lugares era garantir que um dia divergissem, e aí o alerta avisaria de vaga que
  o filtro da tela não mostra.

## [1.0.0] — 2026-08-20

Primeira versão pública. O aplicativo passa a funcionar nos três sistemas
operacionais e deixa de depender de scripts de shell específicos do Linux.

### Adicionado

- Instaladores para **Linux, macOS e Windows** (`install.sh`, `install.ps1`),
  com atalho no menu, ícone e comando de terminal em cada sistema.
- Abertura do aplicativo em Python (`farol abrir`), substituindo o lançador em
  bash. Funciona nos três sistemas e abre janela dedicada quando há navegador
  baseado em Chromium instalado.
- Executáveis únicos por sistema, construídos com PyInstaller e publicados a
  cada tag (`packaging/farol.spec`).
- Imagem Docker e `compose.yaml` para quem quer rodar num servidor de casa.
- Comandos `farol versao` e `farol caminho`; `farol --help` com exemplos.
- Página de erro para endereço inexistente, no lugar da resposta JSON crua.
- Diretório de dados conforme a convenção de cada sistema:
  `~/.local/share/farol` no Linux, `~/Library/Application Support/Farol` no
  macOS e `%LOCALAPPDATA%\Farol` no Windows.
- Integração contínua em Linux, macOS e Windows, do Python 3.10 ao 3.13.
- `LICENSE` (MIT), `CONTRIBUTING.md`, `SECURITY.md`, `CODE_OF_CONDUCT.md`,
  modelos de issue e pull request.

### Corrigido

- **Termo de busca com mais de uma palavra devolvia lista vazia** em Arbeitnow,
  Himalayas, We Work Remotely e feeds RSS: o filtro exigia a frase literal na
  descrição. Agora exige todas as palavras, em qualquer posição.
- **RemoteOK não retornava nada** com termo de mais de uma palavra: a API aceita
  uma tag só. Agora envia a primeira palavra e confere as demais no resultado.
- **Himalayas respondia 403** desde que o portal passou a barrar `User-Agent` de
  navegador sem JavaScript. O aplicativo agora se identifica honestamente
  (`Farol/versão`), o que resolve o bloqueio — e é a postura correta para um
  coletor. A fonte também pagina: 60 vagas por rodada em vez de 20.
- **O servidor congelava** durante "testar fonte", ao salvar o perfil e ao salvar
  ajustes: trabalho bloqueante rodava no laço de eventos. Agora vai para uma
  thread separada.
- Erro 500 ao enviar valor não numérico em `id` ou `job_id`, e ao chamar a troca
  de etapa do pipeline com corpo JSON vazio.
- Estado de vaga fora da lista (`novo`, `descartada`) era aceito e tornava a vaga
  invisível em todos os filtros.
- Feed RSS cadastrado recebia identificador derivado de `hash()`, aleatório por
  processo: o mesmo feed voltava duplicado depois de reiniciar o aplicativo.
- Feed RSS era buscado uma vez por termo de busca, sem que o termo tivesse efeito
  sobre ele. Passa a ser buscado uma vez por rodada.

### Desempenho

Medido com 208 vagas na base, melhor de cinco execuções:

| Tela | Antes | Depois |
|---|---|---|
| Roadmap | 1145 ms | 7 ms |
| Painel | 370 ms | 5 ms |
| Vagas | 15 ms | 10 ms |

- As skills de cada vaga passam a ser gravadas na ingestão (coluna
  `jobs.skills`). O Roadmap e o Painel liam a descrição de até 400 vagas e
  reexecutavam a extração por expressão regular a cada abertura da tela.
- Conexão do SQLite reaproveitada por thread, com WAL e `synchronous=NORMAL`.
  Antes cada consulta abria o arquivo e reaplicava os PRAGMAs.
- Listagem de vagas deixa de trazer a descrição completa (até 20 KB por vaga,
  50 por página) em consulta que não a usa.
- Compressão gzip nas respostas: a lista de vagas caiu de 94 KB para 5,9 KB.
- Portais são consultados em paralelo. A pausa entre requisições ao mesmo portal
  continua valendo.
- Repontuação em uma única transação, com índices novos para os filtros da
  listagem, o pipeline e os currículos.

### Acessibilidade

- Cada cartão do pipeline ganhou um seletor de etapa. Arrastar e soltar não
  existe em tela de toque nem no teclado, e era o único caminho para mudar a
  etapa a partir do quadro.
- A falha ao salvar a etapa deixou de usar `alert()`, que bloqueia a página
  inteira: o aviso aparece na barra e o cartão volta para a coluna de origem, em
  vez de mostrar um estado que não foi gravado.

### Modificado

- Nome de distribuição no PyPI: `farol-carreira` (o comando continua `farol`).
- `app.css` e `app.js` passam a carregar com a versão na URL. Sem isso, o
  navegador continuava servindo a folha antiga do cache depois de o usuário
  atualizar o aplicativo.
- Lacunas já incluídas no plano de estudo aparecem marcadas na tela do Roadmap,
  e o mesmo botão passa a remover o item.

