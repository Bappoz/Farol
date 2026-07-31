"""Descrição da vaga: HTML de entrada → texto guardado → HTML de exibição."""

from farol import markup
from farol.sources import to_text

ANUNCIO = """<h2>About the role</h2>
<p>We are hiring a <b>junior developer</b> to work with Python and FastAPI.</p>
<h3>Requirements</h3>
<ul><li>Python and SQL</li><li>Docker basics</li></ul>
<p>Apply at https://example.com/jobs/1</p>"""


def test_html_do_portal_vira_texto_com_marcadores():
    texto = to_text(ANUNCIO)
    assert "## About the role" in texto
    assert "- Python and SQL" in texto
    assert "- Docker basics" in texto
    assert "<" not in texto  # nenhuma tag sobrevive


def test_marcadores_viram_html_estruturado():
    html = markup.render(to_text(ANUNCIO))
    assert "<h4>About the role</h4>" in html
    assert "<h4>Requirements</h4>" in html
    assert "<ul><li>Python and SQL</li><li>Docker basics</li></ul>" in html
    assert "<p>" in html


def test_lista_fecha_antes_do_proximo_bloco():
    html = markup.render("- um\n- dois\n\nParágrafo final.")
    assert html == "<ul><li>um</li><li>dois</li></ul><p>Parágrafo final.</p>"


def test_itens_separados_por_linha_vazia_continuam_a_mesma_lista():
    """Portal que fecha bloco entre <li> gerava '- a\\n\\n- b' — é uma lista só."""
    assert markup.render("- um\n\n- dois") == "<ul><li>um</li><li>dois</li></ul>"


def test_lista_numerada_virou_ol():
    html = markup.render("1. primeiro\n2. segundo")
    assert html == "<ol><li>primeiro</li><li>segundo</li></ol>"


def test_ol_do_portal_mantem_a_ordem():
    """<ol> não pode virar bullet: em 'etapas do processo' a ordem é o conteúdo."""
    texto = to_text("<ol><li>Triagem</li><li>Técnica</li><li>Cultural</li></ol>")
    assert "1. Triagem" in texto and "2. Técnica" in texto and "3. Cultural" in texto
    assert markup.render(texto) == "<ol><li>Triagem</li><li>Técnica</li><li>Cultural</li></ol>"


def test_ul_e_ol_no_mesmo_anuncio_nao_se_misturam():
    html = markup.render(to_text("<ul><li>Python</li></ul><ol><li>Etapa um</li></ol>"))
    assert html == "<ul><li>Python</li></ul><ol><li>Etapa um</li></ol>"


def test_linha_terminando_em_dois_pontos_e_subtitulo():
    html = markup.render("Requisitos:\n- Python")
    assert html == "<h4>Requisitos</h4><ul><li>Python</li></ul>"


def test_linhas_seguidas_formam_um_paragrafo():
    html = markup.render("primeira linha\nsegunda linha\n\noutro bloco")
    assert html == "<p>primeira linha segunda linha</p><p>outro bloco</p>"


def test_html_do_anuncio_e_escapado_e_nao_executado():
    """Descrição vem de portal de terceiro: nada dela pode virar marcação real."""
    html = markup.render('<script>alert("x")</script> e <b>negrito</b>')
    assert "<script>" not in html
    assert "&lt;script&gt;" in html
    assert "<b>" not in html


def test_url_vira_link_seguro():
    html = markup.render("Inscreva-se em https://example.com/vaga")
    assert '<a href="https://example.com/vaga" target="_blank" rel="noreferrer">' in html


def test_texto_vazio_nao_gera_marcacao():
    assert markup.render("") == ""
    assert markup.render(None) == ""
    assert markup.render("   \n  ") == ""


def test_descricao_antiga_sem_marcadores_continua_legivel():
    """Base gravada antes dos marcadores existirem cai no caminho de parágrafo."""
    html = markup.render("Vaga para dev junior.\n\nStack: Python, Docker.")
    assert html == "<p>Vaga para dev junior.</p><p>Stack: Python, Docker.</p>"
