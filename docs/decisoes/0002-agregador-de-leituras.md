# 2. Agregador de leituras: só feed, só índice, só a pedido

- **Estado:** implementado
- **Data:** 2026-09-23
- **Issue:** [#9 — Adicionar agregador de artigos e novidades de tecnologia](https://github.com/Bappoz/farol/issues/9)

## Contexto

O issue pedia, antes do código, um **estudo de custo-benefício e de fontes com
feed público**. Um agregador é fácil de começar e fácil de transformar em peso
morto: mais uma tela para manter, mais tráfego de rede e mais banco, por um valor
que não é óbvio num aplicativo cujo assunto é candidatura, não leitura.

## Custo-benefício

**O que justifica existir.** O Roadmap já calcula lacunas de competência sobre as
vagas coletadas — ele diz *o que* estudar e não diz *por onde começar*. Um índice
de artigos marcado com a mesma taxonomia de skills fecha essa ponta sem inventar
conceito novo: `kubernetes` aparece como lacuna no Roadmap e como etiqueta no
artigo. O custo marginal é baixo porque o leitor de RSS/Atom (`farol.sources.rss`)
e a extração de skills (`farol.skills`) já existiam para as vagas.

**O que custaria caro, e por isso ficou de fora.**

| Alternativa avaliada | Por que não |
|---|---|
| Raspar blogs sem feed | Mesma fragilidade dos portais de vaga, por conteúdo que vale menos. Um seletor CSS que muda derruba a fonte em silêncio. |
| Guardar o texto completo do artigo | É republicação de obra de terceiro, e o issue proibia isso explicitamente. Também multiplicaria o tamanho do banco. |
| Ranquear/recomendar leitura com modelo | Caixa-preta num app que se define por pontuação explicável. A etiqueta de skill já ordena o suficiente. |
| Atualizar junto com a coleta de vagas | Dobraria o tráfego de uma rodada que já fala com seis portais, para um dado que ninguém pediu naquele momento. |

## Decisão

1. **Apenas RSS e Atom.** Feed é o canal que o autor abriu de propósito para ser
   lido por programa. Sem feed, sem fonte.
2. **Índice, não cópia.** Ficam gravados título, URL, data, feed de origem e um
   resumo cortado em `reading.SUMMARY_MAX` (400 caracteres) — e o resumo é o que o
   próprio feed publica, não um trecho extraído do corpo do artigo. Todo item leva
   ao site de quem escreveu.
3. **Opt-in de verdade.** Os dez feeds do catálogo embutido (`db.BUILTIN_FEEDS`)
   nascem **desligados**, e a busca só roda quando o usuário clica em *Buscar
   artigos*. Abrir o aplicativo não gera uma requisição de leitura sequer.
4. **Uma tabela própria, fora do backup.** `articles` se refaz sozinha a partir
   dos feeds; o que viaja no backup é a lista de `feeds`, que é configuração
   escrita pela pessoa.

## Fontes do catálogo embutido

Todas verificadas em 2026-09-23 (HTTP 200, feed válido, itens presentes):

| Feed | URL |
|---|---|
| Hacker News — capa | `https://hnrss.org/frontpage` |
| DEV Community | `https://dev.to/feed` |
| GitHub Blog | `https://github.blog/feed/` |
| Stack Overflow Blog | `https://stackoverflow.blog/feed/` |
| MDN Blog | `https://developer.mozilla.org/en-US/blog/rss.xml` |
| web.dev | `https://web.dev/static/blog/feed.xml` |
| The Go Blog | `https://go.dev/blog/feed.atom` |
| Rust Blog | `https://blog.rust-lang.org/feed.xml` |
| Martin Fowler | `https://martinfowler.com/feed.atom` |
| AWS Architecture Blog | `https://aws.amazon.com/blogs/architecture/feed/` |

O critério de entrada no catálogo: feed público do **próprio autor do texto**
(blog oficial de linguagem, de produto ou de pessoa), ou agregador que publica
apenas título e link. Nada que republique texto alheio.

## Resiliência, deduplicação e desatualização

- **Deduplicação em duas camadas.** Índice único em `(feed, guid)` para o mesmo
  item reaparecendo no próprio feed, e índice único em `url_key` — a URL sem
  esquema, sem `www.`, sem barra final e sem parâmetros de campanha — para o mesmo
  artigo chegando por dois feeds diferentes. Os dois são resolvidos pelo
  `INSERT OR IGNORE`, no banco, e não por comparação em Python.
- **Falha isolada.** Cada feed é buscado numa thread própria; o que falha grava o
  erro em `feeds.last_error`, aparece com a etiqueta de erro na tela e **não
  apaga** os artigos que já havia trazido.
- **Conteúdo desatualizado.** Artigo publicado há mais de `reading_stale_days`
  (padrão: 365 dias) ganha a marca *pode estar desatualizado* na lista. É o único
  sinal barato e honesto que existe para texto técnico: a data.
- **Poda.** `reading.prune()` apaga o que passou de `reading_keep_days` (padrão:
  60) a cada atualização. O que ainda está no ar volta na busca seguinte.

## Consequências

- O app ganha uma tela e ~350 linhas de módulo, sem nenhuma dependência nova.
- Quem não quiser o recurso simplesmente nunca liga um feed, e o custo para essa
  pessoa é zero requisição e zero linha no banco.
