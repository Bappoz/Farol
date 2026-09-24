"""Agregador de leituras: ingestão, deduplicação, resiliência e poda (issue #9)."""

import httpx
import pytest
from fastapi.testclient import TestClient

from farol import db, reading, sources
from farol.app import app


@pytest.fixture
def client():
    with TestClient(app) as test_client:
        yield test_client


def _rss(*itens: str) -> bytes:
    corpo = "".join(itens)
    return f"""<?xml version="1.0"?>
<rss version="2.0"><channel><title>Feed</title>{corpo}</channel></rss>""".encode()


def _item(titulo, link, descricao="", data="Mon, 01 Sep 2026 10:00:00 +0000") -> str:
    return (f"<item><title>{titulo}</title><link>{link}</link>"
            f"<description>{descricao}</description><pubDate>{data}</pubDate></item>")


@pytest.fixture
def feed_simulado(monkeypatch):
    """Faz qualquer feed responder com o XML que o teste montar, sem tocar a rede."""
    respostas: dict[str, bytes | Exception] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        resposta = respostas.get(str(request.url))
        if isinstance(resposta, Exception):
            raise resposta
        if resposta is None:
            return httpx.Response(404)
        return httpx.Response(200, content=resposta)

    monkeypatch.setattr(
        sources, "client", lambda timeout=25.0: httpx.Client(transport=httpx.MockTransport(handler))
    )
    return respostas


def _ligar(url: str, label: str = "Feed") -> str:
    return reading.add_feed(label, url)


def test_catalogo_embutido_nasce_desligado():
    ligados = [f for f in reading.feeds() if f["enabled"]]
    assert reading.feeds(), "o catálogo embutido deveria estar semeado"
    assert ligados == [], "feed ligado sem o usuário pedir é tráfego não autorizado"


def test_ingestao_guarda_titulo_link_data_e_skills(feed_simulado):
    feed_simulado["https://ex.com/feed"] = _rss(
        _item("Como testar FastAPI com pytest", "https://ex.com/a", "Guia de testes em Python.")
    )
    _ligar("https://ex.com/feed")

    relatorio = reading.refresh()
    assert relatorio["new"] == 1

    artigo = reading.listing()[0]
    assert artigo["title"] == "Como testar FastAPI com pytest"
    assert artigo["url"] == "https://ex.com/a"
    assert artigo["published_at"].startswith("2026-09-01")
    assert set(artigo["skills"]) >= {"fastapi", "python", "pytest"}


def test_resumo_e_cortado_e_nunca_vira_copia_do_artigo(feed_simulado):
    longo = "palavra " * 400
    feed_simulado["https://ex.com/feed"] = _rss(_item("Texto longo", "https://ex.com/a", longo))
    _ligar("https://ex.com/feed")
    reading.refresh()

    resumo = reading.listing()[0]["summary"]
    assert len(resumo) <= reading.SUMMARY_MAX + 1  # o corte acrescenta a reticência
    assert resumo.endswith("…")


def test_item_repetido_no_mesmo_feed_nao_duplica(feed_simulado):
    feed_simulado["https://ex.com/feed"] = _rss(_item("Artigo", "https://ex.com/a"))
    _ligar("https://ex.com/feed")

    assert reading.refresh()["new"] == 1
    assert reading.refresh()["new"] == 0
    assert reading.counts()["total"] == 1


def test_mesmo_artigo_em_dois_feeds_entra_uma_vez_so(feed_simulado):
    """A URL normalizada é a chave: agregador e blog publicam o mesmo link."""
    feed_simulado["https://a.com/feed"] = _rss(
        _item("Artigo", "https://blog.exemplo.com/post?utm_source=agregador")
    )
    feed_simulado["https://b.com/feed"] = _rss(
        _item("Artigo", "https://www.blog.exemplo.com/post/")
    )
    _ligar("https://a.com/feed", "A")
    _ligar("https://b.com/feed", "B")

    reading.refresh()
    assert reading.counts()["total"] == 1


def test_url_key_normaliza_campanha_www_e_barra():
    assert reading.url_key("https://www.x.com/post/") == reading.url_key("http://x.com/post")
    assert reading.url_key("https://x.com/p?utm_campaign=a") == reading.url_key("https://x.com/p")
    assert reading.url_key("https://x.com/p#secao") == reading.url_key("https://x.com/p")


def test_feed_que_falha_nao_derruba_os_outros_nem_apaga_o_que_trouxe(feed_simulado):
    feed_simulado["https://bom.com/feed"] = _rss(_item("Vivo", "https://bom.com/a"))
    feed_simulado["https://ruim.com/feed"] = _rss(_item("Antigo", "https://ruim.com/a"))
    _ligar("https://bom.com/feed", "Bom")
    ruim = _ligar("https://ruim.com/feed", "Ruim")
    reading.refresh()
    assert reading.counts()["total"] == 2

    feed_simulado["https://ruim.com/feed"] = httpx.ConnectError("sem rede")
    relatorio = reading.refresh()

    estados = {f["id"]: f["status"] for f in relatorio["feeds"]}
    assert estados[ruim] == "erro"
    assert any(f["status"] == "ok" for f in relatorio["feeds"])
    assert reading.counts()["total"] == 2  # nada foi apagado
    assert "ConnectError" in db.one("SELECT last_error FROM feeds WHERE id = ?", (ruim,))["last_error"]


