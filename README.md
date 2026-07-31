# Farol

Central de carreira local. Um aplicativo só seu, que abre pelo menu do Omarchy e roda inteiro
na sua máquina: busca vagas remotas nos portais, pontua cada uma contra o seu perfil, acompanha
suas candidaturas, monta currículo direcionado e diz o que estudar em seguida.

Sem conta, sem nuvem, sem assinatura. Os dados ficam em um SQLite dentro de `~/.local/share/farol`.

## O que ele faz

| Tela | Para quê |
|------|----------|
| **Painel** | Funil das candidaturas, meta semanal, próximas ações atrasadas e as melhores vagas do momento. |
| **Vagas** | Coleta de 5 portais + qualquer feed RSS que você adicionar, com fit score de 0 a 100 explicado item a item e filtros combináveis (região, localização, modelo de trabalho, salário). |
| **Pipeline** | Kanban de candidaturas (salva → candidatado → triagem → entrevista → teste → oferta), com histórico e próximo passo. |
| **Currículos** | Currículo base + versões direcionadas a uma vaga, em **português ou inglês**, em **quatro modelos** de apresentação, com checagem antes de enviar, carta e PDF pela impressão. Também guarda **PDFs que você já tem**. |
| **Roadmap** | Lacunas de skill calculadas sobre as vagas que **as suas buscas** trouxeram, com projetos e certificações recomendados. |
| **Perfil** | Fonte única da verdade: alimenta pontuação, currículo e roadmap. |
| **Ajustes** | Termos de busca, fontes (com diagnóstico de erro), preferências de região, aviso no desktop e a chave opcional da API. |

### O fit score não é caixa-preta

Cada vaga recebe uma nota de 0 a 100 somando cinco componentes, e a tela mostra a conta:

```
skills       0–55   quanto do que a vaga pede você já tem
senioridade  0–20   vaga de entrada pontua; vaga sênior derruba
região       0–10   aceita quem está no Brasil / América Latina
recência     0–10   vaga de hoje vale mais que vaga de três semanas
preferências 0–5    suas palavras-chave; termo excluído no título afunda a vaga
```

### Filtros da lista de vagas

Todos combinam entre si e com a busca por texto:

| Filtro | O que faz |
|--------|-----------|
| **Região** | Agrupa a localização em Brasil / América Latina / Mundial / Outra. Resolve a fragmentação dos rótulos: `Brazil` e `Brazil, Latin America` caem no mesmo grupo. |
| **Localização exata** | Lista só os valores que existem na sua base, com a contagem. É um select justamente para não haver erro de digitação. Vale para vaga remota: é ali que os portais dizem de onde aceitam candidato. |
| **Modelo** | Remoto, híbrido, presencial ou todos. |
| **Salário mínimo** | Compara com o topo da faixa anunciada, e **só entre vagas da mesma moeda** — o app não converte câmbio, então nunca compara euro com dólar. Valor mensal é normalizado para anual (×12). |

Duas coisas que o filtro de salário **não** faz, de propósito: não chuta a moeda quando o anúncio
não diz qual é (a vaga fica de fora do filtro em vez de ser tratada como dólar), e não inventa faixa
para quem não publicou nenhuma. A maioria dos anúncios não publica salário — limpar o campo mostra
essas vagas de novo.

Quando o resultado é vazio, a tela diz *por quê* em vez de mandar afrouxar o fit. As cinco fontes
embutidas são portais de trabalho remoto, então filtrar por presencial tende a dar lista vazia: para
vaga de escritório, adicione em Ajustes o feed RSS de um portal que anuncie presencial.

### Aviso no desktop (opcional)

Ligue em Ajustes para receber uma notificação quando a coleta trouxer vaga nova acima do fit que
você escolher. Usa o `notify-send` da sua sessão; sem ele instalado o aviso é ignorado em silêncio,
porque coleta não pode falhar por causa de um aviso. Vem desligado.

### Currículo em inglês

Cada currículo tem seu próprio idioma. Em inglês, o app troca os títulos das seções
(`SUMMARY`, `SKILLS`, `EXPERIENCE`…) e o nome das competências de rótulo português —
`testes automatizados` vira `Automated testing`, `acessibilidade` vira `Accessibility`. O modelo
da carta de apresentação também muda.

O que ele **não** faz é traduzir o seu texto: o currículo nasce com o conteúdo do Perfil e você
traduz ali dentro. Cada currículo é um documento próprio — cargo, empresa, período, marcadores,
formação e idiomas são editáveis campo a campo, e nada disso volta para o Perfil. Assim você mantém
um Perfil só, em português, e quantas versões em inglês quiser. O botão *Remontar a partir do
perfil* refaz o documento do zero quando o Perfil mudou (e aí sim descarta as traduções).

