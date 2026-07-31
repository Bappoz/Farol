"""Descrição de vaga → HTML legível.

O texto guardado no banco é quase-markdown: `sources.to_text` marca título de
seção com `## ` e item de lista com `- `. Aqui isso vira HTML de verdade, com
duas regras que não abrem exceção:

1. **escapar antes de marcar.** O texto vem de portal de terceiro; qualquer HTML
   dele é conteúdo, nunca marcação. Só as tags criadas aqui são reais.
2. **não inventar estrutura.** Linha que não casa com nenhum padrão vira
   parágrafo. Melhor um parágrafo simples que uma lista falsa.

Funciona também com as descrições já gravadas antes desses marcadores existirem:
elas caem no caminho de parágrafo e continuam legíveis.
"""

from __future__ import annotations

import html
import re

# "Requisitos:" / "What you'll do:" — linha curta que termina em dois-pontos age
# como subtítulo em quase todo anúncio
_LABEL = re.compile(r"^[^\s].{0,78}:$")
_BULLET = re.compile(r"^\s*[-•*•]\s+(.*)$")
_NUMBERED = re.compile(r"^\s*\d{1,2}[.)]\s+(.*)$")
_HEADING = re.compile(r"^#{1,6}\s+(.*)$")
_URL = re.compile(r"https?://[^\s<>()\[\]]+")


def _linkify(text: str) -> str:
    """Transforma URL em link. Recebe texto **já escapado**."""
    return _URL.sub(
        lambda m: f'<a href="{m.group(0)}" target="_blank" rel="noreferrer">{m.group(0)}</a>',
        text,
    )


def render(text: str | None) -> str:
    """Devolve o HTML da descrição. String vazia quando não há texto."""
    if not text or not str(text).strip():
        return ""

    out: list[str] = []
    paragraph: list[str] = []
    list_kind: str | None = None  # 'ul' | 'ol' | None

    def close_paragraph() -> None:
        if paragraph:
            out.append(f"<p>{_linkify(' '.join(paragraph))}</p>")
            paragraph.clear()

    def close_list() -> None:
        nonlocal list_kind
        if list_kind:
            out.append(f"</{list_kind}>")
            list_kind = None

    def open_list(kind: str) -> None:
        nonlocal list_kind
        if list_kind != kind:
            close_list()
            out.append(f"<{kind}>")
            list_kind = kind

    for raw_line in html.escape(str(text)).splitlines():
        line = raw_line.strip()
        if not line:
            # linha vazia fecha parágrafo mas não a lista: portal que escreve um
            # <li> por bloco gera "- a\n\n- b", e isso é uma lista só
            close_paragraph()
            continue

        if heading := _HEADING.match(line):
            close_paragraph()
            close_list()
            out.append(f"<h4>{_linkify(heading.group(1).strip())}</h4>")
            continue

        if bullet := _BULLET.match(line):
            close_paragraph()
            open_list("ul")
            out.append(f"<li>{_linkify(bullet.group(1).strip())}</li>")
            continue

        if numbered := _NUMBERED.match(line):
            close_paragraph()
            open_list("ol")
            out.append(f"<li>{_linkify(numbered.group(1).strip())}</li>")
            continue

        # dois-pontos no fim: subtítulo do anúncio, não continuação do parágrafo
        if _LABEL.match(line):
            close_paragraph()
            close_list()
            out.append(f"<h4>{_linkify(line[:-1].strip())}</h4>")
            continue

        close_list()
        paragraph.append(line)

    close_paragraph()
    close_list()
    return "".join(out)
