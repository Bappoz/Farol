"""Taxonomia de skills e extração a partir de texto livre (descrição de vaga, perfil).

O objetivo não é NLP sofisticado: é reconhecer termos técnicos com apelidos comuns,
de forma determinística e auditável, para alimentar o fit score e o roadmap.
"""

from __future__ import annotations

import re
import unicodedata
from collections import Counter
from typing import Iterable

# canônica -> apelidos aceitos (o próprio nome canônico é sempre incluído)
TAXONOMY: dict[str, list[str]] = {
    # linguagens
    "python": ["python", "py"],
    "javascript": ["javascript", "js", "es6", "ecmascript"],
    "typescript": ["typescript", "ts"],
    "java": ["java"],
    "kotlin": ["kotlin"],
    "c#": ["c#", "csharp", "c sharp", ".net", "dotnet"],
    "go": ["golang", "go lang"],
    "rust": ["rust"],
    "php": ["php"],
    "ruby": ["ruby"],
    "swift": ["swift"],
    "dart": ["dart"],
    "scala": ["scala"],
    "r": ["r language", "linguagem r"],
    "sql": ["sql", "consultas sql"],
    "bash": ["bash", "shell script", "shellscript"],
    # front-end
    "react": ["react", "reactjs", "react.js"],
    "next.js": ["next.js", "nextjs"],
    "vue": ["vue", "vuejs", "vue.js"],
    "nuxt": ["nuxt", "nuxtjs"],
    "svelte": ["svelte", "sveltekit"],
    "angular": ["angular", "angularjs"],
    "html": ["html", "html5"],
    "css": ["css", "css3"],
    "sass": ["sass", "scss"],
    "tailwind": ["tailwind", "tailwindcss"],
    "acessibilidade": ["accessibility", "acessibilidade", "wcag", "a11y"],
    "design system": ["design system", "design systems"],
    "figma": ["figma"],
    # back-end / plataformas
    "node.js": ["node.js", "nodejs", "node"],
    "express": ["express", "expressjs"],
    "nestjs": ["nestjs", "nest.js"],
    "django": ["django"],
    "flask": ["flask"],
    "fastapi": ["fastapi"],
    "spring": ["spring", "spring boot", "springboot"],
    "laravel": ["laravel"],
    "rails": ["rails", "ruby on rails"],
    ".net core": [".net core", "asp.net", "aspnet"],
    "rest": ["rest", "api rest", "restful"],
    "graphql": ["graphql"],
    "grpc": ["grpc"],
    "websocket": ["websocket", "websockets"],
    "microserviços": ["microservices", "microserviços", "microsservicos"],
    "mensageria": ["kafka", "rabbitmq", "sqs", "mensageria", "message queue", "pub/sub"],
    # dados
    "postgresql": ["postgresql", "postgres", "psql"],
    "mysql": ["mysql", "mariadb"],
    "sqlite": ["sqlite"],
    "mongodb": ["mongodb", "mongo"],
    "redis": ["redis"],
    "elasticsearch": ["elasticsearch", "opensearch"],
    "modelagem de dados": ["data modeling", "modelagem de dados", "modelagem relacional"],
    "etl": ["etl", "elt", "pipeline de dados", "data pipeline"],
    "airflow": ["airflow"],
    "dbt": ["dbt"],
    "spark": ["spark", "pyspark"],
    "power bi": ["power bi", "powerbi"],
    "tableau": ["tableau"],
    "looker": ["looker", "looker studio", "data studio"],
    "pandas": ["pandas"],
    "estatística": ["statistics", "estatística", "estatistica"],
    "bigquery": ["bigquery", "big query"],
    "snowflake": ["snowflake"],
    "data warehouse": ["data warehouse", "datawarehouse", "warehouse"],
    # ia / ml
    "machine learning": ["machine learning", "aprendizado de máquina", "ml"],
    "deep learning": ["deep learning", "redes neurais", "neural networks"],
    "pytorch": ["pytorch"],
    "tensorflow": ["tensorflow", "keras"],
    "scikit-learn": ["scikit-learn", "sklearn", "scikit learn"],
    "nlp": ["nlp", "processamento de linguagem natural"],
    "llm": ["llm", "large language model", "genai", "generative ai", "ia generativa"],
    "rag": ["rag", "retrieval augmented"],
    "mlops": ["mlops"],
    # infra / devops
    "docker": ["docker", "containers", "contêineres"],
    "kubernetes": ["kubernetes", "k8s"],
    "aws": ["aws", "amazon web services"],
    "gcp": ["gcp", "google cloud"],
    "azure": ["azure"],
    "terraform": ["terraform", "iac", "infrastructure as code"],
    "ansible": ["ansible"],
    "ci/cd": ["ci/cd", "cicd", "continuous integration", "integração contínua"],
    "github actions": ["github actions"],
    "gitlab ci": ["gitlab ci", "gitlab-ci"],
    "linux": ["linux", "unix"],
    "observabilidade": ["observability", "observabilidade", "prometheus", "grafana", "datadog"],
    "nginx": ["nginx"],
    "serverless": ["serverless", "lambda", "cloud functions"],
    # mobile
    "android": ["android"],
    "ios": ["ios"],
    "react native": ["react native"],
    "flutter": ["flutter"],
    # qualidade
    "testes automatizados": ["testes automatizados", "automated tests", "unit tests", "testes unitários"],
    "jest": ["jest", "vitest"],
    "pytest": ["pytest"],
    "cypress": ["cypress", "playwright", "selenium"],
    "tdd": ["tdd", "test driven"],
    "qa": ["qa", "quality assurance", "garantia de qualidade"],
    # produto / processo
    "git": ["git", "controle de versão", "version control"],
    "scrum": ["scrum", "agile", "ágil", "kanban"],
    "code review": ["code review", "revisão de código"],
    "clean code": ["clean code", "solid", "design patterns", "padrões de projeto"],
    "documentação": ["documentation", "documentação", "documentacao"],
    "ux": ["ux", "user experience", "usabilidade"],
    "produto": ["product discovery", "descoberta de produto", "roadmap de produto"],
    "segurança": ["security", "segurança", "owasp", "appsec", "pentest"],
    "supabase": ["supabase"],
    "firebase": ["firebase"],
    "stripe": ["stripe", "pagamentos", "payments"],
    # idiomas (tratados como skill porque aparecem como requisito)
    "inglês": ["english", "inglês", "ingles", "fluent english", "advanced english"],
    "espanhol": ["spanish", "espanhol"],
}

