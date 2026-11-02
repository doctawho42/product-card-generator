"""Reading the input product and noting what is missing in it."""

import json
from dataclasses import dataclass, field

# What suppliers write instead of a value when they don't know it.
# "нет" is not here: "Взрывозащита: нет" is an answer, not a gap.
PLACEHOLDERS = {
    "", "-", "–", "—", "?", "н/д", "нет данных", "данных нет", "не указано", "не указан", "не указана", "уточнить",
}

KNOWN_FIELDS = {"name", "manufacturer", "specs", "description"}


class InputError(Exception):
    """The input can't be turned into a card at all."""


@dataclass
class Product:
    name: str
    manufacturer: str | None
    specs: dict[str, str]
    description: str | None
    empty_specs: list[str] = field(default_factory=list)
    to_clarify: list[str] = field(default_factory=list)

    def source_text(self) -> str:
        """Everything we know about the product. The card may not claim anything beyond it."""
        lines = [self.name, self.manufacturer or "", self.description or ""]
        lines += [f"{name}: {value}" for name, value in self.specs.items()]
        return "\n".join(lines)


def parse_product_json(raw: str | bytes) -> Product:
    try:
        # Bytes are decoded as UTF-8, with or without the BOM that Windows editors like to add.
        data = json.loads(raw)
    except UnicodeDecodeError:
        raise InputError("Данные не в кодировке UTF-8: пересохраните файл в UTF-8") from None
    except json.JSONDecodeError as error:
        raise InputError(f"Некорректный JSON в строке {error.lineno}, позиция {error.colno} ({error.msg})") from error
    return parse_product(data)


def parse_product(data: object) -> Product:
    if not isinstance(data, dict):
        raise InputError("Ожидается JSON-объект с полями name, manufacturer, specs, description")

    name = _text_field(data, "name")
    if not name:
        raise InputError("Не заполнено название товара (name): без него карточку не собрать")

    manufacturer = _text_field(data, "manufacturer")
    description = _text_field(data, "description")
    specs, empty_specs, spec_notes = _read_specs(data.get("specs"))
    if not specs and not description:
        raise InputError("Нет ни характеристик (specs), ни описания (description): модели не на что опереться")

    to_clarify = []
    if not manufacturer:
        to_clarify.append("Не указан производитель")
    if not specs:
        to_clarify.append("Нет характеристик: всё, что известно о приборе, взято из описания")
    if not description:
        to_clarify.append("Нет описания: текст собран только по характеристикам")
    to_clarify += spec_notes

    unknown = [key for key in data if key not in KNOWN_FIELDS]
    if unknown:
        to_clarify.append("Эти поля сервис не использует: " + ", ".join(unknown))

    return Product(name, manufacturer, specs, description, empty_specs, to_clarify)


def is_blank(value: str) -> bool:
    return value.strip().lower() in PLACEHOLDERS


def _text_field(data: dict, key: str) -> str | None:
    value = data.get(key)
    if value is None:
        return None
    if not isinstance(value, str):
        raise InputError(f"Поле {key} должно быть строкой")
    return None if is_blank(value) else value.strip()


def _read_specs(raw: object) -> tuple[dict[str, str], list[str], list[str]]:
    """Filled specs, names of specs that came without a usable value, and notes about both."""
    if raw is None:
        return {}, [], []
    if not isinstance(raw, dict):
        raise InputError('Поле specs должно быть объектом вида {"характеристика": "значение"}')

    filled, empty, notes = {}, [], []
    for name, value in raw.items():
        name = name.strip()
        if not name:
            notes.append(f"Пропущена характеристика без названия: {value}")
            continue
        if isinstance(value, (int, float)) and not isinstance(value, bool):
            value = str(value)

        if value is None or (isinstance(value, str) and is_blank(value)):
            empty.append(name)
            notes.append(f"Не заполнена характеристика «{name}»")
        elif isinstance(value, str):
            filled[name] = value.strip()
        else:
            empty.append(name)
            notes.append(f"Не удалось прочитать характеристику «{name}»: ожидается строка или число")
    return filled, empty, notes
