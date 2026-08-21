"""Acesso ao SQLite. Sem ORM: o schema é pequeno e as consultas são explícitas."""

from __future__ import annotations

import contextlib
import json
import os
import sqlite3
import sys
import threading
from collections.abc import Iterable
from pathlib import Path
from typing import Any

PKG_DIR = Path(__file__).resolve().parent

STATUSES = ["salva", "candidatado", "triagem", "entrevista", "teste", "oferta", "encerrada"]
STATUS_LABELS = {
    "salva": "Salvas",
    "candidatado": "Candidatado",
    "triagem": "Triagem",
    "entrevista": "Entrevista",
    "teste": "Teste técnico",
    "oferta": "Oferta",
    "encerrada": "Encerradas",
}

BUILTIN_SOURCES = [
    ("remotive", "Remotive", "builtin", ""),
    ("remoteok", "RemoteOK", "builtin", ""),
    ("arbeitnow", "Arbeitnow", "builtin", ""),
    ("himalayas", "Himalayas", "builtin", ""),
    ("weworkremotely", "We Work Remotely", "builtin", ""),
    ("vagasbr", "Vagas BR (GitHub)", "builtin", ""),
]

DEFAULT_SETTINGS = {
    "weekly_goal": "5",
    "min_score": "35",
    # janela de descanso entre coletas automáticas (minutos): abrir o app de novo
    # dentro dela não dispara requisição nenhuma nos portais
    "refresh_cooldown_min": "45",
    "theme": "auto",
    # aviso do desktop quando a coleta traz vaga nova com fit alto (precisa de notify-send)
    "notify_new_jobs": "",
    "notify_min_score": "70",
    "anthropic_api_key": "",
    "anthropic_model": "claude-sonnet-5",
    "exclude_keywords": "senior, sênior, staff, principal, lead, tech lead, head of",
    "region_preference": "brazil",  # brazil | latam | worldwide
}


def _configured_home() -> Path:
    env = os.environ.get("FAROL_HOME")
    if env:
        return Path(env).expanduser()
    if os.name == "nt":
        base = os.environ.get("LOCALAPPDATA") or "~/AppData/Local"
        return Path(base).expanduser() / "Farol"
    if sys.platform == "darwin" and not os.environ.get("XDG_DATA_HOME"):
        return Path("~/Library/Application Support/Farol").expanduser()
    base = os.environ.get("XDG_DATA_HOME", "~/.local/share")
    return Path(base).expanduser() / "farol"


_local = threading.local()


def home() -> Path:
    """Diretório de dados, por convenção de cada sistema.

    Linux/BSD  `$XDG_DATA_HOME/farol` (padrão `~/.local/share/farol`)
    macOS      `~/Library/Application Support/Farol`
    Windows    `%LOCALAPPDATA%\\Farol`

    `FAROL_HOME` sobrescreve tudo — é o que os testes usam. O `mkdir` roda uma vez
    por caminho, não a cada consulta.
    """
    path = _configured_home()
    if getattr(_local, "home_ready", None) != path:
        path.mkdir(parents=True, exist_ok=True)
        _local.home_ready = path
    return path


def db_path() -> Path:
    return home() / "farol.db"


# Ajustes de conexão. WAL deixa leitura e escrita conviverem (a coleta grava numa
# thread enquanto a página lê noutra) e `synchronous=NORMAL` é o par recomendado:
# seguro contra queda do processo, sem fsync a cada transação.
PRAGMAS = (
    "PRAGMA journal_mode = WAL",
    "PRAGMA synchronous = NORMAL",
    "PRAGMA foreign_keys = ON",
    "PRAGMA busy_timeout = 15000",
    "PRAGMA temp_store = MEMORY",
    "PRAGMA cache_size = -16000",  # 16 MB por conexão
)


