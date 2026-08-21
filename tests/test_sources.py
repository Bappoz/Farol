"""Coletores rodam contra respostas gravadas — sem rede, sem surpresa."""

import httpx
import pytest

from farol import sources
from farol.sources import arbeitnow, himalayas, remoteok, remotive, rss, weworkremotely


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


def test_user_agent_identifica_o_aplicativo():
    """Sem imitar navegador: é a postura correta e o que destrava o Himalayas."""
    with sources.client() as http:
        agent = http.headers["User-Agent"]
    assert agent.startswith("Farol/")
    assert "Mozilla" not in agent
    assert "Chrome" not in agent