AREAS: dict[str, str] = {
    "frontend": "Front-end",
    "backend": "Back-end",
    "fullstack": "Full-stack",
    "dados": "Dados / Analytics",
    "ia": "IA / Machine Learning",
    "devops": "DevOps / Cloud",
    "mobile": "Mobile",
    "qa": "QA / Testes",
    "seguranca": "Segurança",
    "design": "Design / UX",
}

SENIORITIES: dict[str, str] = {
    "estagio": "Estágio",
    "junior": "Júnior / primeiro emprego",
    "pleno": "Pleno",
    "senior": "Sênior",
}

# termos que sinalizam vaga de entrada
ENTRY_MARKERS = [
    "junior", "júnior", "jr", "entry level", "entry-level", "trainee", "estágio", "estagio",
    "intern", "internship", "graduate", "no experience", "sem experiência", "iniciante",
    "early career", "associate",
]

# termos que sinalizam vaga acima do nível de entrada
SENIOR_MARKERS = [
    "senior", "sênior", "sr.", "staff engineer", "principal", "tech lead", "team lead",
    "head of", "director", "architect", "arquiteto", "especialista", "expert", "manager",
    "10+ years", "8+ years", "7+ years", "6+ years", "5+ years", "5+ anos", "6+ anos",
]

_SLUG_RE = re.compile(r"[^a-z0-9+#./ ]+")


def normalize(text: str) -> str:
    """Minúsculas, sem acento e sem pontuação ruidosa — base para casar apelidos."""
    text = unicodedata.normalize("NFKD", text or "")
    text = "".join(c for c in text if not unicodedata.combining(c))
    text = text.lower()
    text = re.sub(r"<[^>]+>", " ", text)
    text = _SLUG_RE.sub(" ", text)
    return re.sub(r"\s+", " ", text).strip()


def _alias_patterns() -> list[tuple[str, re.Pattern[str]]]:
    patterns: list[tuple[str, re.Pattern[str]]] = []
    for canonical, aliases in TAXONOMY.items():
        # nomes de uma ou duas letras (r, go) só casam pelos apelidos explícitos:
        # "r" solto casaria com "R$ 4.500" e sujaria a extração
        names = [canonical, *aliases] if len(canonical) > 2 else list(aliases)
        terms = {normalize(a) for a in names if normalize(a)}
        parts = sorted((re.escape(t) for t in terms), key=len, reverse=True)
        # \b não funciona depois de "c#" ou "node.js" normalizados; usamos limites manuais
        pattern = re.compile(r"(?<![a-z0-9])(?:%s)(?![a-z0-9])" % "|".join(parts))
        patterns.append((canonical, pattern))
    return patterns


_PATTERNS = _alias_patterns()


def extract(text: str) -> list[str]:
    """Skills canônicas presentes no texto, na ordem da taxonomia."""
    haystack = normalize(text)
    if not haystack:
        return []
    return [canonical for canonical, pattern in _PATTERNS if pattern.search(haystack)]


