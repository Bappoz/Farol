"""Próximas ações em iCalendar, para o compromisso aparecer no calendário.

Um follow-up anotado dentro de um aplicativo que só abre quando a pessoa lembra
de abrir não lembra ninguém de nada. O `.ics` leva a data para onde o alarme já
existe — celular, agenda do trabalho, o que a pessoa já usa.

O arquivo é gerado a cada pedido: nada é sincronizado nem enviado para lugar
nenhum. Quem quiser assinatura viva aponta o calendário para a URL local.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta
from typing import Any

from . import db

PRODID = "-//Farol//Central de carreira local//PT-BR"
LINE_LIMIT = 75  # octetos, conforme a RFC 5545


def _escape(text: str) -> str:
    """Escapa o texto de um campo, na ordem que a RFC exige (barra primeiro)."""
    return (str(text or "")
            .replace("\\", "\\\\")
            .replace(";", "\\;")
            .replace(",", "\\,")
            .replace("\r\n", "\\n")
            .replace("\n", "\\n"))


def _fold(line: str) -> str:
    """Quebra a linha em 75 octetos, continuando com um espaço — regra da RFC."""
    bruto = line.encode("utf-8")
    if len(bruto) <= LINE_LIMIT:
        return line
    pedacos, atual = [], b""
    for char in line:
        octetos = char.encode("utf-8")
        limite = LINE_LIMIT if not pedacos else LINE_LIMIT - 1
        if len(atual) + len(octetos) > limite:
            pedacos.append(atual)
            atual = b""
        atual += octetos
    pedacos.append(atual)
    return "\r\n ".join(pedaco.decode("utf-8") for pedaco in pedacos)


def _as_date(value: str | None) -> date | None:
    if not value:
        return None
    try:
        return date.fromisoformat(str(value)[:10])
    except ValueError:
        return None


def upcoming(limit: int = 200) -> list[dict[str, Any]]:
    """Candidaturas ativas com próximo passo e data marcada."""
    return [
        dict(row)
        for row in db.query(
            """SELECT id, title, company, url, status, next_action, next_action_at
               FROM applications
               WHERE next_action <> '' AND next_action_at IS NOT NULL
                 AND status <> 'encerrada'
               ORDER BY next_action_at LIMIT ?""",
            (limit,),
        )
    ]


def build(base_url: str = "", agora: datetime | None = None) -> str:
    """Calendário com uma tarefa de dia inteiro por próxima ação."""
    agora = agora or datetime.now()
    carimbo = agora.strftime("%Y%m%dT%H%M%SZ")

    linhas = [
        "BEGIN:VCALENDAR",
        "VERSION:2.0",
        f"PRODID:{PRODID}",
        "CALSCALE:GREGORIAN",
        "METHOD:PUBLISH",
        "X-WR-CALNAME:Farol — próximas ações",
    ]
    for item in upcoming():
        quando = _as_date(item["next_action_at"])
        if quando is None:
            continue
        empresa = item["company"] or "empresa não informada"
        descricao = f"{item['title']} — {empresa}"
        if item["url"]:
            descricao += "\n" + item["url"]
        linhas += [
            "BEGIN:VEVENT",
            f"UID:candidatura-{item['id']}@farol.local",
            f"DTSTAMP:{carimbo}",
            # dia inteiro: DTEND é exclusivo, por isso o dia seguinte
            f"DTSTART;VALUE=DATE:{quando.strftime('%Y%m%d')}",
            f"DTEND;VALUE=DATE:{(quando + timedelta(days=1)).strftime('%Y%m%d')}",
            f"SUMMARY:{_escape(item['next_action'] + ' · ' + empresa)}",
            f"DESCRIPTION:{_escape(descricao)}",
            "BEGIN:VALARM",
            "TRIGGER:-PT9H",  # na véspera às 15h para um evento de dia inteiro
            "ACTION:DISPLAY",
            f"DESCRIPTION:{_escape(item['next_action'])}",
            "END:VALARM",
        ]
        if base_url:
            linhas.append(f"URL:{_escape(base_url.rstrip('/'))}/candidaturas/{item['id']}")
        linhas.append("END:VEVENT")
    linhas.append("END:VCALENDAR")

    return "\r\n".join(_fold(linha) for linha in linhas) + "\r\n"
