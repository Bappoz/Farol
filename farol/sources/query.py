"""Casamento entre o termo de busca e o anúncio.

Fica em módulo próprio porque os coletores precisam dele e importá-lo de
`farol.sources` criaria ciclo (o pacote importa os coletores).
"""

from __future__ import annotations

import re
from typing import Any

_WORDS = re.compile(r"[^\w+#.]+", re.UNICODE)


def matches(query: str, *texts: Any) -> bool:
    """O anúncio atende ao termo de busca?

    Casa **todas as palavras** do termo, em qualquer posição — não a frase
    inteira. Exigir a frase literal (o comportamento anterior) devolvia lista
    vazia em praticamente toda busca de mais de uma palavra: nenhum anúncio traz
    "junior backend python" nessa ordem, mas muitos trazem as três palavras.
    """
    terms = [word for word in _WORDS.split((query or "").lower()) if word]
    if not terms:
        return True
    haystack = " ".join(str(text or "") for text in texts).lower()
    return all(term in haystack for term in terms)


def first_term(query: str) -> str:
    """Primeira palavra do termo — para API que só aceita uma tag por vez."""
    terms = [word for word in _WORDS.split((query or "").lower()) if word]
    return terms[0] if terms else ""
