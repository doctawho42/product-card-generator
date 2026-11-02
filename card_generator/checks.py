"""Checks of the model's answer that code does better than the model.

Models can't count characters, and they like to "help" with values the supplier
never gave: IP65, a temperature range, a GOST number. Most such inventions
contain a number, so every number in the published text must occur in the input.
That misses a number which happens to be in the input for another reason ("2"
from "G1/2") and numbers written in words, so the usual suspects (warranty,
GOST, certificates, verification, explosion protection, food production,
aggressive media) are also checked by word.
"""

import re

from .card import DESCRIPTION_MAX, DESCRIPTION_MIN, QUERIES_MAX, QUERIES_MIN, TITLE_MAX, Draft
from .product import Product

NUMBER = re.compile(r"\d+(?:[.,]\d+)?")

# Advertising words that tell an engineer nothing. Matched by the start of a word,
# so "надёжный", "надежно" and "надёжность" all count.
FLUFF = ("уникальн", "инновацион", "идеальн", "лучш", "надежн", "незаменим", "превосходн", "высококачествен")

# Claims a model adds "because such devices usually have it", including the uses the prompt
# forbids to promise (food production, aggressive media). Fine only if the input mentions them too.
CLAIMS = ("гарант", "гост", "сертифик", "поверк", "госреестр", "взрыв", "пищев", "агрессивн")


def find_problems(draft: Draft, product: Product) -> list[str]:
    """What is wrong with the draft, worded for both the model and the content manager."""
    problems = []

    title_length = len(draft.seo_title)
    if title_length > TITLE_MAX:
        problems.append(f"SEO-заголовок длиннее {TITLE_MAX} символов (сейчас {title_length})")

    # Aim 100 characters inside the range, otherwise the model lands right on the edge again.
    # Rounded to tens: "520 символов" reads right, "523 символов" doesn't.
    description_length = len(draft.seo_description)
    if description_length < DESCRIPTION_MIN:
        missing = round(DESCRIPTION_MIN + 100 - description_length, -1)
        problems.append(
            f"SEO-описание короче {DESCRIPTION_MIN} символов (сейчас {description_length}): сохраните написанное "
            f"и допишите ещё примерно {missing} символов — по предложению о каждой характеристике и о том, где применяется прибор"
        )
    elif description_length > DESCRIPTION_MAX:
        extra = round(description_length - DESCRIPTION_MAX + 100, -1)
        problems.append(
            f"SEO-описание длиннее {DESCRIPTION_MAX} символов (сейчас {description_length}): "
            f"сократите примерно на {extra} символов"
        )

    query_count = len(draft.search_queries)
    if not QUERIES_MIN <= query_count <= QUERIES_MAX:
        problems.append(f"Поисковых запросов должно быть от {QUERIES_MIN} до {QUERIES_MAX} (сейчас {query_count})")

    source = product.source_text()
    for section, text in draft.texts().items():
        numbers = unknown_numbers(text, source)
        if numbers:
            problems.append(f"В разделе «{section}» есть значения, которых нет во входных данных: {', '.join(numbers)}")
        claims = unsupported_claims(text, source)
        if claims:
            problems.append(f"В разделе «{section}» упомянуто то, чего нет во входных данных: {', '.join(claims)}")
        fluff = fluff_words(text)
        if fluff:
            problems.append(f"В разделе «{section}» есть рекламные слова без фактов: {', '.join(fluff)}")

    return problems


def unknown_numbers(text: str, source: str) -> list[str]:
    """Numbers from `text` that never occur in `source`, in order of appearance."""
    known = {_as_float(number) for number in NUMBER.findall(source)}
    unknown = []
    for number in NUMBER.findall(text):
        if _as_float(number) not in known and number not in unknown:
            unknown.append(number)
    return unknown


def unsupported_claims(text: str, source: str) -> list[str]:
    source = _normalize(source)
    found = []
    for word in dict.fromkeys(re.findall(r"\w+", _normalize(text))):
        stem = next((stem for stem in CLAIMS if word.startswith(stem)), None)
        if stem and stem not in source:
            found.append(word)
    return found


def fluff_words(text: str) -> list[str]:
    words = re.findall(r"\w+", _normalize(text))
    return [word for word in dict.fromkeys(words) if word.startswith(FLUFF)]


def appears_in(fragment: str, source: str) -> bool:
    """Whether `fragment` is written in `source` word for word, ignoring case, spacing, dash and quote styles."""
    fragment = _normalize(fragment)
    return bool(fragment) and re.search(rf"(?<!\w){re.escape(fragment)}(?!\w)", _normalize(source)) is not None


def _as_float(number: str) -> float:
    return float(number.replace(",", "."))


def _normalize(text: str) -> str:
    text = text.lower().replace("ё", "е")
    text = re.sub(r"[‐‑‒–—−]", "-", text)
    text = re.sub(r"[«»„“”\"']", "", text)
    return " ".join(text.split())