def test_xml_quebrado_vira_diagnostico_e_nao_excecao(feed_simulado, monkeypatch):
    def handler(request):
        return httpx.Response(200, content=b"<rss><channel><item>")

    monkeypatch.setattr(
        sources, "client", lambda timeout=25.0: httpx.Client(transport=httpx.MockTransport(handler))
    )
    _ligar("https://quebrado.com/feed")
    relatorio = reading.refresh()

    assert relatorio["feeds"][0]["status"] == "erro"
    assert relatorio["feeds"][0]["error"]


def test_poda_descarta_artigo_fora_da_janela(feed_simulado):
    feed_simulado["https://ex.com/feed"] = _rss(
        _item("Velho", "https://ex.com/velho", data="Mon, 01 Jan 2024 10:00:00 +0000"),
        _item("Novo", "https://ex.com/novo", data="Mon, 01 Sep 2026 10:00:00 +0000"),
    )
    _ligar("https://ex.com/feed")
    db.set_setting("reading_keep_days", "60")

    relatorio = reading.refresh()
    assert relatorio["removed"] == 1
    assert [a["title"] for a in reading.listing(unread_only=False)] == ["Novo"]


def test_artigo_antigo_e_marcado_como_possivelmente_desatualizado(feed_simulado):
    feed_simulado["https://ex.com/feed"] = _rss(
        _item("Velho", "https://ex.com/velho", data="Mon, 01 Jan 2024 10:00:00 +0000")
    )
    _ligar("https://ex.com/feed")
    db.set_setting("reading_keep_days", "3650")
    db.set_setting("reading_stale_days", "365")
    reading.refresh()

    assert reading.listing()[0]["stale"] is True


def test_remover_feed_leva_os_artigos_dele(feed_simulado):
    feed_simulado["https://ex.com/feed"] = _rss(_item("Artigo", "https://ex.com/a"))
    feed_id = _ligar("https://ex.com/feed")
    reading.refresh()
    assert reading.counts()["total"] == 1

    reading.remove_feed(feed_id)
    assert reading.counts()["total"] == 0


def test_filtro_por_skill_nao_casa_substring(feed_simulado):
    """"java" dentro de "javascript" derrubaria o filtro se a busca fosse ingênua."""
    feed_simulado["https://ex.com/feed"] = _rss(
        _item("Async em JavaScript", "https://ex.com/js", "Promises e await no navegador."),
        _item("Records em Java", "https://ex.com/java", "Novidades da linguagem Java."),
    )
    _ligar("https://ex.com/feed")
    reading.refresh()

    assert [a["title"] for a in reading.listing(skill="java")] == ["Records em Java"]
    assert [a["title"] for a in reading.listing(skill="javascript")] == ["Async em JavaScript"]


def test_filtro_do_meu_perfil_usa_as_skills_do_perfil(feed_simulado, perfil_rust):
    feed_simulado["https://ex.com/feed"] = _rss(
        _item("Ownership em Rust", "https://ex.com/rs", "Memória sem coletor."),
        _item("Planilhas no trabalho", "https://ex.com/xls", "Dicas de produtividade."),
    )
    _ligar("https://ex.com/feed")
    reading.refresh()

    titulos = [a["title"] for a in reading.listing(mine_only=True)]
    assert titulos == ["Ownership em Rust"]


@pytest.fixture
def perfil_rust():
    perfil = db.get_profile()
    perfil["skills"] = ["rust"]
    db.save_profile(perfil)
    return perfil


def test_marcar_como_lido_e_desfazer(feed_simulado):
    feed_simulado["https://ex.com/feed"] = _rss(_item("Artigo", "https://ex.com/a"))
    _ligar("https://ex.com/feed")
    reading.refresh()
    artigo = reading.listing()[0]

    reading.mark_read(artigo["id"])
    assert reading.counts()["unread"] == 0
    assert reading.listing(unread_only=True) == []

    reading.mark_read(artigo["id"], read=False)
    assert reading.counts()["unread"] == 1


# ------------------------------------------------------------------ rotas


def test_tela_abre_sem_feed_ligado(client):
    resposta = client.get("/leituras")
    assert resposta.status_code == 200
    assert "Ligue ao menos um feed" in resposta.text


def test_pedir_atualizacao_sem_feed_ligado_avisa(client):
    resposta = client.post("/leituras/atualizar", follow_redirects=True)
    assert "Nenhum feed ligado" in resposta.text


def test_ligar_remover_e_adicionar_feed_pela_tela(client):
    embutido = reading.feeds()[0]["id"]
    client.post("/leituras/feeds", data={"acao": "toggle", "id": embutido}, follow_redirects=True)
    assert [f["id"] for f in reading.feeds(only_enabled=True)] == [embutido]

    client.post("/leituras/feeds",
                data={"acao": "adicionar", "label": "Meu", "url": "https://meu.com/feed"},
                follow_redirects=True)
    assert any(f["url"] == "https://meu.com/feed" for f in reading.feeds())

    resposta = client.post("/leituras/feeds", data={"acao": "adicionar", "label": "X", "url": " "},
                           follow_redirects=True)
    assert "Informe a URL" in resposta.text


def test_marcar_tudo_como_lido_pela_tela(client, feed_simulado):
    feed_simulado["https://ex.com/feed"] = _rss(
        _item("A", "https://ex.com/a"), _item("B", "https://ex.com/b")
    )
    _ligar("https://ex.com/feed")
    reading.refresh()

    resposta = client.post("/leituras/lidos", follow_redirects=True)
    assert "2 artigo(s)" in resposta.text
    assert reading.counts()["unread"] == 0