def count(texts: Iterable[str]) -> Counter:
    """Frequência de skills em uma coleção de textos (usado no radar de demanda)."""
    counter: Counter = Counter()
    for text in texts:
        counter.update(set(extract(text)))
    return counter


def canonicalize(raw: str) -> str | None:
    """Converte um termo digitado pelo usuário na skill canônica correspondente."""
    found = extract(raw)
    if found:
        return found[0]
    cleaned = normalize(raw)
    return cleaned or None


def parse_skill_list(raw: str) -> list[str]:
    """Lê 'python, sql, docker' → lista canônica sem duplicatas, preservando a ordem."""
    result: list[str] = []
    for chunk in re.split(r"[,;\n]", raw or ""):
        chunk = chunk.strip()
        if not chunk:
            continue
        skill = canonicalize(chunk)
        if skill and skill not in result:
            result.append(skill)
    return result


# Grafia correta para exibição. O que não estiver aqui vira sentença capitalizada.
DISPLAY = {
    "python": "Python", "javascript": "JavaScript", "typescript": "TypeScript", "java": "Java",
    "kotlin": "Kotlin", "c#": "C#", "go": "Go", "rust": "Rust", "php": "PHP", "ruby": "Ruby",
    "swift": "Swift", "dart": "Dart", "scala": "Scala", "r": "R", "sql": "SQL", "bash": "Bash",
    "react": "React", "next.js": "Next.js", "vue": "Vue", "nuxt": "Nuxt", "svelte": "Svelte",
    "angular": "Angular", "html": "HTML", "css": "CSS", "sass": "Sass", "tailwind": "Tailwind",
    "figma": "Figma", "node.js": "Node.js", "express": "Express", "nestjs": "NestJS",
    "django": "Django", "flask": "Flask", "fastapi": "FastAPI", "spring": "Spring",
    "laravel": "Laravel", "rails": "Rails", ".net core": ".NET Core", "rest": "REST",
    "graphql": "GraphQL", "grpc": "gRPC", "websocket": "WebSocket",
    "postgresql": "PostgreSQL", "mysql": "MySQL", "sqlite": "SQLite", "mongodb": "MongoDB",
    "redis": "Redis", "elasticsearch": "Elasticsearch", "etl": "ETL", "airflow": "Airflow",
    "dbt": "dbt", "spark": "Spark", "power bi": "Power BI", "tableau": "Tableau",
    "looker": "Looker", "pandas": "pandas", "bigquery": "BigQuery", "snowflake": "Snowflake",
    "machine learning": "Machine Learning", "deep learning": "Deep Learning", "pytorch": "PyTorch",
    "tensorflow": "TensorFlow", "scikit-learn": "scikit-learn", "nlp": "NLP", "llm": "LLM",
    "rag": "RAG", "mlops": "MLOps", "docker": "Docker", "kubernetes": "Kubernetes", "aws": "AWS",
    "gcp": "GCP", "azure": "Azure", "terraform": "Terraform", "ansible": "Ansible",
    "ci/cd": "CI/CD", "github actions": "GitHub Actions", "gitlab ci": "GitLab CI",
    "linux": "Linux", "nginx": "Nginx", "serverless": "Serverless", "android": "Android",
    "ios": "iOS", "react native": "React Native", "flutter": "Flutter", "jest": "Jest",
    "pytest": "pytest", "cypress": "Cypress", "tdd": "TDD", "qa": "QA", "git": "Git",
    "scrum": "Scrum", "ux": "UX", "supabase": "Supabase", "firebase": "Firebase",
    "stripe": "Stripe", "data warehouse": "Data Warehouse",
}


# Só as canônicas de nome português precisam de tradução; o resto já é termo técnico.
DISPLAY_EN = {
    "acessibilidade": "Accessibility",
    "clean code": "Clean code",
    "code review": "Code review",
    "design system": "Design systems",
    "documentação": "Documentation",
    "espanhol": "Spanish",
    "estatística": "Statistics",
    "inglês": "English",
    "mensageria": "Messaging / queues",
    "microserviços": "Microservices",
    "modelagem de dados": "Data modeling",
    "observabilidade": "Observability",
    "produto": "Product discovery",
    "segurança": "Security",
    "testes automatizados": "Automated testing",
}


def display(skill: str, lang: str = "pt") -> str:
    """Nome apresentável de uma skill canônica, no idioma do currículo."""
    if lang == "en" and skill in DISPLAY_EN:
        return DISPLAY_EN[skill]
    if skill in DISPLAY:
        return DISPLAY[skill]
    return skill[:1].upper() + skill[1:] if skill else skill


def has_marker(text: str, markers: list[str]) -> bool:
    haystack = f" {normalize(text)} "
    return any(f" {normalize(m)} " in haystack for m in markers)
