"""Verificador ATS determinístico: nota de 0 a 100 sem IA, sem rede e sem modelo.

Nenhum ATS publica a nota que dá a um currículo, então isto não finge reproduzir
o Gupy ou o Greenhouse. O que se mede aqui são as causas conhecidas e públicas
de um currículo ser mal lido ou mal ranqueado por um filtro automático: formato
que o parser embaralha, contato que ele não acha, seção que ele não reconhece,
marcador sem verbo nem número e termo da vaga que não aparece no texto.

Três compromissos, e os testes seguram os três:

    reproduzível   mesma entrada, mesma nota. Nada de data de hoje, nada de
                   aleatório, nada de ordem de dicionário.
    explicável     cada ponto perdido vem com o porquê e o que fazer.
    honesto        o verificador nunca sugere escrever competência que você não
                   tem. Termo da vaga ausente vira "cite onde usou, se usou".

A mesma régua serve ao currículo montado no editor (`check`) e ao PDF enviado
(`check_text`), que só tem o texto extraído para olhar.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field
from typing import Any

from . import db, skills

PLACEHOLDER = "[preencher]"

OK, WARN, FAIL, SKIP = "ok", "warn", "fail", "skip"
_VALUE = {OK: 1.0, WARN: 0.5, FAIL: 0.0}

# Peso de cada categoria na nota final. A aderência só entra quando há vaga;
# sem ela os demais pesos são renormalizados, então a nota continua indo a 100.
CATEGORIES: tuple[tuple[str, str, int], ...] = (
    ("formato", "Leitura pelo robô", 25),
    ("contato", "Contato", 15),
    ("estrutura", "Estrutura", 20),
    ("conteudo", "Conteúdo", 40),
    ("vaga", "Aderência à vaga", 30),
)

GRADES: tuple[tuple[int, str, str], ...] = (
    (85, "forte", "Pronto para enviar"),
    (70, "bom", "Bom, com ajustes"),
    (50, "regular", "Precisa de trabalho"),
    (0, "fraco", "Arriscado para filtro automático"),
)

# Falhas que um ajuste fino no resto não compensa: currículo com [preencher]
# esquecido, sem e-mail, sem experiência nem projeto, em idioma trocado ou em
# PDF sem texto não está pronto, por melhores que sejam os marcadores. Enquanto
# uma delas existir, a nota não passa de BLOCKED_CAP — e a tela diz qual é.
BLOCKERS = {"pendencias", "email", "experiencia", "idioma", "texto"}
BLOCKED_CAP = 64

# Modelos que um parser lê sem embaralhar a ordem do texto. Fica aqui, e não em
# `resume.TEMPLATES`, só o veredito: quem conhece o risco é o verificador.
RISKY_LAYOUTS = {"duas-colunas"}

_EMAIL = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9-]+(?:\.[A-Za-z0-9-]+)*\.[A-Za-z]{2,}")
_EMAIL_FULL = re.compile(rf"^{_EMAIL.pattern}$")
_PHONE = re.compile(r"(?:\+?\d[\d\s().-]{7,}\d)")
_YEAR = re.compile(r"\b(?:19|20)\d{2}\b")
_NUMBER = re.compile(r"\d")
_URLISH = re.compile(r"^(?:https?://)?[A-Za-z0-9-]+(?:\.[A-Za-z0-9-]+)+(?:[/?#]\S*)?$")
_WORD = re.compile(r"[A-Za-zÀ-ÿ0-9][A-Za-zÀ-ÿ0-9+#./'-]*")
_BULLET_LINE = re.compile(r"^\s*[•\-–—*·▪◦‣●○■□➤►✓✔]\s+(\S.*)$")

# Caracteres que parser de ATS costuma trocar por "?" ou descartar junto com a
# linha: símbolos decorativos, setas, caixas, emoji. Travessão, aspas curvas e
# o marcador "•" ficam de fora — todo parser atual lê.
_DECORATIVE = re.compile(
    "[←-⇿─-◿☀-➿⬀-⯿\U0001f000-\U0001faff️]"
)
_DECORATIVE_OK = {"•", "●", "▪"}

_ACTION_VERBS = {
    # português, 1ª pessoa do pretérito e infinitivo — quem escreve currículo usa os dois
    "desenvolvi", "implementei", "criei", "construi", "projetei", "liderei",
    "reduzi", "aumentei", "automatizei", "migrei", "otimizei", "entreguei", "publiquei",
    "integrei", "testei", "corrigi", "refatorei", "modelei", "analisei", "escrevi",
    "configurei", "documentei", "organizei", "coordenei", "apresentei", "treinei",
    "mantive", "fiz", "subi", "cobri", "defini", "conduzi", "resolvi", "lancei",
    "medi", "monitorei", "padronizei", "eliminei", "economizei", "acelerei",
    "ampliei", "desenhei", "prototipei", "validei", "pesquisei", "ensinei", "atendi",
    "negociei", "planejei", "estruturei", "implantei", "adaptei", "converti", "dobrei",
    "desenvolver", "implementar", "criar", "construir", "projetar", "liderar",
    # inglês, pretérito
    "built", "developed", "implemented", "created", "designed", "led", "reduced",
    "increased", "automated", "migrated", "optimized", "delivered", "shipped",
    "integrated", "tested", "fixed", "refactored", "modeled", "analyzed", "wrote",
    "configured", "documented", "organized", "coordinated", "presented", "trained",
    "maintained", "made", "deployed", "covered", "defined", "drove", "solved",
    "launched", "measured", "monitored", "standardized", "removed", "saved", "cut",
    "improved", "prototyped", "validated", "researched", "taught", "supported",
    "negotiated", "planned", "structured", "adapted", "converted", "doubled", "ran",
    "set", "owned", "rewrote", "scaled", "introduced", "published", "won",
}

# Começos que parecem verbo e não entregam nada: descrevem presença, não resultado.
_WEAK_STARTS = (
    "responsavel por", "responsavel pela", "responsavel pelo", "responsible for",
    "ajudei", "ajudando", "auxiliei", "auxilio", "participei", "participacao",
    "atuei", "atuacao", "trabalhei", "trabalho com", "helped", "assisted",
    "worked on", "worked with", "participated", "involved in", "duties included",
    "tasks included", "atividades", "experiencia com", "experience with",
    "conhecimento em", "knowledge of",
)

# Substantivos que terminam como verbo conjugado em português ("api", "kpi").
_NOT_VERBS = {
    "api", "kpi", "ui", "wifi", "wi-fi", "cli", "sdk", "poc", "mvp", "rei", "lei",
    "okr", "tdd", "bdd", "ci", "raspberry", "wiki", "kiwi", "hoje", "aqui",
}

_CLICHES = (
    "proativo", "proativa", "pro-ativo", "apaixonado por", "apaixonada por",
    "dinamico", "dinamica", "fora da caixa", "busco novos desafios",
    "buscando desafios", "buscando novos desafios", "facilidade de aprendizado",
    "trabalho em equipe", "perfil analitico", "comprometido", "comprometida",
    "focado em resultados", "focada em resultados", "team player", "hard-working",
    "hard working", "hardworking", "detail-oriented", "detail oriented",
    "results-driven", "results driven", "passionate about", "self-starter",
    "self starter", "go-getter", "think outside the box", "fast learner",
    "quick learner", "motivated", "synergy", "ninja", "rockstar", "guru",
)

_FIRST_PERSON = re.compile(r"\b(?:eu|meu|minha|meus|minhas|i|my|me)\b", re.IGNORECASE)

_STOP_PT = {"de", "que", "com", "para", "uma", "nao", "em", "os", "as", "do", "da", "na", "no", "e", "um", "por"}
_STOP_EN = {"the", "and", "with", "for", "of", "to", "in", "a", "on", "is", "by", "an", "at", "from", "that"}

# Palavras do título da vaga que não dizem o que a vaga é.
_TITLE_NOISE = {
    "junior", "jr", "pleno", "senior", "sr", "trainee", "estagio", "estagiario",
    "estagiaria", "intern", "internship", "entry", "level", "remote", "remoto",
    "remota", "hibrido", "vaga", "para", "de", "em", "and", "the", "of", "a", "e",
    "i", "ii", "iii", "mid", "pessoa", "desenvolvedora", "m", "f", "h",
}

_SECTION_HEADS: dict[str, tuple[str, ...]] = {
    "experiência": ("experiencia", "experiencia profissional", "experience", "work experience",
                    "professional experience", "employment", "historico profissional"),
    "formação": ("formacao", "formacao academica", "educacao", "education", "academic background"),
    "competências": ("competencias", "habilidades", "skills", "technical skills",
                     "conhecimentos", "tecnologias", "hard skills"),
    "projetos": ("projetos", "projects", "personal projects", "projetos pessoais"),
    "resumo": ("resumo", "resumo profissional", "summary", "profile", "perfil",
               "objetivo", "objective", "about", "sobre", "sobre mim"),
}


def _fold(text: str) -> str:
    """Minúsculas sem acento, para comparar termo com termo."""
    decomposed = unicodedata.normalize("NFKD", text or "")
    return "".join(ch for ch in decomposed if not unicodedata.combining(ch)).lower()


def _words(text: str) -> list[str]:
    return _WORD.findall(text or "")


def _join(items: list[str], limit: int = 4) -> str:
    shown = [item for item in items if item][:limit]
    extra = len([item for item in items if item]) - len(shown)
    return ", ".join(shown) + (f" e mais {extra}" if extra > 0 else "")


def _quote(text: str, size: int = 70) -> str:
    text = " ".join((text or "").split())
    return f"“{text[:size].rstrip()}{'…' if len(text) > size else ''}”"


@dataclass
class Check:
    key: str
    category: str
    label: str
    status: str
    weight: int
    detail: str = ""
    fix: str = ""

    def as_dict(self) -> dict[str, Any]:
        return {
            "key": self.key, "label": self.label, "status": self.status,
            "weight": self.weight, "detail": self.detail, "fix": self.fix,
        }


@dataclass
class Doc:
    """O que o verificador enxerga, venha do editor ou do texto de um PDF."""

    structured: bool
    lang: str = "pt"
    layout: str = "uma-coluna"
    template_label: str = ""
    name: str = ""
    headline: str = ""
    email: str = ""
    phone: str = ""
    city: str = ""
    links: list[str] = field(default_factory=list)
    summary: str = ""
    skills: list[str] = field(default_factory=list)
    # (rótulo do item, período, marcadores)
    experience: list[tuple[str, str, list[str]]] = field(default_factory=list)
    projects: list[tuple[str, str, list[str]]] = field(default_factory=list)
    education: list[tuple[str, str]] = field(default_factory=list)
    languages: list[str] = field(default_factory=list)
    bullets: list[str] = field(default_factory=list)
    sections: list[str] = field(default_factory=list)
    text: str = ""

    @property
    def words(self) -> int:
        return len(_words(self.text))


def _doc_from_resume(resume: dict[str, Any], lang: str, layout: str, label: str) -> Doc:
    def clean(value: Any) -> str:
        return str(value or "").strip()

    def entries(key: str, title: tuple[str, ...]) -> list[tuple[str, str, list[str]]]:
        found = []
        for item in resume.get(key) or []:
            if not isinstance(item, dict):
                continue
            name = " — ".join(clean(item.get(f)) for f in title if clean(item.get(f)))
            marks = [clean(b) for b in (item.get("bullets") or []) if clean(b)]
            found.append((name, clean(item.get("period")), marks))
        return found

    experience = entries("experience", ("role", "org"))
    projects = entries("projects", ("name",))
    education = [
        (" — ".join(clean(item.get(f)) for f in ("course", "school") if clean(item.get(f))),
         clean(item.get("period")))
        for item in (resume.get("education") or []) if isinstance(item, dict)
    ]
    languages = [
        f"{clean(item.get('name'))} ({clean(item.get('level'))})"
        for item in (resume.get("languages") or [])
        if isinstance(item, dict) and clean(item.get("name"))
    ]
    links = [clean(link.get("url")) for link in (resume.get("links") or [])
             if isinstance(link, dict) and clean(link.get("url"))]
    owned = [clean(s) for s in (resume.get("skills") or []) if clean(s)]
    bullets = [b for _, _, marks in experience + projects for b in marks]

    stacks = [clean(item.get("stack")) for item in (resume.get("projects") or [])
              if isinstance(item, dict)]
    notes = [clean(item.get("note")) for item in (resume.get("education") or [])
             if isinstance(item, dict)]
    doc = Doc(
        structured=True, lang=lang, layout=layout, template_label=label,
        name=clean(resume.get("name")), headline=clean(resume.get("headline")),
        email=clean(resume.get("email")), phone=clean(resume.get("phone")),
        city=clean(resume.get("city")), links=links, summary=clean(resume.get("summary")),
        skills=owned, experience=experience, projects=projects, education=education,
        languages=languages, bullets=bullets,
    )
    doc.text = "\n".join(
        part for part in [
            doc.name, doc.headline, doc.city, doc.email, doc.phone, *links, doc.summary,
            " ".join(skills.display(s, lang) for s in owned),
            *(f"{name} {period}" for name, period, _ in experience + projects),
            *stacks, *bullets, *(f"{name} {period}" for name, period in education),
            *notes, *languages,
        ] if part
    )
    return doc


def _doc_from_text(text: str, lang: str) -> Doc:
    text = text or ""
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    bullets = [m.group(1).strip() for line in lines if (m := _BULLET_LINE.match(line))]
    email = _EMAIL.search(text)
    phone = _PHONE.search(text)
    folded_lines = {_fold(line).strip(" :-–—|").strip() for line in lines if len(line) <= 40}
    sections = [name for name, heads in _SECTION_HEADS.items() if folded_lines & set(heads)]
    links = re.findall(r"(?:https?://)?(?:www\.)?(?:linkedin\.com|github\.com|gitlab\.com)/[^\s,;|)]+", text)
    return Doc(
        structured=False, lang=lang, name=lines[0] if lines else "",
        email=email.group(0) if email else "", phone=phone.group(0).strip() if phone else "",
        links=links, bullets=bullets, sections=sections, text=text,
        skills=skills.extract(text),
    )


# ------------------------------------------------------------------ formato


def _check_layout(doc: Doc) -> Check:
    risky = doc.layout in RISKY_LAYOUTS
    return Check(
        "layout", "formato", "Modelo de uma coluna", FAIL if risky else OK, 12,
        detail=(f"O modelo {doc.template_label or 'escolhido'} usa duas colunas. Parser de ATS lê a "
                "página da esquerda para a direita, linha por linha: o texto da barra lateral "
                "entra no meio da experiência." if risky else
                "Uma coluna: o texto sai na ordem em que foi escrito."),
        fix=("Para subir em formulário, troque para Sóbrio, Harvard ou FAANG. Guarde este modelo "
             "para quando uma pessoa abre o PDF direto." if risky else ""),
    )


def _check_text_layer(doc: Doc) -> Check:
    chars = len(doc.text.strip())
    if chars >= 400:
        return Check("texto", "formato", "PDF com texto legível", OK, 10,
                     detail=f"{doc.words} palavras extraídas do arquivo.")
    if chars >= 80:
        return Check("texto", "formato", "PDF com texto legível", WARN, 10,
                     detail=f"Só {doc.words} palavras saíram do arquivo — parte do conteúdo pode ser imagem.",
                     fix="Exporte de novo a partir do documento original, como PDF de texto (não digitalizado).")
    return Check("texto", "formato", "PDF com texto legível", FAIL, 10,
                 detail="Quase nenhum texto saiu do arquivo. Para um ATS, este PDF está em branco.",
                 fix="PDF escaneado ou exportado como imagem não é lido. Gere o PDF a partir do editor de texto.")


def _check_characters(doc: Doc) -> Check:
    found = sorted({ch for ch in _DECORATIVE.findall(doc.text) if ch not in _DECORATIVE_OK})
    found = [ch for ch in found if ch != "️"]
    if not found and "\t" not in doc.text:
        return Check("caracteres", "formato", "Sem símbolo que quebra o parser", OK, 5,
                     detail="Nenhum emoji, seta ou caractere decorativo no texto.")
    what = " ".join(found[:8]) or "tabulação"
    return Check("caracteres", "formato", "Sem símbolo que quebra o parser", WARN, 5,
                 detail=f"Encontrado: {what}. Muitos ATS trocam isso por “?” ou descartam a linha.",
                 fix="Troque por texto simples: hífen ou o marcador padrão “•”, e escreva a palavra no lugar do ícone.")


def _check_dates(doc: Doc) -> Check:
    if doc.structured:
        dated = [(name, period) for name, period, _ in doc.experience] + list(doc.education)
        if not dated:
            return Check("datas", "formato", "Períodos com ano", SKIP, 6)
        missing = [name or "item sem título" for name, period in dated if not _YEAR.search(period)]
        if not missing:
            return Check("datas", "formato", "Períodos com ano", OK, 6,
                         detail="Toda experiência e formação tem período com ano.")
        status = FAIL if len(missing) > len(dated) / 2 else WARN
        return Check("datas", "formato", "Períodos com ano", status, 6,
                     detail=f"Sem ano reconhecível: {_join(missing)}.",
                     fix="Escreva o período como “mar 2024 – atual” ou “2023 – 2025”. ATS calcula tempo de experiência a partir disso.")
    years = len(_YEAR.findall(doc.text))
    if years >= 2:
        return Check("datas", "formato", "Períodos com ano", OK, 6, detail=f"{years} datas com ano no texto.")
    return Check("datas", "formato", "Períodos com ano", WARN if years else FAIL, 6,
                 detail="Poucas datas com ano no texto." if years else "Nenhuma data com ano no texto.",
                 fix="Cada experiência e formação precisa de período com ano: “2023 – 2025”.")


def _check_links(doc: Doc) -> Check:
    if not doc.links:
        return Check("links", "formato", "Links por extenso e válidos", SKIP, 3)
    broken = [link for link in doc.links if " " in link or not _URLISH.match(link)]
    if broken:
        return Check("links", "formato", "Links por extenso e válidos", WARN, 3,
                     detail=f"Não parece um endereço: {_join(broken, 3)}.",
                     fix="Use o endereço inteiro, sem espaço: https://linkedin.com/in/seu-nome.")
    return Check("links", "formato", "Links por extenso e válidos", OK, 3,
                 detail="Endereços escritos por extenso — sobrevivem mesmo quando o ATS descarta o hiperlink.")


def _check_headings(doc: Doc) -> Check:
    """Só no PDF: no editor os títulos de seção são os do próprio app."""
    core = [name for name in ("experiência", "formação", "competências") if name in doc.sections]
    if "projetos" in doc.sections and "experiência" not in core:
        core.append("projetos")
    missing = [name for name in ("experiência", "formação", "competências") if name not in doc.sections]
    if len(core) >= 3:
        return Check("titulos", "formato", "Seções com título padrão", OK, 7,
                     detail=f"Reconhecidas: {_join(doc.sections, 6)}.")
    return Check("titulos", "formato", "Seções com título padrão", WARN if len(core) == 2 else FAIL, 7,
                 detail=(f"Reconhecidas: {_join(doc.sections, 6)}. " if doc.sections else "Nenhum título de seção reconhecido. ")
                        + f"Não encontrei: {_join(missing)}.",
                 fix="Use títulos que o ATS conhece, sozinhos na linha: Experiência, Formação, Competências. "
                     "“Minha trajetória” ou “O que eu sei” não são reconhecidos.")


# ------------------------------------------------------------------ contato


def _check_name(doc: Doc) -> Check:
    ok = bool(doc.name) and PLACEHOLDER not in doc.name
    return Check("nome", "contato", "Nome no topo", OK if ok else FAIL, 3,
                 detail="" if ok else "O currículo está sem nome.",
                 fix="" if ok else "Preencha o nome no Perfil e remonte, ou edite o cabeçalho.")


def _check_email(doc: Doc) -> Check:
    if doc.email and _EMAIL_FULL.match(doc.email):
        return Check("email", "contato", "E-mail válido", OK, 5, detail=doc.email)
    return Check("email", "contato", "E-mail válido", FAIL, 5,
                 detail=("Não encontrei e-mail." if not doc.email or PLACEHOLDER in doc.email
                         else f"“{doc.email}” não parece um e-mail."),
                 fix="Sem e-mail legível o recrutador não tem como responder. Use nome@dominio, em texto.")


def _check_phone(doc: Doc) -> Check:
    digits = sum(ch.isdigit() for ch in doc.phone)
    if digits >= 8:
        return Check("telefone", "contato", "Telefone com DDD", OK, 3, detail=doc.phone)
    return Check("telefone", "contato", "Telefone com DDD", WARN, 3,
                 detail="Sem telefone." if not digits else "O telefone parece incompleto.",
                 fix="Inclua DDD (e +55 em vaga de fora): recrutador ainda liga e manda WhatsApp.")


def _check_city(doc: Doc) -> Check:
    if not doc.structured:
        return Check("cidade", "contato", "Cidade e estado", SKIP, 2)
    return Check("cidade", "contato", "Cidade e estado", OK if doc.city else WARN, 2,
                 detail=doc.city or "Sem localização.",
                 fix="" if doc.city else "Cidade e estado bastam. Muito ATS filtra por localização, inclusive em vaga remota.")


def _check_profiles(doc: Doc) -> list[Check]:
    joined = _fold(" ".join(doc.links) + " " + ("" if doc.structured else doc.text))
    linkedin = "linkedin.com" in joined
    code = any(site in joined for site in ("github.com", "gitlab.com", "bitbucket.org"))
    return [
        Check("linkedin", "contato", "LinkedIn", OK if linkedin else WARN, 2,
              detail="" if linkedin else "Sem link do LinkedIn.",
              fix="" if linkedin else "Adicione o endereço do perfil no cabeçalho — é o primeiro lugar onde o recrutador confere o que leu."),
        Check("codigo", "contato", "GitHub ou portfólio", OK if code else WARN, 2,
              detail="" if code else "Sem link para código.",
              fix="" if code else "Em vaga técnica de entrada, o link do código pesa mais que o resumo."),
    ]


# ---------------------------------------------------------------- estrutura


def _check_summary(doc: Doc) -> Check:
    if not doc.structured:
        return Check("resumo", "estrutura", "Resumo no tamanho certo", SKIP, 4)
    size = len(_words(doc.summary))
    if not size:
        return Check("resumo", "estrutura", "Resumo no tamanho certo", WARN, 4,
                     detail="Sem resumo.",
                     fix="Duas a quatro linhas: o que você faz, com o quê e o que procura. É onde cabem os termos da vaga em frase.")
    if PLACEHOLDER in doc.summary:
        return Check("resumo", "estrutura", "Resumo no tamanho certo", FAIL, 4,
                     detail="O resumo ainda é o rascunho do app.",
                     fix="Reescreva com as suas palavras e apague o [preencher].")
    if size < 15:
        return Check("resumo", "estrutura", "Resumo no tamanho certo", WARN, 4,
                     detail=f"{size} palavras — curto demais para dizer algo.",
                     fix="Chegue a 30–70 palavras, com a tecnologia principal e um resultado.")
    if size > 110:
        return Check("resumo", "estrutura", "Resumo no tamanho certo", WARN, 4,
                     detail=f"{size} palavras — vira parágrafo que ninguém lê.",
                     fix="Corte para 30–70 palavras. O detalhe vai nos marcadores.")
    return Check("resumo", "estrutura", "Resumo no tamanho certo", OK, 4, detail=f"{size} palavras.")


def _check_core_sections(doc: Doc) -> list[Check]:
    if not doc.structured:
        return []
    has_work = bool(doc.experience or doc.projects)
    return [
        Check("experiencia", "estrutura", "Experiência ou projetos", OK if has_work else FAIL, 6,
              detail=(f"{len(doc.experience)} experiência(s) e {len(doc.projects)} projeto(s)." if has_work
                      else "O currículo não tem experiência nem projeto."),
              fix="" if has_work else "Sem emprego anterior, projeto é a experiência: cadastre dois no Perfil, com link e o que você resolveu."),
        Check("formacao", "estrutura", "Formação", OK if doc.education else WARN, 3,
              detail="" if doc.education else "Sem formação.",
              fix="" if doc.education else "Inclua curso, instituição e período — vale curso em andamento."),
    ]


def _check_skill_count(doc: Doc) -> Check:
    count = len(doc.skills)
    label = "Competências na medida"
    if count < 3:
        return Check("competencias", "estrutura", label, FAIL, 4,
                     detail=f"{count} competência(s) reconhecida(s).",
                     fix="É a seção que o ATS mais usa para casar com a vaga. Liste as tecnologias que você de fato usou.")
    if count < 6:
        return Check("competencias", "estrutura", label, WARN, 4,
                     detail=f"{count} competências — pouco para casar com a busca do recrutador.",
                     fix="Chegue a 6–15, incluindo ferramentas (Git, Docker, banco) além das linguagens.")
    if count > 30:
        return Check("competencias", "estrutura", label, WARN, 4,
                     detail=f"{count} competências — lista longa assim lê como enchimento de palavra-chave.",
                     fix="Fique com as 15–20 que você defenderia numa conversa técnica.")
    return Check("competencias", "estrutura", label, OK, 4, detail=f"{count} competências.")


def _check_length(doc: Doc) -> Check:
    words = doc.words
    label = "Tamanho do currículo"
    if words < 100:
        return Check("tamanho", "estrutura", label, FAIL, 6,
                     detail=f"{words} palavras — poucas linhas.",
                     fix="Detalhe projetos e entregas: o ATS ranqueia pelo texto, e aqui quase não há texto.")
    if words < 150:
        return Check("tamanho", "estrutura", label, WARN, 6,
                     detail=f"{words} palavras — menos de meia página.",
                     fix="Há espaço para mais dois ou três marcadores com resultado.")
    if words <= 750:
        return Check("tamanho", "estrutura", label, OK, 6, detail=f"{words} palavras — cabe em uma página.")
    if words <= 1100:
        return Check("tamanho", "estrutura", label, WARN, 6,
                     detail=f"{words} palavras — passa de uma página.",
                     fix="Em início de carreira, uma página. Corte o item mais antigo ou menos ligado à vaga.")
    return Check("tamanho", "estrutura", label, FAIL, 6,
                 detail=f"{words} palavras — duas páginas ou mais.",
                 fix="Corte pela metade: mantenha o que responde a esta vaga.")


def _check_placeholder(doc: Doc) -> Check:
    count = doc.text.count(PLACEHOLDER)
    return Check("pendencias", "estrutura", "Nada por preencher", FAIL if count else OK, 3,
                 detail=f"{count} trecho(s) com [preencher] ainda no currículo." if count else "",
                 fix="Procure por [preencher] e resolva cada um antes de enviar." if count else "")


# ----------------------------------------------------------------- conteúdo


def _first_word(bullet: str) -> str:
    words = _words(bullet)
    return words[0] if words else ""


def is_action_start(bullet: str) -> bool:
    """O marcador abre com verbo de entrega? Lista explícita + terminação do pretérito."""
    folded = _fold(bullet).strip()
    if not folded or folded.startswith(_WEAK_STARTS):
        return False
    first = _fold(_first_word(bullet))
    if first in _ACTION_VERBS:
        return True
    if first in _NOT_VERBS or len(first) < 4 or not first.isalpha():
        return False
    # pretérito em português (-ei, -i, -ou, -iu) e em inglês (-ed)
    return first.endswith(("ei", "ou", "iu", "ed")) or (first.endswith("i") and not first.endswith(("ai", "oi", "ui")))


def _nothing_to_measure(doc: Doc, key: str, label: str) -> Check:
    """Sem marcador não há verbo nem número para avaliar.

    No editor isso é falta de conteúdo e custa ponto. No PDF pode ser só o
    marcador que se perdeu na extração do texto — aí a checagem fica de fora,
    em vez de acusar o que não dá para ver.
    """
    if not doc.structured:
        return Check(key, "conteudo", label, SKIP, 10)
    return Check(key, "conteudo", label, FAIL, 10,
                 detail="Não há marcadores para avaliar.",
                 fix="Escreva as entregas de cada experiência e projeto em marcadores, um por linha.")


def _check_bullet_count(doc: Doc) -> Check:
    count = len(doc.bullets)
    label = "Marcadores de entrega"
    if doc.structured:
        thin = [name or "item sem título" for name, _, marks in doc.experience + doc.projects if len(marks) < 2]
        if count >= 4 and not thin:
            return Check("marcadores", "conteudo", label, OK, 10, detail=f"{count} marcadores.")
        if count >= 4:
            return Check("marcadores", "conteudo", label, WARN, 10,
                         detail=f"Com menos de dois marcadores: {_join(thin)}.",
                         fix="Cada experiência ou projeto pede dois a quatro marcadores: o que você fez e o que mudou.")
        return Check("marcadores", "conteudo", label, FAIL, 10,
                     detail=f"{count} marcador(es) no currículo inteiro.",
                     fix="Chegue a pelo menos quatro. Marcador é onde o ATS acha a palavra-chave em contexto e a pessoa acha o resultado.")
    if count >= 4:
        return Check("marcadores", "conteudo", label, OK, 10, detail=f"{count} marcadores.")
    return Check("marcadores", "conteudo", label, WARN, 10,
                 detail=f"{count} linha(s) em formato de marcador no texto extraído.",
                 fix="Descreva cada experiência em marcadores curtos, não em parágrafo.")


def _check_action_verbs(doc: Doc) -> Check:
    label = "Marcadores começam com verbo de ação"
    if len(doc.bullets) < 2:
        return _nothing_to_measure(doc, "verbos", label)
    weak = [b for b in doc.bullets if not is_action_start(b)]
    share = 1 - len(weak) / len(doc.bullets)
    if share >= 0.7:
        return Check("verbos", "conteudo", label, OK, 10,
                     detail=f"{len(doc.bullets) - len(weak)} de {len(doc.bullets)} abrem com verbo.")
    verbs = "Built, Reduced, Automated" if doc.lang == "en" else "Desenvolvi, Reduzi, Automatizei"
    return Check("verbos", "conteudo", label, WARN if share >= 0.4 else FAIL, 10,
                 detail=f"{len(weak)} de {len(doc.bullets)} não abrem com verbo. Ex.: {_quote(weak[0])}",
                 fix=f"Comece pelo que você fez: {verbs}. “Responsável por” e “Participei de” descrevem presença, não entrega.")


def _check_numbers(doc: Doc) -> Check:
    label = "Resultados com número"
    if len(doc.bullets) < 2:
        return _nothing_to_measure(doc, "numeros", label)
    with_number = [b for b in doc.bullets if _NUMBER.search(b)]
    need = max(1, -(-len(doc.bullets) // 3))
    if len(with_number) >= need:
        return Check("numeros", "conteudo", label, OK, 10,
                     detail=f"{len(with_number)} de {len(doc.bullets)} marcadores têm número.")
    without = next(b for b in doc.bullets if not _NUMBER.search(b))
    return Check("numeros", "conteudo", label, WARN if with_number else FAIL, 10,
                 detail=f"{len(with_number)} de {len(doc.bullets)} marcadores têm número (meta: {need}). Sem número: {_quote(without)}",
                 fix="Meça o que der: tempo, volume, cobertura, usuários. “Reduzi o tempo de resposta de 800 ms para 200 ms” no lugar de “melhorei a performance”. Só use número que você sabe defender.")


def _check_bullet_length(doc: Doc) -> Check:
    label = "Marcadores no tamanho certo"
    if len(doc.bullets) < 2:
        return Check("tamanho_marcador", "conteudo", label, SKIP, 4)
    sizes = [(b, len(_words(b))) for b in doc.bullets]
    long = [b for b, n in sizes if n > 32]
    short = [b for b, n in sizes if n < 4]
    off = long + short
    if len(off) <= len(sizes) / 4:
        return Check("tamanho_marcador", "conteudo", label, OK, 4, detail="Entre 4 e 32 palavras cada.")
    which = (f"{len(long)} longo(s) demais" if long else "") + (" e " if long and short else "") + \
            (f"{len(short)} curto(s) demais" if short else "")
    return Check("tamanho_marcador", "conteudo", label, WARN, 4,
                 detail=f"{which}. Ex.: {_quote(off[0])}",
                 fix="Uma ou duas linhas por marcador. O longo vira dois; o curto ganha o resultado que faltou.")


def _check_cliches(doc: Doc) -> Check:
    haystack = f" {_fold(doc.text)} "
    found = sorted({c for c in _CLICHES if re.search(rf"(?<![a-z]){re.escape(c)}(?![a-z])", haystack)})
    if not found:
        return Check("cliches", "conteudo", "Sem adjetivo vazio", OK, 4)
    return Check("cliches", "conteudo", "Sem adjetivo vazio", WARN if len(found) < 3 else FAIL, 4,
                 detail=f"Encontrado: {_join(found, 5)}.",
                 fix="Troque o adjetivo pelo fato que o prova. Todo currículo diz “proativo”; quase nenhum diz o que foi feito.")


def _check_first_person(doc: Doc) -> Check:
    scope = " ".join(doc.bullets) if doc.bullets else ""
    if doc.structured:
        scope += " " + doc.summary
    hits = _FIRST_PERSON.findall(scope)
    # "I" maiúsculo solto só conta em currículo em inglês; "me" e "a" confundem em português
    hits = [h for h in hits if h.lower() not in {"i", "me", "my"} or doc.lang == "en"]
    if len(hits) <= 1:
        return Check("pessoa", "conteudo", "Sem pronome de primeira pessoa", OK, 2)
    return Check("pessoa", "conteudo", "Sem pronome de primeira pessoa", WARN, 2,
                 detail=f"{len(hits)} ocorrências de “{hits[0]}” e afins.",
                 fix="Currículo dispensa o sujeito: “Desenvolvi a API”, não “Eu desenvolvi a minha API”.")


def _check_repetition(doc: Doc) -> Check:
    label = "Verbos variados"
    if len(doc.bullets) < 5:
        return Check("repeticao", "conteudo", label, SKIP, 3)
    counts: dict[str, int] = {}
    for bullet in doc.bullets:
        first = _fold(_first_word(bullet))
        if first:
            counts[first] = counts.get(first, 0) + 1
    word, top = max(counts.items(), key=lambda kv: (kv[1], kv[0]))
    if top >= 3 and top / len(doc.bullets) > 0.4:
        return Check("repeticao", "conteudo", label, WARN, 3,
                     detail=f"{top} de {len(doc.bullets)} marcadores começam com “{word}”.",
                     fix="Varie o verbo de abertura: a repetição faz entregas diferentes parecerem a mesma.")
    return Check("repeticao", "conteudo", label, OK, 3)


def _check_language(doc: Doc) -> Check:
    """Currículo em inglês com texto em português (e o contrário) é o erro mais comum do editor."""
    label = "Texto no idioma do currículo"
    prose = " ".join([doc.summary, *doc.bullets]) if doc.structured else doc.text
    tokens = [_fold(w) for w in _words(prose)]
    pt = sum(t in _STOP_PT for t in tokens)
    en = sum(t in _STOP_EN for t in tokens)
    if pt + en < 8:
        return Check("idioma", "conteudo", label, SKIP, 6)
    wrong, right = (pt, en) if doc.lang == "en" else (en, pt)
    if wrong > right:
        other, own = ("português", "inglês") if doc.lang == "en" else ("inglês", "português")
        return Check("idioma", "conteudo", label, FAIL, 6,
                     detail=f"O currículo está marcado como {own}, mas o texto está em {other}.",
                     fix=f"Traduza resumo e marcadores para {own}, ou troque o idioma do currículo. ATS casa palavra-chave no idioma do anúncio.")
    return Check("idioma", "conteudo", label, OK, 6)


# -------------------------------------------------------------------- vaga


def job_skills(job: dict[str, Any] | None) -> list[str]:
    if not job:
        return []
    tags = job.get("tags")
    if isinstance(tags, str):
        tags = db.loads(tags, [])
    text = f"{job.get('title', '')} {' '.join(map(str, tags or []))} {job.get('description', '')}"
    return skills.extract(text)


def _check_job(doc: Doc, job: dict[str, Any], lang: str) -> tuple[list[Check], dict[str, list[str]]]:
    wanted = job_skills(job)
    present = set(doc.skills) | set(skills.extract(doc.text))
    matched = [s for s in wanted if s in present]
    missing = [s for s in wanted if s not in present]
    checks: list[Check] = []

    def names(items: list[str], limit: int = 6) -> str:
        return _join([skills.display(s, lang) for s in items], limit)

    if wanted:
        share = len(matched) / len(wanted)
        status = OK if share >= 0.7 else WARN if share >= 0.4 else FAIL
        checks.append(Check(
            "cobertura", "vaga", "Termos técnicos da vaga no currículo", status, 16,
            detail=f"{len(matched)} de {len(wanted)} ({round(share * 100)}%)."
                   + (f" Ausentes: {names(missing)}." if missing else ""),
            fix=("" if status == OK else
                 "Dos ausentes, inclua só o que você já usou — e diga onde, num marcador. "
                 "O que você não sabe não entra: vira pergunta de entrevista. Se o termo se repete nas suas vagas, leve para o Roadmap."),
        ))

        prose = _fold(" ".join([doc.summary, *doc.bullets])) if doc.structured else ""
        if doc.structured and matched:
            in_prose = set(skills.extract(prose))
            listed_only = [s for s in matched if s not in in_prose]
            if len(listed_only) > len(matched) / 2:
                checks.append(Check(
                    "contexto", "vaga", "Termos da vaga usados em contexto", WARN, 6,
                    detail=f"Só aparecem na lista de competências: {names(listed_only)}.",
                    fix="ATS moderno pesa o termo dentro de uma frase. Cite a tecnologia no marcador do projeto em que você a usou.",
                ))
            else:
                checks.append(Check("contexto", "vaga", "Termos da vaga usados em contexto", OK, 6,
                                    detail="A maioria aparece em resumo ou marcador, não só na lista."))

    title = [w for w in (_fold(t) for t in _words(str(job.get("title") or "")))
             if w not in _TITLE_NOISE and len(w) > 1]
    if title:
        where = _fold(doc.headline + " " + doc.summary) if doc.structured else _fold(doc.text[:600])
        hit = [w for w in title if re.search(rf"(?<![a-z0-9]){re.escape(w)}(?![a-z0-9])", where)]
        ok = len(hit) >= max(1, len(title) // 2)
        checks.append(Check(
            "titulo", "vaga", "Cargo da vaga no cabeçalho", OK if ok else WARN, 8,
            detail="" if ok else f"O anúncio chama a vaga de “{job.get('title')}”; o topo do currículo não usa esses termos.",
            fix="" if ok else "Se o cargo descreve o que você faz, use a mesma nomenclatura do anúncio em “Cargo pretendido”. Recrutador busca pelo título.",
        ))
    return checks, {"matched": matched, "missing": missing}


# ----------------------------------------------------------------- resultado


def grade(score: int) -> tuple[str, str]:
    for floor, key, label in GRADES:
        if score >= floor:
            return key, label
    return GRADES[-1][1], GRADES[-1][2]


# Checagens que passam por ausência ("nenhum clichê encontrado"). Num currículo
# quase vazio elas dariam ponto de graça, então só contam quando há texto.
_PASS_BY_ABSENCE = {"layout", "caracteres", "cliches", "pessoa", "pendencias", "repeticao"}
_MIN_WORDS = 30


def _report(doc: Doc, checks: list[Check], keywords: dict[str, list[str]]) -> dict[str, Any]:
    if doc.words < _MIN_WORDS:
        for item in checks:
            if item.key in _PASS_BY_ABSENCE and item.status == OK:
                item.status = SKIP
    categories = []
    total_weight = 0
    total_points = 0.0
    for key, label, weight in CATEGORIES:
        scored = [c for c in checks if c.category == key and c.status != SKIP]
        if not scored:
            continue
        inner = sum(c.weight for c in scored)
        value = sum(c.weight * _VALUE[c.status] for c in scored) / inner
        categories.append({
            "key": key, "label": label, "weight": weight, "score": round(value * 100),
            "checks": [c.as_dict() for c in scored],
        })
        total_weight += weight
        total_points += weight * value

    score = round(100 * total_points / total_weight) if total_weight else 0
    blocked = [c.label for c in checks if c.key in BLOCKERS and c.status == FAIL]
    if blocked:
        score = min(score, BLOCKED_CAP)
    key, label = grade(score)

    # o que mais devolve ponto vem primeiro; empate resolve pela ordem das checagens
    weights = {cat["key"]: cat["weight"] / sum(c["weight"] for c in cat["checks"]) for cat in categories}
    pending = [
        (weights[c.category] * c.weight * (1 - _VALUE[c.status]), index, c)
        for index, c in enumerate(checks)
        if c.status in (WARN, FAIL) and c.fix
    ]
    # primeiro o que trava a nota, depois o que mais devolve ponto
    pending.sort(key=lambda item: (not (item[2].key in BLOCKERS and item[2].status == FAIL), -item[0], item[1]))
    fixes = [
        {"key": c.key, "label": c.label, "status": c.status, "detail": c.detail, "fix": c.fix,
         "gain": max(1, round(100 * lost / total_weight)),
         "blocker": c.key in BLOCKERS and c.status == FAIL}
        for lost, _, c in pending
    ]
    return {
        "score": score, "grade": key, "label": label, "categories": categories, "fixes": fixes,
        "blocked": blocked, "cap": BLOCKED_CAP,
        "keywords": keywords,
        "stats": {"words": doc.words, "bullets": len(doc.bullets), "skills": len(doc.skills)},
        "structured": doc.structured,
    }


def check(resume: dict[str, Any], *, lang: str = "pt", layout: str = "uma-coluna",
          template_label: str = "", job: dict[str, Any] | None = None) -> dict[str, Any]:
    """Nota e sugestões para um currículo montado no editor."""
    doc = _doc_from_resume(resume or {}, lang, layout, template_label)
    checks = [
        _check_layout(doc), _check_characters(doc), _check_dates(doc), _check_links(doc),
        _check_name(doc), _check_email(doc), _check_phone(doc), _check_city(doc), *_check_profiles(doc),
        _check_summary(doc), *_check_core_sections(doc), _check_skill_count(doc),
        _check_length(doc), _check_placeholder(doc),
        _check_bullet_count(doc), _check_action_verbs(doc), _check_numbers(doc),
        _check_bullet_length(doc), _check_cliches(doc), _check_first_person(doc),
        _check_repetition(doc), _check_language(doc),
    ]
    keywords: dict[str, list[str]] = {"matched": [], "missing": []}
    if job:
        extra, keywords = _check_job(doc, job, lang)
        checks += extra
    return _report(doc, checks, keywords)


def check_text(text: str, *, lang: str = "pt", job: dict[str, Any] | None = None) -> dict[str, Any]:
    """Nota e sugestões para um PDF enviado, a partir do texto que saiu dele."""
    doc = _doc_from_text(text, lang)
    checks = [_check_text_layer(doc)]
    if len(doc.text.strip()) >= 80:
        # sem texto não há o que medir: o resto viraria uma lista de falsos alarmes
        checks += [
            _check_headings(doc), _check_characters(doc), _check_dates(doc),
            _check_email(doc), _check_phone(doc), *_check_profiles(doc),
            _check_skill_count(doc), _check_length(doc),
            _check_bullet_count(doc), _check_action_verbs(doc), _check_numbers(doc),
            _check_bullet_length(doc), _check_cliches(doc), _check_first_person(doc),
            _check_repetition(doc), _check_language(doc),
        ]
    keywords: dict[str, list[str]] = {"matched": [], "missing": []}
    if job and len(doc.text.strip()) >= 80:
        extra, keywords = _check_job(doc, job, lang)
        checks += extra
    return _report(doc, checks, keywords)
