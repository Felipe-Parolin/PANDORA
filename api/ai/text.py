"""Normalização de texto em português e minimização de dados pessoais (RNF5)."""
import re
import unicodedata
from abc import ABC, abstractmethod

STOPWORDS = frozenset("""
a o as os um uma uns umas de do da dos das em no na nos nas por para com sem sob sobre ate ao aos
e ou mas que se como quando onde porque pois ja nao sim muito muita mais menos tambem apenas so
foi era ser sao esta estao estava tem ter teve tinha ha isso isto esse essa esses essas este
aquele aquela ele ela eles elas seu sua seus suas meu minha nosso nossa lhe me te nos vos
equipamento equipamentos favor precisa fazer feito feita
""".split())

_TOKEN = re.compile(r"[a-z0-9]+")


def strip_accents(value: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFD", value) if unicodedata.category(c) != "Mn")


def stem(word: str) -> str:
    """Stemmer leve e conservador para português (apenas plurais e gerúndios/particípios)."""
    if len(word) <= 3 or word.isdigit():
        return word
    for suffix, replacement in (("coes", "cao"), ("oes", "ao"), ("aes", "ao"), ("ais", "al"), ("eis", "el"), ("ns", "m")):
        if word.endswith(suffix):
            return word[: -len(suffix)] + replacement
    if word.endswith("s") and not word.endswith("ss"):
        word = word[:-1]
    if len(word) > 4 and word.endswith("am"):  # 3ª pessoa do plural: ligam → liga
        word = word[:-1]
    if len(word) > 6:
        for suffix in ("ando", "endo", "indo", "ados", "adas", "idos", "idas"):
            if word.endswith(suffix):
                return word[: -len(suffix)]
    return word


def tokenize(text: str) -> list[str]:
    folded = strip_accents((text or "").lower())
    return [stem(token) for token in _TOKEN.findall(folded) if len(token) > 1 and token not in STOPWORDS]


def clean_whitespace(text: str) -> str:
    return " ".join((text or "").split()).strip()


def truncate(text: str, limit: int) -> str:
    text = clean_whitespace(text)
    return text if len(text) <= limit else text[: limit - 1].rstrip() + "…"


def neutralize_markup(text: str) -> str:
    """Impede que conteúdo de manuais/OS feche as tags de fonte usadas no prompt."""
    return (text or "").replace("<", "‹").replace(">", "›")


# --- Chain of Responsibility: cada elo remove um tipo de dado pessoal -------------------------


class Redactor(ABC):
    def __init__(self, successor: "Redactor | None" = None):
        self.successor = successor

    def handle(self, text: str) -> str:
        text = self.redact(text)
        return self.successor.handle(text) if self.successor else text

    @abstractmethod
    def redact(self, text: str) -> str: ...


class PatternRedactor(Redactor):
    def __init__(self, pattern: str, placeholder: str, successor=None):
        super().__init__(successor)
        self._pattern = re.compile(pattern, re.IGNORECASE)
        self._placeholder = placeholder

    def redact(self, text):
        return self._pattern.sub(self._placeholder, text)


class NameRedactor(Redactor):
    """Remove nomes de clientes cadastrados (consulta única ao banco por requisição)."""

    def __init__(self, names, successor=None):
        super().__init__(successor)
        names = sorted({clean_whitespace(n) for n in names if n and len(clean_whitespace(n)) >= 4}, key=len, reverse=True)
        self._pattern = re.compile("|".join(re.escape(n) for n in names), re.IGNORECASE) if names else None

    def redact(self, text):
        return self._pattern.sub("[CLIENTE]", text) if self._pattern else text


def build_redactor(customer_names=()):
    chain = NameRedactor(customer_names)
    for pattern, placeholder in (
        (r"\b[\w.+-]+@[\w-]+(?:\.[\w-]+)+\b", "[E-MAIL]"),
        (r"(?:\+?55\s?)?\(?\b\d{2}\)?\s?9?\d{4}-?\d{4}\b", "[TELEFONE]"),
        (r"\b\d{5}-?\d{3}\b", "[CEP]"),
        (r"\b\d{3}\.?\d{3}\.?\d{3}-?\d{2}\b", "[CPF]"),
        (r"\b\d{2}\.?\d{3}\.?\d{3}/?\d{4}-?\d{2}\b", "[CNPJ]"),
    ):
        chain = PatternRedactor(pattern, placeholder, chain)
    return chain  # CNPJ é aplicado primeiro (último elo criado), evitando que CPF corte um CNPJ


def redact(text: str, customer_names=()) -> str:
    return build_redactor(customer_names).handle(text or "")
