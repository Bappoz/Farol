# Como contribuir

Contribuições são bem-vindas. Este documento descreve o ambiente de
desenvolvimento, os padrões adotados e o que se espera de um pull request.

## Ambiente

Requer Python 3.10 ou superior. O projeto usa [uv](https://docs.astral.sh/uv/)
quando disponível e o `venv` da biblioteca padrão caso contrário.

```bash
git clone https://github.com/Bappoz/Tunel.git farol
cd farol
./install.sh --sem-atalho      # cria .venv e instala em modo editável
.venv/bin/python -m farol servir --reload
```

No Windows:

```powershell
powershell -ExecutionPolicy Bypass -File .\install.ps1 -SemAtalho
.\.venv\Scripts\python.exe -m farol servir --reload
```

Com [`just`](https://github.com/casey/just) instalado, `just --list` mostra as
receitas equivalentes para todas as tarefas descritas abaixo.

## Verificações obrigatórias

Todo pull request precisa passar, nesta ordem:

```bash
.venv/bin/ruff check farol tests   # lint
.venv/bin/python -m pytest         # testes
```

A formatação não é imposta por ferramenta: `ruff format` está disponível
(`just format`), mas o repositório não é reformatado em massa. Escreva no estilo
do arquivo vizinho — alinhamento de dicionário e SQL em várias linhas são
escolhas deliberadas de legibilidade que o formatador desfaria.

A integração contínua roda o mesmo conjunto em Linux, macOS e Windows, nas
versões 3.10 a 3.13 do Python. Um pull request com verificação vermelha não é
avaliado até ficar verde.

## Padrões de código

- **Idioma.** Identificadores, mensagens de commit e nomes de arquivo em inglês.
  Interface, documentação, comentários e docstrings em português.
- **Comentário explica o porquê**, nunca o quê. Se o código precisa de comentário
  para dizer o que faz, reescreva o código.
- **Sem dependência nova sem justificativa** no corpo do pull request. O projeto
  se sustenta em seis dependências diretas e a intenção é que continue assim.
- **Nada de framework de front-end.** O HTML é renderizado no servidor com Jinja
  e o JavaScript existe apenas onde a alternativa seria pior para o usuário.
- **Tipagem** em toda função pública.

## Testes

A suíte não acessa a rede. Os coletores são exercitados contra respostas HTTP
gravadas em `tests/fixtures/`, servidas por `httpx.MockTransport`. Cada teste
recebe um banco novo em diretório temporário pela fixture `isolated_home`.

Ao corrigir um defeito, escreva primeiro o teste que falha por causa dele.

## Adicionar uma fonte de vagas

Para um portal que publica RSS ou Atom, nada de código é necessário: a URL do
feed pode ser cadastrada em Ajustes.

Para um portal com API própria:

1. Crie `farol/sources/meuportal.py` com `fetch(client, query) -> list[dict]`.
   O dicionário devolvido segue o formato documentado em
   `farol/sources/__init__.py`.
2. Use `farol.sources.query.matches()` para filtrar pelo termo de busca quando a
   API não filtrar sozinha. Ele casa todas as palavras do termo, não a frase.
3. Registre o módulo em `REGISTRY` (`farol/sources/__init__.py`) e em
   `BUILTIN_SOURCES` (`farol/db.py`).
4. Grave uma resposta real em `tests/fixtures/` e escreva o teste correspondente
   em `tests/test_sources.py`.

Respeite os termos de uso do portal. O Farol se identifica honestamente pelo
`User-Agent` e mantém uma pausa entre requisições ao mesmo servidor; nenhuma
contribuição deve remover qualquer um dos dois.

## Alterar o banco de dados

O esquema vive em `farol/schema.sql` e é aplicado com `CREATE TABLE IF NOT
EXISTS`. Bancos já instalados não recebem colunas novas por esse caminho, então
toda coluna acrescentada precisa também de uma entrada em `db.MIGRATIONS`. Se o
valor da coluna deriva do conteúdo da vaga, inclua o nome em
`db.DERIVED_JOB_COLUMNS` para que as linhas existentes sejam recalculadas.

Nenhuma migração pode apagar dados do usuário.

## Pull requests

- Uma mudança por pull request.
- Mensagens no formato [Conventional Commits](https://www.conventionalcommits.org/):
  `feat:`, `fix:`, `docs:`, `refactor:`, `test:`, `chore:`.
- Descreva o comportamento antes e depois. Em mudança de interface, anexe imagem.
- Atualize `README.md` quando a mudança alterar o que o usuário vê, e
  `CHANGELOG.md` na seção *Não publicado*.

## Reportar defeito

Abra uma issue com a versão (`farol versao`), o sistema operacional, os passos
para reproduzir, o resultado esperado e o obtido. Quando houver erro de servidor,
inclua as últimas linhas do log — o caminho aparece em `farol caminho`.
