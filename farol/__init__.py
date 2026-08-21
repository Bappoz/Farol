"""Farol — central de carreira local.

Aplicativo de mesa que roda inteiro na máquina do usuário: coleta vagas remotas
nos portais públicos, pontua cada uma contra o perfil, acompanha as candidaturas,
monta currículos direcionados e calcula o que estudar em seguida.
"""

from __future__ import annotations

__all__ = ["USER_AGENT", "__version__"]

__version__ = "1.0.0"

# Identificação honesta nas requisições aos portais. Não imitamos um navegador:
# além de ser a postura correta para um coletor, a proteção antibot de alguns
# portais (Himalayas, por exemplo) devolve 403 para User-Agent de navegador que
# chega sem executar JavaScript, e 200 para um cliente que se identifica.
USER_AGENT = f"Farol/{__version__} (+https://github.com/Bappoz/farol) uso pessoal"