A pontuação das vagas não se importa com idioma: `unit tests` e `testes automatizados` caem na mesma
skill canônica, e o mesmo vale para senioridade (`junior`, `entry level`, `trainee`, `estágio`).

### Modelos de currículo

Quatro modelos, escolhidos na criação e trocáveis a qualquer momento no editor:

| Modelo | Quando usar |
|--------|-------------|
| **Sóbrio** *(recomendado, padrão)* | Uma coluna, sem enfeite. É o que passa limpo por filtro de ATS. |
| **Compacto** | Mesma estrutura em espaçamento menor — ajuda a caber em uma página. |
| **Com destaque** | Nome e títulos de seção em cor de acento. |
| **Moderno** | Sem serifa, nome grande, barra no título da seção. |

**Sóbrio é o recomendado por um motivo concreto**: quando o anúncio manda subir o currículo num
formulário, é quase certo que um filtro automático (ATS) lê antes de qualquer pessoa, e coluna
lateral, cor de fundo e ícone são o que mais o confunde. Os outros valem quando você sabe que alguém
vai abrir o PDF direto — indicação, feira, portfólio.

Os modelos mudam **só o CSS da impressão** sobre o mesmo HTML: trocar de modelo não altera nem perde
nada do que você escreveu.

### PDF que você já tem

Dá para subir um currículo pronto em PDF (até 15 MB) na tela de Currículos ou direto na página da
vaga. Ele fica na lista junto com os montados no editor, ligado à vaga, e o arquivo é guardado em
`~/.local/share/farol/curriculos/` — o app não altera o PDF.

O texto é lido de volta (via `pypdf`, com `pdftotext` como alternativa) para três coisas: mostrar
**o que um filtro de ATS enxerga**, comparar com a vaga (*o que ela pede e aparece no seu PDF* × *o
que falta*) e sugerir ao Perfil as skills que aparecem lá e ainda não estão cadastradas — você marca
quais aceita. Se o PDF for imagem escaneada, o app diz que não há camada de texto em vez de fingir
que leu; e avisa, porque é assim que filtro automático costuma reprovar currículo.

### A descrição da vaga é remontada, não despejada

Cada portal manda a descrição num HTML diferente. Na ingestão o app reduz isso a texto marcando a
estrutura (`## ` para título de seção, `- ` e `1. ` para lista) e, na hora de mostrar, `farol.markup`
remonta em títulos, listas e parágrafos, com URL virando link. Assim o anúncio é legível em vez de um
bloco corrido com tudo no mesmo nível.

O texto do anúncio é **escapado antes** de qualquer marcação: ele vem de portal de terceiro e nunca
pode injetar HTML na página. Descrição já gravada antes desses marcadores continua legível — cai no
caminho de parágrafo.

### O app não inventa experiência

O gerador de currículo reordena e destaca o que está no seu perfil — nada mais. Onde falta
informação, ele escreve `[preencher]` e diz o que falta. A revisão opcional por IA recebe a mesma
regra na instrução de sistema.

## Instalação

Requer Python 3.10+ (o Omarchy já vem com 3.13) e `curl`.

```bash
git clone <este-repositório> ~/Work/personal_repo/farol
cd ~/Work/personal_repo/farol
./install.sh
```

O script cria o ambiente virtual, prepara o banco, instala o ícone e escreve
`~/.local/share/applications/farol.desktop`. Depois disso:

- **Menu do Omarchy**: `SUPER + espaço` e digite `Farol`.
- **Terminal**: `farol` (link criado em `~/.local/bin`).

Se o nome não aparecer de imediato no menu, o launcher ainda está com a lista antiga em cache —
sair e entrar na sessão resolve (o `install.sh` já roda `update-desktop-database`).

O atalho executa `bin/farol-app`, que sobe o servidor local se ele ainda não estiver de pé e abre
uma janela dedicada — usando `omarchy-launch-webapp` quando existe, senão `chromium --app`.

### Uma coleta por abertura

Abrir o app dispara **uma** rodada de coleta e só. A janela abre na hora e o indicador
*coletando vagas nos portais…* fica na barra de cima; quando termina, o Painel e a lista de Vagas
se atualizam sozinhos com o resumo do que entrou.

Entre uma abertura e outra vale a **janela de descanso** (Ajustes → *intervalo mínimo entre coletas
automáticas*, 45 min por padrão): reabrir o app cinco vezes em dez minutos não gera requisição
nenhuma nos portais. É o que evita rajada — e o CAPTCHA e o bloqueio por IP que vêm depois dela.
Dentro da coleta ainda há 1,5 s de pausa entre requisições (`FAROL_REQUEST_DELAY` muda isso).

