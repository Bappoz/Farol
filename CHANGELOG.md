# Changelog

Formato baseado em [Keep a Changelog](https://keepachangelog.com/pt-BR/1.1.0/).
Versionamento conforme [SemVer](https://semver.org/lang/pt-BR/).

## [Não publicado]

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

