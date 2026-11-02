"""Messages for the model. The prompt text itself lives in system_prompt.md."""

import json
from pathlib import Path
from string import Template

from .card import DESCRIPTION_MAX, DESCRIPTION_MIN, QUERIES_MAX, QUERIES_MIN, TITLE_MAX
from .product import Product

# The limits come from the same constants the checks use, so the prompt and the checks can't drift apart.
SYSTEM_PROMPT = Template((Path(__file__).parent / "system_prompt.md").read_text(encoding="utf-8")).substitute(
    title_max=TITLE_MAX,
    description_min=DESCRIPTION_MIN,
    description_max=DESCRIPTION_MAX,
    queries_min=QUERIES_MIN,
    queries_max=QUERIES_MAX,
)


def product_message(product: Product) -> str:
    data: dict = {"name": product.name}
    if product.manufacturer:
        data["manufacturer"] = product.manufacturer
    if product.specs:
        data["specs"] = product.specs
    if product.description:
        data["description"] = product.description

    message = "Данные о товаре:\n\n" + json.dumps(data, ensure_ascii=False, indent=2)

    missing = []
    if not product.manufacturer:
        missing.append("производитель")
    if not product.specs:
        missing.append("характеристики")
    if not product.description:
        missing.append("описание")
    missing += [f"характеристика «{name}»" for name in product.empty_specs]
    if missing:
        message += "\n\nНе указано: " + ", ".join(missing) + ". Эти данные не додумывай."
    return message


def fix_message(problems: list[str]) -> str:
    listed = "\n".join(f"- {problem}" for problem in problems)
    return (
        f"В ответе есть проблемы:\n{listed}\n\n"
        "Исправь их и верни JSON-объект с исправленными полями, остальные поля можно не повторять. "
        "Значения, которых нет во входных данных, удали, а не заменяй другими."
    )
