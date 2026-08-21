"""Casamento entre termo de busca e anúncio.

A regressão que estes testes travam: exigir a frase literal fazia
`junior backend python` devolver zero resultado em quatro das cinco fontes, já
que nenhum anúncio traz as três palavras nessa ordem.
"""

from farol.sources.query import first_term, matches


def test_termo_vazio_aceita_tudo():
    assert matches("", "qualquer coisa")
    assert matches(None, "qualquer coisa")


def test_uma_palavra_casa_em_qualquer_campo():
    assert matches("python", "Backend Engineer", "trabalhamos com Python e Go")
    assert not matches("rust", "Backend Engineer", "trabalhamos com Python e Go")


def test_todas_as_palavras_precisam_aparecer():
    titulo = "Backend Developer"
    corpo = "Buscamos pessoa junior para trabalhar com Python."
    assert matches("junior backend python", titulo, corpo)
    assert not matches("junior backend rust", titulo, corpo)


def test_ordem_das_palavras_nao_importa():
    assert matches("python junior", "Junior Python Developer")
    assert matches("junior python", "Junior Python Developer")


def test_ignora_maiuscula_pontuacao_e_espaco_extra():
    assert matches("  Node.JS,  React ", "Vaga de node.js com react")


def test_campo_ausente_nao_quebra():
    assert matches("python", None, "", "Python")


def test_primeira_palavra_para_api_de_tag_unica():
    assert first_term("junior backend python") == "junior"
    assert first_term("  ") == ""