def connect() -> sqlite3.Connection:
    """Conexão do SQLite reaproveitada por thread.

    Abrir um arquivo e reaplicar os PRAGMAs a cada consulta custava mais que a
    própria consulta em página com dezenas delas. A conexão é guardada por thread
    (o módulo `sqlite3` proíbe compartilhar entre threads) e invalidada quando o
    caminho do banco muda, que é o que acontece entre testes.
    """
    path = db_path()
    conn = getattr(_local, "conn", None)
    if conn is not None:
        if getattr(_local, "conn_path", None) == path:
            return conn
        close()
    conn = sqlite3.connect(path, timeout=15)
    conn.row_factory = sqlite3.Row
    for pragma in PRAGMAS:
        conn.execute(pragma)
    _local.conn = conn
    _local.conn_path = path
    return conn


def close() -> None:
    """Fecha a conexão desta thread. Idempotente."""
    conn = getattr(_local, "conn", None)
    if conn is not None:
        with contextlib.suppress(sqlite3.Error):
            conn.close()
    _local.conn = None
    _local.conn_path = None


# Colunas acrescentadas depois que bancos já existiam. O schema usa
# CREATE TABLE IF NOT EXISTS, então quem já tinha o app instalado não receberia
# a coluna nova — este mapa cuida disso a cada bootstrap, sem apagar nada.
MIGRATIONS: dict[str, dict[str, str]] = {
    "resumes": {
        "lang": "TEXT NOT NULL DEFAULT 'pt'",
        "template": "TEXT NOT NULL DEFAULT 'sober'",
        "kind": "TEXT NOT NULL DEFAULT 'montado'",
        "file": "TEXT NOT NULL DEFAULT ''",
    },
    "jobs": {
        "work_mode": "TEXT NOT NULL DEFAULT 'remoto'",
        "region": "TEXT NOT NULL DEFAULT 'outros'",
        "salary_min": "INTEGER",
        "salary_max": "INTEGER",
        "salary_currency": "TEXT NOT NULL DEFAULT ''",
        # skills extraídas do anúncio, gravadas na ingestão: o roadmap lê esta
        # coluna em vez de reprocessar a descrição de centenas de vagas a cada
        # abertura da tela (ver farol.roadmap.demand)
        "skills": "TEXT NOT NULL DEFAULT '[]'",
    },
}

# Colunas derivadas do conteúdo da vaga: o DEFAULT do ALTER TABLE não serve como
# valor final (marcaria toda vaga já existente como remota, e aí o filtro de
# presencial/híbrido devolveria lista vazia). Quando uma delas nasce, recalculamos
# a partir das linhas que já estão no banco.
DERIVED_JOB_COLUMNS = {
    "work_mode", "region", "salary_min", "salary_max", "salary_currency", "skills",
}


def _migrate(conn: sqlite3.Connection) -> set[str]:
    """Acrescenta colunas que faltam. Devolve os nomes recém-criados como 'tabela.coluna'."""
    added: set[str] = set()
    for table, columns in MIGRATIONS.items():
        existing = {row["name"] for row in conn.execute(f"PRAGMA table_info({table})")}
        if not existing:
            continue  # tabela ainda não existe: o schema.sql acabou de criá-la completa
        for name, ddl in columns.items():
            if name not in existing:
                conn.execute(f"ALTER TABLE {table} ADD COLUMN {name} {ddl}")
                added.add(f"{table}.{name}")
    return added


def _backfill_jobs(conn: sqlite3.Connection) -> int:
    """Recalcula as colunas derivadas das vagas já gravadas. Devolve quantas mudaram."""
    from . import scoring, skills  # local: evita acoplar db a scoring no import time

    updates = []
    for row in conn.execute("SELECT * FROM jobs").fetchall():
        job = dict(row)
        low, high, currency = scoring.salary_range(job.get("salary")) or (None, None, "")
        updates.append(
            (scoring.work_mode(job), scoring.region(job), low, high, currency,
             dumps(skills.extract(job_text(job))), job["id"])
        )
    conn.executemany(
        """UPDATE jobs SET work_mode = ?, region = ?, salary_min = ?, salary_max = ?,
                           salary_currency = ?, skills = ? WHERE id = ?""",
        updates,
    )
    return len(updates)


