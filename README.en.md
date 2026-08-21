<div align="center">
  <img src="assets/farol-128.png" alt="" width="88" height="88">

# Farol

**A local career workspace for tech job seekers.**

Collects remote job postings from public boards, scores each one against your
profile, tracks your applications, builds tailored résumés and works out what to
study next. No account, no cloud, no subscription.

[![CI](https://github.com/Bappoz/farol/actions/workflows/ci.yml/badge.svg)](https://github.com/Bappoz/farol/actions/workflows/ci.yml)
[![MIT License](https://img.shields.io/badge/license-MIT-informational)](LICENSE)
[![Python 3.10+](https://img.shields.io/badge/python-3.10%2B-blue)](https://www.python.org/downloads/)
[![Linux, macOS and Windows](https://img.shields.io/badge/platforms-Linux%20%C2%B7%20macOS%20%C2%B7%20Windows-lightgrey)](#installation)

[Português](README.md) · **English**

</div>

> **The application interface is in Brazilian Portuguese.** This page exists so
> that English readers can evaluate, install and contribute to the project. The
> full documentation — every screen, every design decision and every trade-off —
> is in [README.md](README.md).

---

## What it is

Farol is a desktop application that runs entirely on your own machine. The
server listens on `127.0.0.1` only, data lives in a single SQLite file under
your user directory, and nothing leaves the machine — except read-only requests
to the job boards and, when you explicitly enable it, calls to the optional AI
assistant.

| Screen | Purpose |
|--------|---------|
| **Painel** (Dashboard) | Application funnel, weekly goal, overdue next actions and the highest-scoring postings right now. |
| **Vagas** (Jobs) | Postings from six boards plus any RSS feeds you add, with a 0–100 fit score explained item by item and combinable filters. |
| **Pipeline** | Kanban of applications by stage, with history and next step. Cards move by drag or by a stage selector that works on keyboard and touch. |
| **Currículos** (Résumés) | A base résumé and versions tailored to a posting, in Portuguese or English, in four presentation templates, with a pre-send checklist, cover letter and PDF output. Also stores PDFs you already have. |
| **Roadmap** | Skill gaps computed over the postings *your own* searches brought in, with recommended projects and certifications. |
| **Perfil** (Profile) | Single source of truth: feeds the scoring, the résumés and the roadmap. |
| **Ajustes** (Settings) | Search terms, sources with error diagnostics, region preferences, desktop notifications and the optional API key. |

### The fit score is not a black box

Each posting scores 0–100 as the sum of five components, and the screen shows
the arithmetic:

| Component | Range | Criterion |
|-----------|-------|-----------|
| Skills | 0–55 | How much of what the posting asks for you already have. |
| Seniority | 0–20 | Entry-level postings score; senior ones lose points. |
| Region | 0–10 | Accepts candidates in Brazil or Latin America. |
| Recency | 0–10 | A posting from today beats one from three weeks ago. |
| Preferences | 0–5 | Your keywords; an excluded term in the title sinks the posting. |

The computation is deterministic and local. No statistical model, no network
call: the same posting with the same profile always yields the same number, and
that number is auditable in the interface itself.

---

## Installation

Requires **Python 3.10 or newer**.

### Linux and macOS

```bash
git clone https://github.com/Bappoz/farol.git
cd farol
./install.sh
```

Creates an isolated Python environment, installs the application, prepares the
database and registers the system shortcut — a `.desktop` entry on Linux, a
`Farol.app` bundle in `~/Applications` on macOS. The `farol` command becomes
available in the terminal.

### Windows

```powershell
git clone https://github.com/Bappoz/farol.git
cd farol
powershell -ExecutionPolicy Bypass -File .\install.ps1
```

Creates the environment, installs the application, adds a Start Menu shortcut
and registers `farol` on the user `PATH`. Pass `-ComAreaDeTrabalho` for a
desktop shortcut as well.

### Standalone executable

[Releases](https://github.com/Bappoz/farol/releases) carry one executable per
platform with the Python interpreter embedded. Download, extract, run.

These files are not code-signed. On macOS, clear the quarantine flag with
`xattr -d com.apple.quarantine farol` before first use; on Windows, SmartScreen
asks for confirmation under *More info → Run anyway*.

### pip or pipx

```bash
pipx install farol-carreira
farol
```

Installs the command only, without a system menu entry.

### Docker

```bash
docker compose up -d          # http://127.0.0.1:7788
```

`compose.yaml` binds the port to `127.0.0.1` deliberately. Farol has no
authentication and the database holds personal data: to reach it from another
machine, put an authenticating reverse proxy in front rather than exposing the
port. See [SECURITY.md](SECURITY.md).

### Uninstalling

```bash
./uninstall.sh                                              # Linux and macOS
powershell -ExecutionPolicy Bypass -File .\uninstall.ps1    # Windows
```

Your data is **not** deleted. Add `--com-dados` (`-ComDados` on Windows) to
remove it as well; confirmation is required.

---

## Command line

```
farol                 open the application (starts the server, opens the window)
farol servir          server only, in the foreground
farol atualizar       collect job postings and exit
farol caminho         print where the database and files live
farol versao          print the installed version
```

Options: `--port`, `--host`, `--reload` and `--sem-navegador` (skip opening the
browser). Run `farol --help` for the full description.

---

## Data location

| Platform | Directory |
|----------|-----------|
| Linux | `$XDG_DATA_HOME/farol` (default `~/.local/share/farol`) |
| macOS | `~/Library/Application Support/Farol` |
| Windows | `%LOCALAPPDATA%\Farol` |

`FAROL_HOME` overrides the choice. The directory holds `farol.db`, an uploaded
résumés folder and `server.log`. It sits **outside** the project folder on
purpose: to upgrade, extract the new version over the old one — new columns are
applied on the next start, without deleting anything.

---

## Job sources and collection policy

Six built-in sources, all public APIs or feeds requiring no key: **Remotive**,
**RemoteOK**, **Arbeitnow**, **Himalayas**, **We Work Remotely** and **Vagas BR**
— the job boards the Brazilian developer community keeps as GitHub issues, and
the only built-in source in Portuguese. Any RSS or Atom feed can be added from
the settings screen.

Farol queries third-party servers and constrains itself accordingly:

- **Honest identification.** The `User-Agent` states the name, version and
  project URL. The application does not pose as a browser.
- **One collection per launch**, and only one.
- **Cool-down window.** A configurable minimum interval between automatic
  collections, 45 minutes by default. Reopening the application five times in
  ten minutes produces no extra requests.
- **Delay between requests.** Consecutive requests to the *same* board are
  spaced 1.5 s apart. Different boards run in parallel, being different servers.

Usage is personal. Respect each board's terms of service.

---

## Development

```bash
./install.sh --sem-atalho              # environment and editable install
.venv/bin/python -m farol servir --reload
.venv/bin/python -m pytest             # 132 tests, no network access
.venv/bin/ruff check farol tests
```

With [`just`](https://github.com/casey/just): `just setup`, `just dev`,
`just check`, `just binary`, `just docker`. The `justfile` is the canonical
reference for project commands.

The test suite never touches the network: collectors run against recorded HTTP
responses in `tests/fixtures/`.

Contributions are welcome — see [CONTRIBUTING.md](CONTRIBUTING.md). Code,
commits and identifiers are in English; the interface, documentation and
comments are in Portuguese.

---

## Architecture

FastAPI and Jinja rendering everything server-side, SQLite without an ORM, a
single CSS file and roughly 200 lines of JavaScript. No build step, no `npm`, no
front-end framework.

```
farol/
  app.py          routes and rendering
  db.py           SQLite access, schema and column migrations
  collect.py      ingestion: fetch, deduplicate, store and score
  scoring.py      explainable fit score, work mode, region and salary range
  skills.py       skill taxonomy and text extraction
  markup.py       job description to readable HTML (escapes before marking up)
  resume.py       résumé assembly, cover letter and checklist
  pdfs.py         uploaded PDFs: store, serve and extract text
  roadmap.py      gaps, projects and certifications
  launcher.py     application startup on Linux, macOS and Windows
  sources/        one module per board, a generic RSS reader and term matching
```

---

## License

[MIT](LICENSE). Change history in [CHANGELOG.md](CHANGELOG.md).
