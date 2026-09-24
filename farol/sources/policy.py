"""Política de fontes: o que o Farol coleta, o que não coleta e por quê.

Só dados — nenhum import do pacote, para poder ser lido de qualquer lugar sem
criar ciclo. A tela de Ajustes renderiza isto, e as decisões completas estão em
`docs/decisoes/`.

Por que isso existe no aplicativo, e não só no README: a ausência de um portal
grande parece defeito. Quem procura o LinkedIn na lista de fontes e não acha
conclui que o app está quebrado ou incompleto, e essa conclusão é pior do que a
ausência. Dizer o motivo na tela, com o caminho manual ao lado, transforma um
buraco silencioso em uma decisão que a pessoa pode conferir e contornar.
"""

from __future__ import annotations

from typing import Any

# A regra que decide se um portal entra. Vale para toda fonte futura.
CRITERION = (
    "O Farol só coleta de portal cujo robots.txt permita, ou que ofereça API ou "
    "feed público para este uso. Portal que só funcionaria por raspagem de HTML "
    "fica de fora — é proibido em uns, instável em todos, e uma fonte que quebra "
    "em silêncio é pior que uma fonte que não existe."
)

DECISIONS_URL = "https://github.com/Bappoz/farol/tree/main/docs/decisoes"

# Portais avaliados e recusados. `evidence` é o que foi verificado, com data:
# "não dá" sem evidência é palpite, e palpite não serve como decisão registrada.
NOT_COLLECTED: list[dict[str, Any]] = [
    {
        "name": "LinkedIn",
        "reason": "acesso automatizado proibido e sem API de leitura de vagas",
        "evidence": (
            "O robots.txt termina em “User-agent: * / Disallow: /” e o cabeçalho do "
            "arquivo proíbe robôs sem permissão expressa. Na API oficial, as únicas "
            "permissões autosserviço são entrar com o LinkedIn e publicar — nenhuma lê "
            "anúncio de vaga; o resto depende de aprovação em programa de parceria."
        ),
        "checked": "2026-09-23",
        "doc": f"{DECISIONS_URL}/0001-linkedin-como-fonte.md",
        "issue": "https://github.com/Bappoz/farol/issues/10",
    },
]

# Feeds abertos que cobrem parte do que o portal recusado traria. Todos foram
# verificados na data indicada; o botão ao lado cadastra o feed em um clique.
SUGGESTED_FEEDS: list[dict[str, str]] = [
    {
        "label": "Jobicy",
        "url": "https://jobicy.com/?feed=job_feed",
        "note": "vagas remotas, boa parte em tecnologia",
    },
    {
        "label": "Hacker News — Who is hiring",
        "url": "https://hnrss.org/whoishiring/jobs",
        "note": "mural mensal onde muita empresa publica antes do LinkedIn",
    },
    {
        "label": "Hacker News — vagas YC",
        "url": "https://hnrss.org/jobs",
        "note": "empresas do Y Combinator",
    },
    {
        "label": "Python.org Jobs",
        "url": "https://www.python.org/jobs/feed/rss/",
        "note": "vagas de Python fora dos portais remotos",
    },
    {
        "label": "We Work Remotely — programação",
        "url": "https://weworkremotely.com/categories/remote-programming-jobs.rss",
        "note": "a categoria inteira; a fonte embutida usa um recorte menor",
    },
]

FEEDS_CHECKED = "2026-09-23"