def job_text(job: dict[str, Any]) -> str:
    """Texto único da vaga para extrair skills — título, tags e descrição."""
    tags = job.get("tags") or []
    if isinstance(tags, str):
        tags = loads(tags, [])
    return " ".join(
        [str(job.get("title") or ""), " ".join(str(t) for t in tags), str(job.get("description") or "")]
    )


def bootstrap() -> None:
    """Cria o schema, aplica migrações e semeia dados iniciais. Idempotente."""
    schema = (PKG_DIR / "schema.sql").read_text(encoding="utf-8")
    with connect() as conn:
        conn.executescript(schema)
        added = _migrate(conn)
        if any(f"jobs.{column}" in added for column in DERIVED_JOB_COLUMNS):
            _backfill_jobs(conn)
        conn.execute("INSERT OR IGNORE INTO profile (id) VALUES (1)")
        for key, value in DEFAULT_SETTINGS.items():
            conn.execute("INSERT OR IGNORE INTO settings (key, value) VALUES (?, ?)", (key, value))
        for sid, label, kind, url in BUILTIN_SOURCES:
            conn.execute(
                "INSERT OR IGNORE INTO sources (id, label, kind, url) VALUES (?, ?, ?, ?)",
                (sid, label, kind, url),
            )
        count = conn.execute("SELECT COUNT(*) AS n FROM searches").fetchone()["n"]
        if not count:
            conn.execute(
                "INSERT INTO searches (label, keywords) VALUES (?, ?)",
                ("Primeira busca", "junior developer"),
            )


# ---------------------------------------------------------------- helpers


def query(sql: str, params: Iterable[Any] = ()) -> list[sqlite3.Row]:
    with connect() as conn:
        return conn.execute(sql, tuple(params)).fetchall()


def one(sql: str, params: Iterable[Any] = ()) -> sqlite3.Row | None:
    with connect() as conn:
        return conn.execute(sql, tuple(params)).fetchone()


def execute(sql: str, params: Iterable[Any] = ()) -> int:
    with connect() as conn:
        cur = conn.execute(sql, tuple(params))
        return cur.lastrowid or cur.rowcount


def loads(value: Any, fallback: Any = None) -> Any:
    if not value:
        return fallback if fallback is not None else []
    try:
        return json.loads(value)
    except (TypeError, ValueError):
        return fallback if fallback is not None else []


def dumps(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False)


# ---------------------------------------------------------------- settings


def get_settings() -> dict[str, str]:
    values = dict(DEFAULT_SETTINGS)
    for row in query("SELECT key, value FROM settings"):
        values[row["key"]] = row["value"]
    return values


def set_setting(key: str, value: str) -> None:
    execute(
        "INSERT INTO settings (key, value) VALUES (?, ?) "
        "ON CONFLICT (key) DO UPDATE SET value = excluded.value",
        (key, value),
    )


# ---------------------------------------------------------------- profile


def get_profile() -> dict[str, Any]:
    row = one("SELECT * FROM profile WHERE id = 1")
    if row is None:
        bootstrap()
        row = one("SELECT * FROM profile WHERE id = 1")
    profile = dict(row)  # type: ignore[arg-type]
    for field in ("links", "skills", "languages", "education", "experience", "projects"):
        profile[field] = loads(profile.get(field), [])
    return profile


def save_profile(data: dict[str, Any]) -> None:
    fields = [
        "name", "headline", "email", "phone", "city", "area", "seniority", "summary",
        "links", "skills", "languages", "education", "experience", "projects",
    ]
    payload = []
    for field in fields:
        value = data.get(field, "")
        payload.append(dumps(value) if isinstance(value, (list, dict)) else value)
    assignments = ", ".join(f"{f} = ?" for f in fields)
    execute(
        f"UPDATE profile SET {assignments}, updated_at = datetime('now') WHERE id = 1",
        payload,
    )
