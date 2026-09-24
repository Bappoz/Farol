"""Política de fontes na tela: por que um portal não entra, e o que fazer então."""

import pytest
from fastapi.testclient import TestClient

from farol import db
from farol.app import app
from farol.sources import policy


@pytest.fixture
def client():
    with TestClient(app) as test_client:
        yield test_client


def test_ajustes_explica_cada_portal_recusado(client):
    corpo = client.get("/ajustes").text

    assert "Portais que não entram" in corpo
    for portal in policy.NOT_COLLECTED:
        assert portal["name"] in corpo
        assert portal["reason"] in corpo
        assert portal["doc"] in corpo


def test_toda_recusa_tem_evidencia_datada():
    """"Não dá" sem evidência é palpite, e palpite não serve como decisão."""
    for portal in policy.NOT_COLLECTED:
        assert portal["evidence"].strip()
        assert portal["checked"].count("-") == 2
        assert portal["doc"].startswith("https://")


def test_a_tela_aponta_o_caminho_manual(client):
    """A ausência da fonte precisa vir com o que fazer no lugar dela."""
    ajustes = client.get("/ajustes").text
    assert "/pipeline" in ajustes
    assert "/roadmap" in ajustes

    for pagina in ("/vagas", "/pipeline"):
        corpo = client.get(pagina).text
        assert "Portais que não entram" in corpo or "não coleta" in corpo


def test_feed_sugerido_entra_em_um_clique(client):
    sugerido = policy.SUGGESTED_FEEDS[0]
    client.post(
        "/ajustes/fontes",
        data={"acao": "adicionar", "label": sugerido["label"], "url": sugerido["url"]},
        follow_redirects=True,
    )
    gravado = db.one("SELECT label, kind FROM sources WHERE url = ?", (sugerido["url"],))
    assert gravado is not None
    assert (gravado["label"], gravado["kind"]) == (sugerido["label"], "rss")


def test_feed_ja_cadastrado_nao_oferece_o_botao_de_novo(client):
    sugerido = policy.SUGGESTED_FEEDS[0]
    antes = client.get("/ajustes").text
    assert antes.count(f'value="{sugerido["url"]}"') == 1

    client.post(
        "/ajustes/fontes",
        data={"acao": "adicionar", "label": sugerido["label"], "url": sugerido["url"]},
        follow_redirects=True,
    )
    depois = client.get("/ajustes").text
    assert f'value="{sugerido["url"]}"' not in depois
    assert "já cadastrado" in depois
