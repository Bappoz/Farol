"""Currículos que já existem em PDF: guardar o arquivo e ler o texto dele.

A leitura é oportunista — serve para conferir o que o PDF cobre e sugerir skills
ao Perfil, não para reconstruir o documento. PDF que é imagem escaneada não tem
texto para extrair, e o app diz isso em vez de fingir que leu.
"""

from __future__ import annotations

import re
import shutil
import subprocess
from pathlib import Path

from . import db

MAX_BYTES = 15 * 1024 * 1024
MAGIC = b"%PDF-"


def files_dir() -> Path:
    path = db.home() / "curriculos"
    path.mkdir(parents=True, exist_ok=True)
    return path


def slug(text: str) -> str:
    cleaned = re.sub(r"[^a-zA-Z0-9]+", "-", text or "").strip("-").lower()
    return (cleaned or "curriculo")[:60]


def is_pdf(content: bytes) -> bool:
    return content[:5] == MAGIC


def save(resume_id: int, name: str, content: bytes) -> str:
    """Grava o arquivo e devolve o caminho relativo ao diretório de dados.

    Sempre com `/`, mesmo no Windows: o valor vai para o banco, para dentro do
    ZIP de backup e para a URL de download — os três esperam separador POSIX.
    """
    target = files_dir() / f"{resume_id}-{slug(name)}.pdf"
    target.write_bytes(content)
    return target.relative_to(db.home()).as_posix()


def path_for(relative: str) -> Path | None:
    if not relative:
        return None
    candidate = (db.home() / relative).resolve()
    # nunca servir nada fora do diretório de dados
    if not str(candidate).startswith(str(db.home().resolve())):
        return None
    return candidate if candidate.is_file() else None


def remove(relative: str) -> None:
    target = path_for(relative)
    if target:
        target.unlink(missing_ok=True)


def extract_text(relative: str) -> tuple[str, str]:
    """Devolve (texto, aviso). Texto vazio + aviso quando não deu para ler."""
    target = path_for(relative)
    if target is None:
        return "", "arquivo não encontrado"

    try:
        from pypdf import PdfReader  # dependência opcional
    except ImportError:
        return _extract_with_poppler(target)

    try:
        reader = PdfReader(str(target))
        pages = [page.extract_text() or "" for page in reader.pages[:12]]
    except Exception as exc:  # noqa: BLE001 — PDF quebrado não pode derrubar a página
        return "", f"não consegui ler o PDF ({type(exc).__name__})"

    text = _tidy("\n".join(pages))
    if not text:
        return "", "o PDF não tem camada de texto (provavelmente é imagem escaneada)"
    return text, ""


def _extract_with_poppler(target: Path) -> tuple[str, str]:
    if not shutil.which("pdftotext"):
        return "", "instale o pypdf (./install.sh) para o app ler o texto do PDF"
    try:
        result = subprocess.run(
            ["pdftotext", "-layout", str(target), "-"],
            capture_output=True, timeout=20, check=True,
        )
    except (subprocess.SubprocessError, OSError) as exc:
        return "", f"pdftotext falhou ({type(exc).__name__})"
    text = _tidy(result.stdout.decode("utf-8", "replace"))
    return (text, "") if text else ("", "o PDF não tem camada de texto")


def _tidy(raw: str) -> str:
    text = re.sub(r"[ \t\xa0]+", " ", raw)
    text = re.sub(r"\n\s*\n\s*\n+", "\n\n", text)
    return "\n".join(line.strip() for line in text.splitlines()).strip()
