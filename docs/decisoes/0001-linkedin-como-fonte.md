# 1. LinkedIn não entra como fonte de vagas

- **Estado:** decidido
- **Data:** 2026-09-23
- **Issue:** [#10 — Investigar LinkedIn como fonte de vagas](https://github.com/Bappoz/farol/issues/10)

## Contexto

O LinkedIn tem a maior cobertura de vagas do mercado, e a pergunta do issue era
se dava para usá-lo sem cair em scraping frágil ou em violação de termos. A
investigação precisava vir antes de qualquer linha de código de adaptador.

## Evidências levantadas

Tudo verificado em 2026-09-23, com requisições diretas e a documentação oficial.

**1. O `robots.txt` proíbe o acesso automatizado, explicitamente.**
`https://www.linkedin.com/robots.txt` abre com um aviso dizendo que usar robôs ou
outros meios automatizados para acessar o LinkedIn sem permissão expressa é
estritamente proibido, e aponta para os termos de crawling e para um e-mail de
liberação (`whitelist-crawl@linkedin.com`). O arquivo libera caminhos para
`LinkedInBot` e para buscadores nomeados, e termina com a regra que vale para
todo o resto:

```
User-agent: *
Disallow: /
```

Não é uma proibição parcial de alguns caminhos: é o site inteiro, para qualquer
agente não listado. O Farol seria um agente não listado.

**2. A API oficial não tem porta de entrada para isto.**
A página *Getting Access to LinkedIn APIs* lista as únicas permissões
autosserviço, disponíveis a qualquer desenvolvedor: `profile` e `email` (Sign in
with LinkedIn using OpenID Connect) e `w_member_social` (Share on LinkedIn).
Nenhuma delas lê anúncio de vaga. Tudo o que vai além — inclusive as APIs de
Talent Solutions, onde vivem as vagas — depende de aprovação explícita do
LinkedIn dentro de um programa de parceria. Um aplicativo de mesa de uso pessoal
não é candidato a esses programas.

**3. Não há feed público.**
Não existe RSS/Atom oficial de busca de vagas. O que circula são serviços de
terceiros que raspam o site e revendem o resultado — ou seja, o mesmo problema,
com um intermediário e um custo a mais no caminho.

**4. Do lado técnico, a raspagem também seria ruim.**
A busca de vagas sem sessão devolve HTML montado no cliente e leva a *authwall*
depois de poucas requisições do mesmo IP. Uma fonte assim entra no app como
"funciona hoje, quebra no mês que vem", e o usuário só descobre quando a lista
de vagas silenciosamente encolhe.

## Decisão

**Não implementar o LinkedIn como fonte de vagas** — nem por raspagem, nem por
serviço de terceiros que raspe por nós. A decisão não é só de risco jurídico: é
que uma fonte proibida e instável entrega ao usuário uma promessa que o app não
consegue manter.

O critério fica registrado para as próximas fontes: **o Farol só coleta de
portal cujo `robots.txt` permita, ou que ofereça API/feed público para este uso.**
As seis fontes embutidas hoje atendem a esse critério.

## O que fica no lugar

Cobertura equivalente vem de fontes abertas. As URLs abaixo responderam 200 com
conteúdo em 2026-09-23 e podem ser cadastradas em **Ajustes → Fontes → Adicionar
feed**:

| Feed | URL | O que cobre |
|------|-----|-------------|
| Jobicy | `https://jobicy.com/?feed=job_feed` | vagas remotas, boa parte em tecnologia |
| HN — Who is hiring | `https://hnrss.org/whoishiring/jobs` | mural mensal do Hacker News, onde muita empresa publica antes do LinkedIn |
| HN — YC jobs | `https://hnrss.org/jobs` | vagas de empresas do Y Combinator |
| Python.org Jobs | `https://www.python.org/jobs/feed/rss/` | vagas de Python, inclusive fora dos portais remotos |
| We Work Remotely — programação | `https://weworkremotely.com/categories/remote-programming-jobs.rss` | categoria completa (a fonte embutida usa um recorte menor) |

Para o mercado brasileiro, a fonte embutida **Vagas BR** já lê os murais que a
comunidade mantém como issues do GitHub (`backend-br/vagas` e outros cinco), que
é onde boa parte das vagas nacionais circula sem passar pelo LinkedIn.

## Consequências

- O usuário continua candidatando-se pelo LinkedIn quando o anúncio estiver lá;
  o que o app não faz é **coletar** de lá. Nada impede colar a URL da vaga numa
  candidatura manual no Pipeline.
- Se algum dia o LinkedIn publicar um feed ou abrir uma API de leitura para uso
  pessoal, esta decisão é revisitada — um adaptador novo custa um arquivo em
  `farol/sources/` e uma linha em `db.BUILTIN_SOURCES`.
