"""Coletores rodam contra respostas gravadas — sem rede, sem surpresa."""

import httpx
import pytest

from farol import sources
from farol.sources import (
    arbeitnow,
    himalayas,
    remoteok,
    remotive,
    rss,
    vagasbr,
    weworkremotely,
)


def client_for(fixtures, mapping):
    def handler(request: httpx.Request) -> httpx.Response:
        for fragment, (filename, content_type) in mapping.items():
            if fragment in str(request.url):
                body = (fixtures / filename).read_bytes()
                return httpx.Response(200, content=body, headers={"content-type": content_type})
        return httpx.Response(404)

    return httpx.Client(transport=httpx.MockTransport(handler))


def test_remotive(fixtures):
    with client_for(fixtures, {"remotive.com": ("remotive.json", "application/json")}) as http:
        items = remotive.fetch(http, "python")
    assert len(items) == 2
    first = sources.normalize("remotive", items[0])
    assert first["title"] == "Junior Python Developer"
    assert first["company"] == "Northwind Labs"
    assert first["source_id"] == "1900001"
    assert "pytest" in first["description"]
    assert "<p>" not in first["description"]  # html virou texto
    assert first["published_at"].startswith("2026-07-29")


def test_remoteok_ignora_aviso_legal(fixtures):
    with client_for(fixtures, {"remoteok.com": ("remoteok.json", "application/json")}) as http:
        items = remoteok.fetch(http, "")
    assert len(items) == 1
    assert items[0]["title"] == "Junior Frontend Engineer"
    assert "US$" in items[0]["salary"]


def test_arbeitnow_filtra_pelo_termo(fixtures):
    mapping = {"arbeitnow.com": ("arbeitnow.json", "application/json")}
    with client_for(fixtures, mapping) as http:
        assert len(arbeitnow.fetch(http, "data analyst")) == 1
        assert arbeitnow.fetch(http, "kubernetes") == []


def test_himalayas(fixtures):
    with client_for(fixtures, {"himalayas.app": ("himalayas.json", "application/json")}) as http:
        items = himalayas.fetch(http, "")
    assert items[0]["location"] == "Brazil, Latin America"
    assert items[0]["published_at"] == 1785000000


def test_rss_generico(fixtures):
    with client_for(fixtures, {"weworkremotely": ("wwr.xml", "application/xml")}) as http:
        items = rss.fetch(http, "https://weworkremotely.com/categories/remote-programming-jobs.rss")
    assert len(items) == 1
    assert items[0]["title"].startswith("Codeline:")
    assert "Anywhere" in items[0]["location"]


def test_wwr_separa_empresa_do_cargo(fixtures):
    with client_for(fixtures, {"weworkremotely": ("wwr.xml", "application/xml")}) as http:
        items = weworkremotely.fetch(http, "")
    assert items[0]["company"] == "Codeline"
    assert items[0]["title"] == "Junior Ruby on Rails Developer"


def test_normalize_descarta_item_sem_titulo():
    assert sources.normalize("x", {"source_id": "1"}) is None
    assert sources.normalize("x", {"title": "Dev"}) is None


@pytest.mark.parametrize(
    "raw,esperado",
    [
        (1785000000, "2026"),
        ("2026-07-29T10:00:00", "2026-07-29"),
        ("Tue, 28 Jul 2026 09:00:00 +0000", "2026-07-28"),
        ("", None),
        ("banana", None),
    ],
)
def test_iso(raw, esperado):
    result = sources.iso(raw)
    if esperado is None:
        assert result is None
    else:
        assert result.startswith(esperado)


def test_to_text_preserva_paragrafos():
    text = sources.to_text("<p>Um</p><ul><li>Dois</li><li>Três</li></ul>")
    assert text.splitlines()[0] == "Um"
    assert "Dois" in text and "Três" in text


# ------------------------------------------------------------ termo de busca
# Regressão: o filtro exigia a frase literal na descrição, e por isso qualquer
# termo de mais de uma palavra devolvia lista vazia nestas fontes.


def test_arbeitnow_casa_palavras_soltas(fixtures):
    mapping = {"arbeitnow.com": ("arbeitnow.json", "application/json")}
    with client_for(fixtures, mapping) as http:
        assert len(arbeitnow.fetch(http, "analyst data")) == 1
        assert arbeitnow.fetch(http, "data kubernetes") == []