Quando você quiser dados frescos antes da hora, o botão **Atualizar vagas** (no Painel e em Vagas)
ignora a janela e roda na hora.

Para desfazer: `./uninstall.sh` (remove atalho, ícone e ambiente; **não** apaga seus dados).

## Uso no dia a dia

1. **Perfil** — preencha antes de tudo. Skills separadas por vírgula; o app entende apelidos
   (`js`, `k8s`, `postgres`).
2. **Ajustes** — escreva 2 a 4 termos de busca. Termos em inglês trazem muito mais resultado nesses
   portais (`junior backend`, `entry level data`, `trainee software`).
3. **Vagas → Atualizar vagas** — coleta, deduplica e pontua.
4. **Salvar** uma vaga cria o cartão no pipeline com um próximo passo já sugerido.
5. **Gerar currículo direcionado** na página da vaga, revisar a checagem, `Ver / gerar PDF` →
   *Salvar como PDF* no diálogo de impressão. Para vaga em inglês, crie o currículo com o idioma
   *English* e traduza os campos dentro dele.
6. **Roadmap** — o que aparece muito nas suas vagas e falta em você vira projeto ou certificação.

### Coleta sem abrir a janela

```bash
~/Work/personal_repo/farol/.venv/bin/python -m farol atualizar
```

Imprime uma linha por fonte com o que encontrou ou o erro exato. Este comando ignora a janela de
descanso — se você agendar em cron, escolha um intervalo folgado (uma ou duas vezes por dia) pelo
mesmo motivo do parágrafo acima.

## Fontes de vagas

Embutidas (APIs públicas, sem chave): **Remotive**, **RemoteOK**, **Arbeitnow**, **Himalayas** e
**We Work Remotely**. Todas são de uso pessoal — respeite os termos de cada portal.

Portal fora do ar ou API que mudou de formato não derruba a coleta: a fonte fica marcada como erro
em Ajustes, com a mensagem crua, e o botão **testar** roda só aquela fonte.

Para acrescentar um portal brasileiro (ou qualquer outro) que publique RSS, é só colar a URL do feed
em Ajustes → *Adicionar feed*. Para um portal com API própria, crie `farol/sources/meuportal.py`
com uma função `fetch(client, query)` e registre em `farol/sources/__init__.py`.

## Assistente por IA (opcional)

Cole uma chave da API Anthropic em Ajustes para liberar três botões: revisar o resumo, reescrever os
marcadores e revisar a carta. Sem chave, os botões não aparecem e todo o resto funciona igual — a
pontuação, o roadmap e o currículo são calculados localmente, sem rede.

## Desenvolvimento

```bash
.venv/bin/python -m pytest tests -q      # 100 testes, sem rede (fontes usam respostas gravadas)
.venv/bin/python -m farol servir --reload
```

Estrutura:

```
farol/
  app.py         rotas e renderização (FastAPI + Jinja, tudo server-side)
  db.py          SQLite sem ORM + schema.sql + migrações de coluna
  collect.py     ingestão: busca, deduplica, grava, pontua
  scoring.py     fit score explicável, modelo de trabalho, região e faixa salarial
  skills.py      taxonomia de skills e extração de texto
  markup.py      descrição da vaga → HTML legível (escapa antes de marcar)
  resume.py      montagem de currículo, carta e checagem
  pdfs.py        PDFs enviados por você: guardar, servir e extrair texto
  roadmap.py     lacunas, projetos e certificações
  sources/       um módulo por portal + leitor RSS genérico
  data/          catálogo de projetos e certificações (JSON editável)
  templates/     páginas
  static/        app.css, app.js, ícone
bin/farol-app    launcher usado pelo atalho do menu
install.sh       ambiente + .desktop + ícone
```

Sem build, sem npm, sem framework de front-end. O CSS é uma folha só, com tokens no topo e tema
claro/escuro (segue o sistema; o botão *Tema* na barra lateral força um dos dois).

## Dados

Tudo em `~/.local/share/farol/` — `farol.db` e a pasta `curriculos/` com os PDFs que você enviou
(ou em `$FAROL_HOME`). O banco fica **fora** da pasta do
projeto de propósito: para atualizar o app, extraia a versão nova por cima da pasta e abra de novo —
colunas novas são aplicadas sozinhas na abertura (`db.MIGRATIONS`), sem apagar nada. Ajustes → *Exportar backup* gera um JSON
com perfil, candidaturas, currículos e roadmap. Para mudar de máquina, copie o arquivo do banco.
