<div align="center">
  <img src="assets/farol-128.png" alt="" width="88" height="88">

# Farol

**Central de carreira local para quem procura emprego em tecnologia.**

Coleta vagas remotas em portais públicos, pontua cada uma contra o seu perfil,
acompanha as candidaturas, monta currículos direcionados e calcula o que estudar
em seguida. Sem conta, sem nuvem, sem assinatura.

[![CI](https://github.com/Bappoz/farol/actions/workflows/ci.yml/badge.svg)](https://github.com/Bappoz/farol/actions/workflows/ci.yml)
[![Licença MIT](https://img.shields.io/badge/licen%C3%A7a-MIT-informational)](LICENSE)
[![Python 3.10+](https://img.shields.io/badge/python-3.10%2B-blue)](https://www.python.org/downloads/)
[![Linux, macOS e Windows](https://img.shields.io/badge/sistemas-Linux%20%C2%B7%20macOS%20%C2%B7%20Windows-lightgrey)](#instalação)

**Português** · [English](README.en.md)

</div>

---

## Sumário

- [Visão geral](#visão-geral)
- [Instalação](#instalação)
- [Primeiro uso](#primeiro-uso)
- [Funcionalidades](#funcionalidades)
  - [Pontuação de aderência](#pontuação-de-aderência)
  - [Filtros da lista de vagas](#filtros-da-lista-de-vagas)
  - [Currículos](#currículos)
  - [Roadmap de estudos](#roadmap-de-estudos)
  - [Métricas](#métricas)
- [Fontes de vagas](#fontes-de-vagas)
- [Política de coleta](#política-de-coleta)
- [Assistente por inteligência artificial](#assistente-por-inteligência-artificial)
- [Linha de comando](#linha-de-comando)
- [Dados e backup](#dados-e-backup)
- [Execução em contêiner](#execução-em-contêiner)
- [Arquitetura](#arquitetura)
- [Desenvolvimento](#desenvolvimento)
- [Privacidade e segurança](#privacidade-e-segurança)
- [Licença](#licença)

---

## Visão geral

O Farol é um aplicativo de desktop que roda inteiramente na máquina do usuário.
O servidor escuta apenas em `127.0.0.1`, os dados ficam em um arquivo SQLite no
diretório do usuário e nenhuma informação é enviada para serviços externos —
exceto as requisições de leitura aos portais de vagas e, quando explicitamente
habilitado, ao assistente por inteligência artificial.

| Tela | Finalidade |
|------|------------|
| **Painel** | Funil de candidaturas, meta semanal, próximas ações atrasadas e as vagas de maior aderência no momento. |
| **Vagas** | Vagas coletadas de seis portais mais os feeds RSS cadastrados, com pontuação de 0 a 100 explicada item a item e filtros combináveis. |
| **Métricas** | Conversão entre etapas, tempo mediano de cada passo, ritmo semanal, candidaturas esquecidas, retorno por fonte e faixa salarial das vagas coletadas. |
| **Pipeline** | Quadro das candidaturas por etapa, com histórico e próximo passo. O cartão muda de coluna por arraste ou pelo seletor de etapa, que funciona no teclado e no celular. |
| **Currículos** | Currículo base e versões direcionadas a uma vaga, em português ou inglês, em quatro modelos de apresentação, com verificação antes do envio, carta de apresentação e geração de PDF. Também armazena PDFs prontos. |
| **Roadmap** | Lacunas de competência calculadas sobre as vagas que as suas buscas trouxeram, com projetos e certificações recomendados. |
| **Perfil** | Fonte única de verdade: alimenta a pontuação, os currículos e o roadmap. |
| **Ajustes** | Termos de busca, fontes com diagnóstico de erro, preferências de região, notificação no desktop e a chave opcional da API. |

---

## Instalação

O aplicativo requer **Python 3.10 ou superior**. As distribuições Linux
recentes e o macOS já o incluem; no Windows, o instalador indica como obtê-lo
caso não esteja presente.

### Linux e macOS

```bash
git clone https://github.com/Bappoz/farol.git
cd farol
./install.sh
```

O script cria um ambiente Python isolado, instala o aplicativo, prepara o banco
de dados e registra o atalho no sistema: uma entrada `.desktop` no menu, no
Linux, e um pacote `Farol.app` em `~/Applications`, no macOS. O comando `farol`
fica disponível no terminal.

### Windows

```powershell
git clone https://github.com/Bappoz/farol.git
cd farol
powershell -ExecutionPolicy Bypass -File .\install.ps1
```

O script cria o ambiente, instala o aplicativo, adiciona o atalho no Menu
Iniciar e registra o comando `farol` no `PATH` do usuário. Use
`-ComAreaDeTrabalho` para criar também um atalho na área de trabalho.

### Executável único

As páginas de [Releases](https://github.com/Bappoz/farol/releases) trazem um
executável por sistema, com o interpretador Python embutido. Baixe, extraia e
execute — não há instalação nem dependências.

Esses arquivos não são assinados digitalmente. No macOS, libere o executável com
`xattr -d com.apple.quarantine farol` antes do primeiro uso; no Windows, o
SmartScreen pede confirmação em *Mais informações → Executar assim mesmo*.

### Via pip ou pipx

```bash
pipx install farol-carreira
farol
```

Esta forma instala apenas o comando, sem atalho no menu do sistema.

### Desinstalação

```bash
./uninstall.sh                                                    # Linux e macOS
powershell -ExecutionPolicy Bypass -File .\uninstall.ps1          # Windows
```

Os dados **não** são apagados. Para removê-los também, acrescente `--com-dados`
(ou `-ComDados` no Windows); a confirmação é solicitada.

---

## Primeiro uso

1. **Perfil.** Preencha antes de qualquer outra coisa: a pontuação, o currículo
   e o roadmap derivam dele. Competências são separadas por vírgula e o
   aplicativo reconhece abreviações comuns (`js`, `k8s`, `postgres`).
2. **Ajustes.** Cadastre de dois a quatro termos de busca. Termos em inglês
   produzem muito mais resultado nestes portais: `junior backend`,
   `entry level data`, `trainee software`.
3. **Vagas → Atualizar vagas.** A coleta busca, remove duplicatas e pontua.
4. **Salvar** uma vaga cria o cartão no pipeline com um próximo passo sugerido.
5. **Gerar currículo direcionado** na página da vaga, revisar a verificação e
   usar *Ver / gerar PDF* → *Salvar como PDF* no diálogo de impressão.
6. **Roadmap.** O que aparece com frequência nas suas vagas e falta no seu perfil
   se converte em projeto ou certificação recomendada.

---

## Funcionalidades

### Pontuação de aderência

Cada vaga recebe uma nota de 0 a 100, soma de cinco componentes. A tela exibe a
conta completa, componente por componente, com a frase que justifica cada nota.

| Componente | Faixa | Critério |
|------------|-------|----------|
| Competências | 0–55 | Quanto do que a vaga pede já consta no seu perfil. |
| Senioridade | 0–20 | Vaga de entrada pontua; vaga sênior reduz a nota. |
| Região | 0–10 | Aceita candidatos no Brasil ou na América Latina. |
| Recência | 0–10 | Vaga publicada hoje vale mais que vaga de três semanas. |
| Preferências | 0–5 | Suas palavras-chave; termo excluído no título derruba a vaga. |

O cálculo é determinístico e local. Não há modelo estatístico, chamada de rede
nem caixa-preta: a mesma vaga com o mesmo perfil produz sempre a mesma nota, e a
nota é auditável na própria interface.

### Filtros da lista de vagas

Todos os filtros combinam entre si e com a busca textual.

| Filtro | Comportamento |
|--------|---------------|
| **Região** | Agrupa a localização em Brasil, América Latina, Mundial ou Outra, resolvendo a fragmentação dos rótulos: `Brazil` e `Brazil, Latin America` caem no mesmo grupo. |
| **Localização exata** | Lista apenas os valores presentes na sua base, com a contagem de cada um. É um campo de seleção justamente para evitar erro de digitação. Aplica-se também a vagas remotas: é nesse campo que os portais informam de onde aceitam candidatos. |
| **Modelo** | Remoto, híbrido, presencial ou todos. |
| **Salário mínimo** | Compara com o topo da faixa anunciada e **apenas entre vagas da mesma moeda**. Valor mensal é normalizado para anual (multiplicado por doze). |

Duas restrições são deliberadas no filtro de salário. O aplicativo **não infere a
moeda** quando o anúncio não a declara — a vaga fica fora do filtro em vez de ser
tratada como dólar — e **não estima faixa** para quem não publicou nenhuma. Como
a maioria dos anúncios não publica salário, limpar o campo devolve essas vagas à
lista.

Quando o resultado é vazio, a tela informa a causa em vez de sugerir afrouxar a
pontuação. As cinco fontes embutidas são portais de trabalho remoto, de modo que
filtrar por presencial tende a produzir lista vazia; para vagas presenciais,
cadastre em Ajustes o feed RSS de um portal que as anuncie.

### Currículos

**Idioma.** Cada currículo tem o seu. Em inglês, o aplicativo troca os títulos
das seções (`SUMMARY`, `SKILLS`, `EXPERIENCE`) e o nome das competências de
rótulo português — `testes automatizados` passa a `Automated testing`. O modelo
da carta de apresentação também muda.

O que o aplicativo **não** faz é traduzir o seu texto: o currículo nasce com o
conteúdo do Perfil e a tradução é feita ali dentro. Cada currículo é um documento
próprio — cargo, empresa, período, marcadores, formação e idiomas são editáveis
campo a campo, e nada disso retorna ao Perfil. Assim é possível manter um Perfil
único, em português, e quantas versões em inglês forem necessárias. O botão
*Remontar a partir do perfil* refaz o documento do zero e, com isso, descarta as
traduções.

A pontuação das vagas independe do idioma: `unit tests` e `testes automatizados`
resolvem para a mesma competência canônica, assim como `junior`, `entry level`,
`trainee` e `estágio` para o mesmo nível de senioridade.

**Modelos de apresentação.** Quatro, escolhidos na criação e trocáveis a qualquer
momento no editor.

| Modelo | Quando usar |
|--------|-------------|
| **Sóbrio** *(recomendado, padrão)* | Uma coluna, sem ornamento. É o que passa limpo por filtro automático de currículos. |
| **Compacto** | Mesma estrutura em espaçamento menor, para caber em uma página. |
| **Com destaque** | Nome e títulos de seção em cor de acento. |
| **Moderno** | Sem serifa, nome em corpo maior, barra no título da seção. |

O modelo sóbrio é o recomendado por uma razão concreta: quando o anúncio pede o
envio do currículo por formulário, é quase certo que um filtro automático o leia
antes de qualquer pessoa, e coluna lateral, cor de fundo e ícone são o que mais
o confunde. Os demais valem quando se sabe que uma pessoa abrirá o PDF
diretamente — indicação, feira, portfólio.

Os modelos alteram apenas o CSS de impressão sobre o mesmo HTML. Trocar de
modelo não altera nem perde nada do que foi escrito.

**PDF pronto.** É possível enviar um currículo que já existe em PDF (até 15 MB),
pela tela de Currículos ou diretamente na página da vaga. Ele aparece na lista
junto dos montados no editor, vinculado à vaga, e o arquivo é guardado no
diretório de dados. O aplicativo não modifica o PDF.

O texto é extraído de volta — via `pypdf`, com `pdftotext` como alternativa —
para três finalidades: mostrar o que um filtro automático enxerga, comparar com a
vaga (*o que ela pede e aparece no seu PDF* × *o que falta*) e sugerir ao Perfil
as competências presentes no arquivo que ainda não foram cadastradas. Se o PDF
for uma imagem digitalizada, o aplicativo informa que não há camada de texto em
vez de simular a leitura, e avisa: é assim que filtros automáticos costumam
reprovar currículos.

**Descrição da vaga.** Cada portal entrega a descrição em um HTML diferente. Na
ingestão, o aplicativo reduz o conteúdo a texto marcando a estrutura (`## ` para
título de seção, `- ` e `1. ` para listas) e, na exibição, `farol.markup`
remonta títulos, listas e parágrafos, convertendo URLs em links. O texto do
anúncio é escapado antes de qualquer marcação: ele vem de terceiros e nunca pode
injetar HTML na página.

**Sem invenção.** O gerador de currículo reordena e destaca o que consta no seu
perfil, e nada além disso. Onde falta informação, escreve `[preencher]` e diz o
que falta. A revisão opcional por inteligência artificial recebe a mesma regra na
instrução de sistema.

### Roadmap de estudos

As lacunas são calculadas sobre as vagas que as **suas** buscas trouxeram, e não
sobre uma lista genérica de tecnologias em alta. Cada competência ausente do
perfil aparece com a frequência real na sua base, e o catálogo de projetos e
certificações é ordenado pelo quanto cobre essas lacunas.

Itens marcados formam um quadro de acompanhamento em três estados: planejado,
fazendo e concluído.

### Métricas

A tela responde à pergunta que o funil sozinho não responde: **onde a busca está
travando**. Quarenta candidaturas sem nenhuma triagem é um problema de currículo;
quarenta candidaturas com doze triagens e nenhuma entrevista é um problema de
conversa técnica. São diagnósticos opostos, e sem os números não há como
distingui-los.

| Bloco | O que mostra |
|-------|--------------|
| **Funil** | Quantas candidaturas chegaram a cada etapa, com a conversão de uma para a seguinte. Conta a etapa mais avançada alcançada, não a atual: uma recusa após a entrevista conta na entrevista. |
| **Ritmo** | Envios e respostas por semana, nas últimas oito. |
| **Tempo entre etapas** | Mediana de dias de cada passo, com o tamanho da amostra ao lado. Serve para saber quando cobrar retorno. |
| **Paradas** | Candidaturas ativas sem movimento há mais de dez dias. |
| **O fit prevê resposta?** | Pontuação média das vagas que responderam contra as que não responderam — uma checagem da própria pontuação contra o resultado real. |
| **Retorno por fonte** | De qual portal saem as candidaturas que avançam. |
| **Faixa salarial** | Média das faixas publicadas nas vagas coletadas, por moeda. |

Todos os números são descritivos: não há previsão, modelo nem recomendação
automática. Percentual só aparece a partir de cinco candidaturas na amostra, e
etapa sem dado exibe "sem dado" em vez de um número inventado.

---

## Fontes de vagas

Seis fontes embutidas, todas APIs ou feeds públicos, sem necessidade de chave:
**Remotive**, **RemoteOK**, **Arbeitnow**, **Himalayas**, **We Work Remotely** e
**Vagas BR**.

**Vagas BR** reúne os murais que a comunidade brasileira mantém no GitHub —
`backend-br/vagas`, `frontendbr/vagas`, `react-brasil/vagas`, `androiddevbr/vagas`,
`phpdevbr/vagas` e `datascience-br/vagas`. É a única fonte embutida em português,
e a única que traz vaga híbrida e presencial em quantidade. Ela não recebe termo
de busca: cada repositório já é a seleção, e filtrar anúncio em português por
termo escrito para portal em inglês devolveria lista vazia.

**Vaga que sai do ar.** Nenhum portal avisa quando remove um anúncio; o único
sinal é ele parar de aparecer nas coletas. Depois de três semanas sem reaparecer
(`FAROL_STALE_DAYS` ajusta), a vaga é marcada como *fora do ar*: some da lista e
deixa de contar no roadmap e nas métricas, mas continua no banco, porque pode
estar ligada a uma candidatura em andamento. O filtro *Estado → fora do ar* traz
essas vagas de volta à tela. A marcação só acontece depois de uma rodada que
trouxe resultado — se todas as fontes falharam, o sumiço é da rede, não do
anúncio.

Um portal fora do ar ou uma API que mudou de formato não derruba a coleta: a
fonte é marcada como erro em Ajustes, com a mensagem original, e o botão
**testar** executa apenas aquela fonte.

Para acrescentar um portal que publique RSS ou Atom, basta colar a URL do feed em
Ajustes → *Adicionar feed*. Para um portal com API própria, o procedimento está
descrito em [CONTRIBUTING.md](CONTRIBUTING.md#adicionar-uma-fonte-de-vagas).

O termo de busca casa **todas as palavras** informadas, em qualquer posição do
anúncio. `junior backend python` encontra vagas que mencionem as três palavras,
ainda que separadas — não a frase literal.

---

## Política de coleta

O Farol consulta portais de terceiros e trata isso com as restrições que a
situação exige.

**Identificação honesta.** O cabeçalho `User-Agent` declara o nome, a versão e o
endereço do projeto. O aplicativo não se faz passar por navegador.

**Uma coleta por abertura.** Abrir o aplicativo dispara uma rodada e apenas uma.
A janela abre imediatamente e o indicador *coletando vagas nos portais* fica na
barra superior; ao terminar, o Painel e a lista de Vagas se atualizam sozinhos.

**Janela de descanso.** Entre uma abertura e outra vale o intervalo mínimo
configurado em Ajustes, de 45 minutos por padrão. Reabrir o aplicativo cinco
vezes em dez minutos não gera nenhuma requisição adicional. É o que evita a
rajada — e o CAPTCHA e o bloqueio por endereço que costumam vir depois dela.

**Pausa entre requisições.** Dentro de uma rodada, requisições consecutivas ao
**mesmo** portal são espaçadas em 1,5 segundo (`FAROL_REQUEST_DELAY` ajusta).
Portais distintos são consultados em paralelo, por serem servidores diferentes.

**Escape manual.** O botão **Atualizar vagas**, no Painel e em Vagas, ignora a
janela de descanso e executa a coleta imediatamente.

O uso é pessoal. Respeite os termos de cada portal.

---

## Assistente por inteligência artificial

Opcional e desligado por padrão. Ao inserir uma chave da API Anthropic em
Ajustes, três botões passam a existir: revisar o resumo, reescrever os marcadores
e revisar a carta de apresentação.

Sem chave configurada, os botões não aparecem e todo o restante funciona
igualmente: a pontuação, o roadmap e o currículo são calculados localmente, sem
qualquer acesso à rede.

---

## Linha de comando

```
farol                 abre o aplicativo (sobe o servidor e abre a janela)
farol servir          apenas o servidor, no primeiro plano
farol atualizar       apenas a coleta de vagas
farol caminho         mostra onde ficam o banco e os arquivos
farol versao          mostra a versão instalada
farol update          verifica se há uma versão nova do app e atualiza
```

Opções: `--port`, `--host`, `--reload` e `--sem-navegador`. Use `farol --help`
para a descrição completa.

O comando `farol atualizar` imprime uma linha por fonte com o que foi encontrado
ou o erro exato, e **ignora** a janela de descanso. Ao agendá-lo em `cron` ou no
Agendador de Tarefas, escolha um intervalo folgado — uma ou duas vezes ao dia —
pela mesma razão descrita em [Política de coleta](#política-de-coleta).

O comando `farol update` só funciona quando o app foi instalado a partir de um
clone git (o caminho descrito em [Instalação](#instalação)): ele busca o
repositório remoto, compara com o commit instalado e, se houver algo novo, faz
`git pull --ff-only` e reinstala as dependências no mesmo ambiente. Com mudanças
locais não commitadas ele se recusa a mexer — resolva-as primeiro.

---

## Dados e backup

Tudo fica em um único diretório, por convenção de cada sistema:

| Sistema | Diretório |
|---------|-----------|
| Linux | `$XDG_DATA_HOME/farol` (por padrão `~/.local/share/farol`) |
| macOS | `~/Library/Application Support/Farol` |
| Windows | `%LOCALAPPDATA%\Farol` |

A variável `FAROL_HOME` sobrescreve essa escolha. O comando `farol caminho`
mostra os caminhos em uso.

O diretório contém `farol.db` (o banco SQLite), a pasta `curriculos/` com os PDFs
enviados e `server.log`. Fica **fora** da pasta do projeto de propósito: para
atualizar o aplicativo, basta extrair a versão nova sobre a antiga — colunas
novas são aplicadas na abertura seguinte, sem apagar nada.

**Backup e restauração.** Ajustes → *Backup completo* gera um ZIP com perfil,
candidaturas e todo o histórico de etapas, currículos (inclusive os PDFs
enviados), plano de estudo e ajustes. *Restaurar* lê o mesmo arquivo de volta —
ou um JSON solto de versões anteriores — e **substitui** os dados atuais, o que
exige digitar a confirmação.

As vagas coletadas ficam de fora do backup de propósito: elas se refazem sozinhas
na próxima coleta e ocupariam a maior parte do arquivo. A chave da API também
nunca entra: backup que carrega credencial vira credencial espalhada.

**Agenda.** `/agenda.ics` devolve as próximas ações com data marcada em formato
iCalendar, uma tarefa de dia inteiro por candidatura, com alarme na véspera.
Baixe o arquivo ou assine a URL no calendário do celular para vê-la sempre
atual. Um follow-up anotado num aplicativo que só abre quando a pessoa lembra de
abrir não lembra ninguém de nada.

---

## Execução em contêiner

Para manter o Farol disponível em um servidor doméstico:

```bash
docker compose up -d          # http://127.0.0.1:7788
```

O `compose.yaml` publica a porta apenas em `127.0.0.1`, de propósito. O Farol não
possui autenticação, e a base contém dados pessoais: para alcançá-lo de outra
máquina, coloque um proxy reverso com autenticação à frente em vez de expor a
porta na rede. Consulte [SECURITY.md](SECURITY.md).

---

## Arquitetura

```
farol/
  app.py          rotas e renderização (FastAPI + Jinja, tudo no servidor)
  db.py           SQLite sem ORM, schema.sql e migrações de coluna
  collect.py      ingestão: busca, deduplicação, gravação e pontuação
  scoring.py      pontuação explicável, modelo de trabalho, região e faixa salarial
  skills.py       taxonomia de competências e extração de texto
  markup.py       descrição da vaga em HTML legível (escapa antes de marcar)
  resume.py       montagem de currículo, carta e verificação
  pdfs.py         PDFs enviados: armazenar, servir e extrair texto
  roadmap.py      lacunas, projetos e certificações
  launcher.py     abertura do aplicativo em Linux, macOS e Windows
  sources/        um módulo por portal, leitor RSS genérico e casamento de termos
  data/           catálogo de projetos e certificações (JSON editável)
  templates/      páginas
  static/         app.css, app.js e ícone
packaging/        especificação do executável único (PyInstaller)
assets/           ícones nos formatos de cada sistema
```

Sem etapa de build, sem `npm`, sem framework de front-end. O CSS é uma folha
única, com tokens no topo e tema claro e escuro que segue o sistema; o botão
*Tema*, na barra lateral, força um dos dois.

O banco é SQLite em modo WAL, com a conexão reaproveitada por thread. As
competências de cada vaga são extraídas uma vez, na ingestão, e gravadas na linha
— é o que mantém o Painel e o Roadmap na casa dos milissegundos independentemente
do tamanho da base.

---

## Desenvolvimento

```bash
./install.sh --sem-atalho              # ambiente e instalação editável
.venv/bin/python -m farol servir --reload
.venv/bin/python -m pytest             # 132 testes, sem acesso à rede
.venv/bin/ruff check farol tests
```

Com [`just`](https://github.com/casey/just): `just setup`, `just dev`,
`just check`, `just binary`, `just docker`. O `justfile` é a referência canônica
dos comandos do projeto.

A suíte de testes não acessa a rede: os coletores são exercitados contra
respostas HTTP gravadas em `tests/fixtures/`.

Consulte [CONTRIBUTING.md](CONTRIBUTING.md) antes de abrir um pull request.

---

## Privacidade e segurança

O servidor escuta em `127.0.0.1` e não possui autenticação, porque assume que o
único cliente é a pessoa sentada na máquina. Os dados não são cifrados em
repouso. O modelo de ameaça completo, as superfícies consideradas no projeto e o
canal para relatar vulnerabilidades estão em [SECURITY.md](SECURITY.md).

---

## Licença

[MIT](LICENSE). O histórico de mudanças está em [CHANGELOG.md](CHANGELOG.md).