def test_himalayas_casa_palavras_soltas(fixtures):
    mapping = {"himalayas.app": ("himalayas.json", "application/json")}
    # a vaga da fixture é "Junior Backend Developer" com Node.js na descrição
    with client_for(fixtures, mapping) as http:
        assert len(himalayas.fetch(http, "junior node.js")) == 1
    with client_for(fixtures, mapping) as http:
        assert himalayas.fetch(http, "junior cobol") == []


def test_remoteok_manda_uma_tag_e_filtra_o_resto(fixtures):
    vistas = []

    def handler(request: httpx.Request) -> httpx.Response:
        vistas.append(dict(request.url.params))
        body = (fixtures / "remoteok.json").read_bytes()
        return httpx.Response(200, content=body, headers={"content-type": "application/json"})

    with httpx.Client(transport=httpx.MockTransport(handler)) as http:
        items = remoteok.fetch(http, "junior frontend")

    # a API do RemoteOK aceita uma tag só; o resto do termo é conferido aqui
    assert vistas[0] == {"tags": "junior"}
    assert len(items) == 1
    assert items[0]["title"] == "Junior Frontend Engineer"

    with httpx.Client(transport=httpx.MockTransport(handler)) as http:
        assert remoteok.fetch(http, "junior cobol") == []


def test_wwr_casa_palavras_soltas(fixtures):
    with client_for(fixtures, {"weworkremotely": ("wwr.xml", "application/xml")}) as http:
        assert weworkremotely.fetch(http, "ruby junior")
    with client_for(fixtures, {"weworkremotely": ("wwr.xml", "application/xml")}) as http:
        assert weworkremotely.fetch(http, "ruby cobol") == []


def test_user_agent_identifica_o_aplicativo():
    """Sem imitar navegador: é a postura correta e o que destrava o Himalayas."""
    with sources.client() as http:
        agent = http.headers["User-Agent"]
    assert agent.startswith("Farol/")
    assert "Mozilla" not in agent
    assert "Chrome" not in agent


# ----------------------------------------------------------------- vagas BR


def _vagasbr_client(fixtures):
    def handler(request: httpx.Request) -> httpx.Response:
        if "api.github.com" in str(request.url):
            body = (fixtures / "vagasbr.json").read_bytes()
            return httpx.Response(200, content=body, headers={"content-type": "application/json"})
        return httpx.Response(404)

    return httpx.Client(transport=httpx.MockTransport(handler))


def test_vagasbr_le_os_murais_da_comunidade(fixtures):
    with _vagasbr_client(fixtures) as http:
        items = vagasbr.fetch(http, "")
    # uma requisição por mural, todas respondidas com a mesma fixture
    assert len(items) == 4 * len(vagasbr.REPOS)
    primeiro = sources.normalize("vagasbr", items[0])
    assert primeiro["title"] == ".NET Backend Developer Pleno"   # colchetes fora do cargo
    assert primeiro["company"] == "Valorei"                       # veio de "## Nossa empresa"
    assert primeiro["location"].startswith("Brasil")
    assert "PostgreSQL" in primeiro["tags"]


def test_vagasbr_marca_presencial_e_empresa_do_titulo(fixtures):
    with _vagasbr_client(fixtures) as http:
        items = vagasbr.fetch(http, "")
    presencial = next(i for i in items if "Python" in i["title"])
    assert presencial["remote"] is False
    assert "Presencial" in presencial["location"]
    assert presencial["title"] == "Desenvolvedor Python Júnior"
    assert presencial["company"] == "Acme Tecnologia"


def test_vagasbr_descarta_pull_request():
    assert vagasbr.parse_issue({"title": "x", "html_url": "u", "pull_request": {}}, "r", "a") is None


def test_mural_da_comunidade_e_buscado_uma_vez_por_rodada():
    """Termo escrito para portal em inglês não casa com anúncio em português."""
    assert sources.fetches_once({"id": "vagasbr", "kind": "builtin"})
    assert sources.fetches_once({"id": "rss-1", "kind": "rss"})
    assert not sources.fetches_once({"id": "remotive", "kind": "builtin"})
