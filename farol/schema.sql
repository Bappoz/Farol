PRAGMA journal_mode = WAL;
PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS profile (
    id          INTEGER PRIMARY KEY CHECK (id = 1),
    name        TEXT NOT NULL DEFAULT '',
    headline    TEXT NOT NULL DEFAULT '',
    email       TEXT NOT NULL DEFAULT '',
    phone       TEXT NOT NULL DEFAULT '',
    city        TEXT NOT NULL DEFAULT '',
    area        TEXT NOT NULL DEFAULT 'backend',
    seniority   TEXT NOT NULL DEFAULT 'junior',
    summary     TEXT NOT NULL DEFAULT '',
    links       TEXT NOT NULL DEFAULT '[]',   -- [{label, url}]
    skills      TEXT NOT NULL DEFAULT '[]',   -- ["python", "sql", ...] (canônicas)
    languages   TEXT NOT NULL DEFAULT '[]',   -- [{name, level}]
    education   TEXT NOT NULL DEFAULT '[]',   -- [{school, course, period, note}]
    experience  TEXT NOT NULL DEFAULT '[]',   -- [{role, org, period, bullets[]}]
    projects    TEXT NOT NULL DEFAULT '[]',   -- [{name, url, stack, bullets[]}]
    updated_at  TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS settings (
    key   TEXT PRIMARY KEY,
    value TEXT NOT NULL
);

-- Fontes de vagas: as embutidas são semeadas em db.bootstrap(); kind='rss' permite adicionar as suas.
CREATE TABLE IF NOT EXISTS sources (
    id           TEXT PRIMARY KEY,
    label        TEXT NOT NULL,
    kind         TEXT NOT NULL,               -- builtin | rss
    url          TEXT NOT NULL DEFAULT '',
    enabled      INTEGER NOT NULL DEFAULT 1,
    last_run_at  TEXT,
    last_status  TEXT,                        -- ok | erro
    last_count   INTEGER NOT NULL DEFAULT 0,
    last_error   TEXT NOT NULL DEFAULT ''
);

CREATE TABLE IF NOT EXISTS searches (
    id       INTEGER PRIMARY KEY AUTOINCREMENT,
    label    TEXT NOT NULL,
    keywords TEXT NOT NULL DEFAULT '',
    enabled  INTEGER NOT NULL DEFAULT 1
);

CREATE TABLE IF NOT EXISTS jobs (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    source        TEXT NOT NULL,
    source_id     TEXT NOT NULL,
    fingerprint   TEXT NOT NULL,
    title         TEXT NOT NULL,
    company       TEXT NOT NULL DEFAULT '',
    url           TEXT NOT NULL DEFAULT '',
    apply_url     TEXT NOT NULL DEFAULT '',
    location      TEXT NOT NULL DEFAULT '',
    remote          INTEGER NOT NULL DEFAULT 1,
    work_mode       TEXT NOT NULL DEFAULT 'remoto', -- remoto | hibrido | presencial (scoring.work_mode)
    region          TEXT NOT NULL DEFAULT 'outros', -- brasil | latam | mundial | outros (scoring.region)
    salary          TEXT NOT NULL DEFAULT '',
    salary_min      INTEGER,                        -- valor anual, melhor esforço (scoring.salary_range)
    salary_max      INTEGER,
    salary_currency TEXT NOT NULL DEFAULT '',       -- USD | EUR | GBP | BRL | '' quando indefinida
    tags          TEXT NOT NULL DEFAULT '[]',
    skills        TEXT NOT NULL DEFAULT '[]',      -- canônicas, extraídas na ingestão (farol.skills)
    description   TEXT NOT NULL DEFAULT '',
    published_at  TEXT,
    first_seen_at TEXT NOT NULL DEFAULT (datetime('now')),
    last_seen_at  TEXT NOT NULL DEFAULT (datetime('now')),
    score         INTEGER NOT NULL DEFAULT 0,
    score_data    TEXT NOT NULL DEFAULT '{}',
    state         TEXT NOT NULL DEFAULT 'novo' -- novo | descartada
);

CREATE UNIQUE INDEX IF NOT EXISTS jobs_source_key ON jobs (source, source_id);
CREATE INDEX IF NOT EXISTS jobs_fingerprint ON jobs (fingerprint);
CREATE INDEX IF NOT EXISTS jobs_score ON jobs (score DESC);

CREATE TABLE IF NOT EXISTS applications (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    job_id         INTEGER REFERENCES jobs (id) ON DELETE SET NULL,
    title          TEXT NOT NULL,
    company        TEXT NOT NULL DEFAULT '',
    url            TEXT NOT NULL DEFAULT '',
    status         TEXT NOT NULL DEFAULT 'salva',
    position       INTEGER NOT NULL DEFAULT 0,
    applied_at     TEXT,
    next_action    TEXT NOT NULL DEFAULT '',
    next_action_at TEXT,
    contact        TEXT NOT NULL DEFAULT '',
    notes          TEXT NOT NULL DEFAULT '',
    prep           TEXT NOT NULL DEFAULT '',   -- anotações de preparação (STAR, perguntas)
    created_at     TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at     TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS applications_status ON applications (status, position);

CREATE TABLE IF NOT EXISTS events (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    application_id INTEGER NOT NULL REFERENCES applications (id) ON DELETE CASCADE,
    kind           TEXT NOT NULL,
    note           TEXT NOT NULL DEFAULT '',
    created_at     TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS resumes (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    name           TEXT NOT NULL,
    job_id         INTEGER REFERENCES jobs (id) ON DELETE SET NULL,
    application_id INTEGER REFERENCES applications (id) ON DELETE SET NULL,
    lang           TEXT NOT NULL DEFAULT 'pt',   -- pt | en (ver db.MIGRATIONS)
    template       TEXT NOT NULL DEFAULT 'sober',   -- modelo de impressão (resume.TEMPLATES)
    kind           TEXT NOT NULL DEFAULT 'montado', -- montado (editor) | arquivo (PDF seu)
    file           TEXT NOT NULL DEFAULT '',        -- caminho relativo ao diretório de dados
    data           TEXT NOT NULL DEFAULT '{}',
    letter         TEXT NOT NULL DEFAULT '',
    created_at     TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at     TEXT NOT NULL DEFAULT (datetime('now'))
);

-- Itens do roadmap (projetos, certificações e skills marcadas para estudar).
CREATE TABLE IF NOT EXISTS learning (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    kind       TEXT NOT NULL,                 -- projeto | certificacao | skill
    ref        TEXT NOT NULL,                 -- id do catálogo ou nome da skill
    title      TEXT NOT NULL,
    url        TEXT NOT NULL DEFAULT '',
    status     TEXT NOT NULL DEFAULT 'planejado', -- planejado | fazendo | concluido
    notes      TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE UNIQUE INDEX IF NOT EXISTS learning_ref ON learning (kind, ref);
