"""From product data to a card: ask the model, check the answer, send it back for fixes."""

import json
import logging
import re
from typing import Protocol

from pydantic import ValidationError

from .card import NO_DATA, Draft, ProductCard, Spec
from .checks import appears_in, find_problems
from .llm import LLMError
from .product import Product, is_blank
from .prompts import SYSTEM_PROMPT, fix_message, product_message

# Every round is one more request to the model. Two are usually enough to fix the length.
FIX_ROUNDS = 2

log = logging.getLogger(__name__)


class ChatModel(Protocol):
    """All the generator needs from a model. LLMClient is one; tests use a fake."""

    def complete_json(self, messages: list[dict]) -> str: ...


def generate_card(product: Product, llm: ChatModel) -> ProductCard:
    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": product_message(product)},
    ]
    fields: dict = {}
    draft = None
    for _ in range(1 + FIX_ROUNDS):
        answer = llm.complete_json(messages)
        try:
            # When fixing, the model may send back only the fields it changed.
            fields = {**fields, **_json_object(answer)}
            draft = Draft.model_validate(fields)
        except ValueError as error:  # broken JSON or wrong structure, pydantic's error is a ValueError too
            problems = [f"Ответ не подходит под нужную структуру JSON: {_describe(error)}"]
        else:
            problems = find_problems(draft, product)
            if not problems:
                break
        log.info("Замечания к ответу модели: %s", "; ".join(problems))
        messages += [
            {"role": "assistant", "content": answer},
            {"role": "user", "content": fix_message(problems)},
        ]

    if draft is None:
        raise LLMError("Модель так и не вернула ответ в нужном формате")
    # What the last good draft still gets wrong is shown to the content manager, not hidden.
    return assemble_card(product, draft, problems=find_problems(draft, product))


def assemble_card(product: Product, draft: Draft, problems: list[str]) -> ProductCard:
    """Builds the card. Spec values come from the input, never from the model's own words."""
    specs = [
        Spec(name="Производитель", value=product.manufacturer, source="input")
        if product.manufacturer
        else Spec(name="Производитель", value=NO_DATA, source="missing")
    ]
    specs += [Spec(name=_capitalize(name), value=value, source="input") for name, value in product.specs.items()]

    warnings = list(problems)
    for extra in draft.extra_specs:
        if is_blank(extra.value) or _already_listed(specs, extra.name):
            continue
        if appears_in(extra.value, product.description or ""):
            specs.append(Spec(name=_capitalize(extra.name), value=extra.value, source="description"))
        else:
            warnings.append(f"Характеристика «{extra.name}: {extra.value}» не найдена в описании и в карточку не попала")

    to_clarify = list(product.to_clarify)
    for name in product.empty_specs:
        if not _already_listed(specs, name):
            specs.append(Spec(name=_capitalize(name), value=NO_DATA, source="missing"))
    for name in draft.missing_specs:
        if not _already_listed(specs, name):
            specs.append(Spec(name=_capitalize(name), value=NO_DATA, source="missing"))
            to_clarify.append(f"Нет данных: {name}")
    # The model sometimes lists bare spec names here; the table and "Нет данных" lines already cover them.
    to_clarify += [note for note in draft.to_clarify if not _is_spec_name(specs, note)]

    return ProductCard(
        product=product.name,
        seo_title=_capitalize(draft.seo_title),
        seo_description=draft.seo_description,
        specs=specs,
        search_queries=draft.search_queries,
        commercial=draft.commercial,
        to_clarify=to_clarify,
        warnings=warnings,
    )


def _json_object(answer: str) -> dict:
    """The JSON object from the answer, ignoring code fences, "Here is the card:" and the like."""
    start, end = answer.find("{"), answer.rfind("}")
    data = json.loads(answer[start:end + 1] if 0 <= start < end else answer)
    if not isinstance(data, dict):
        raise ValueError("ожидался JSON-объект")
    return data


def _describe(error: ValueError) -> str:
    if isinstance(error, ValidationError):
        return "; ".join(f"{'.'.join(map(str, item['loc']))}: {item['msg']}" for item in error.errors()[:5])
    return str(error)


def _already_listed(specs: list[Spec], name: str) -> bool:
    """Whether the card already has this spec, possibly worded a little differently.

    "Тип выходного сигнала" is the same spec as "Выходной сигнал", but "Диапазон рабочих
    температур" is not the same as "Диапазон измерений" although both start alike.
    """
    words = _stems(name)
    for spec in specs:
        listed = _stems(spec.name)
        # A name like "U" has no stems at all and must not match everything.
        if words and listed and (words <= listed or listed <= words):
            return True
    return False


def _is_spec_name(specs: list[Spec], text: str) -> bool:
    """Whether `text` is nothing more than the name of a spec already in the card."""
    words = _stems(text)
    return bool(words) and any(words <= _stems(spec.name) for spec in specs)


def _stems(name: str) -> set[str]:
    # The first six letters are enough to match "выходной" with "выходного".
    words = re.findall(r"\w+", name.lower().replace("ё", "е"))
    return {word[:6] for word in words if len(word) > 1}


def _capitalize(name: str) -> str:
    return name[:1].upper() + name[1:]
