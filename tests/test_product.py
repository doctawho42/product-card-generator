import codecs
import json

import pytest

from card_generator.product import InputError, parse_product, parse_product_json

DM02 = {
    "name": "Манометр показывающий DM 02",
    "manufacturer": "Манотомь",
    "specs": {
        "диапазон измерений": "0–1,6 МПа",
        "класс точности": "1,5",
        "присоединение": "G1/2",
        "диаметр корпуса": "100 мм",
    },
    "description": "Прибор предназначен для измерения избыточного давления.",
}


def test_complete_product_is_read_as_is():
    product = parse_product(DM02)

    assert product.name == "Манометр показывающий DM 02"
    assert product.manufacturer == "Манотомь"
    assert product.specs == DM02["specs"]
    assert product.description == "Прибор предназначен для измерения избыточного давления."
    assert product.empty_specs == []
    assert product.to_clarify == []


def test_broken_json_reports_where_it_broke():
    with pytest.raises(InputError, match="строке 2"):
        parse_product_json('{"name": "Манометр",\n "specs": }')


def test_file_saved_with_bom_is_read():
    product = parse_product_json(codecs.BOM_UTF8 + json.dumps(DM02, ensure_ascii=False).encode("utf-8"))

    assert product.name == "Манометр показывающий DM 02"


def test_file_in_another_encoding_is_rejected_with_a_hint():
    with pytest.raises(InputError, match="UTF-8"):
        parse_product_json(json.dumps(DM02, ensure_ascii=False).encode("cp1251"))


def test_json_must_be_an_object():
    with pytest.raises(InputError):
        parse_product_json('["Манометр", "Манотомь"]')


@pytest.mark.parametrize("name", [None, "", "   "])
def test_product_without_name_is_rejected(name):
    data = {**DM02, "name": name}
    with pytest.raises(InputError, match="name"):
        parse_product(data)


def test_product_with_nothing_to_describe_is_rejected():
    with pytest.raises(InputError):
        parse_product({"name": "Манометр DM 02", "specs": {}, "description": ""})


def test_description_alone_is_enough():
    product = parse_product({"name": "Манометр DM 02", "description": "Измеряет давление."})

    assert product.specs == {}
    assert any("характеристик" in note for note in product.to_clarify)


def test_missing_manufacturer_is_noted_but_not_fatal():
    data = {key: value for key, value in DM02.items() if key != "manufacturer"}

    product = parse_product(data)

    assert product.manufacturer is None
    assert any("производитель" in note.lower() for note in product.to_clarify)


def test_placeholder_values_count_as_empty():
    data = {**DM02, "specs": {"класс точности": "1,5", "питание": "", "степень защиты": "—", "материал": "н/д"}}

    product = parse_product(data)

    assert product.specs == {"класс точности": "1,5"}
    assert product.empty_specs == ["питание", "степень защиты", "материал"]
    assert sum("питание" in note for note in product.to_clarify) == 1


def test_no_is_a_value_not_a_gap():
    data = {**DM02, "specs": {"взрывозащита": "нет", "подсветка шкалы": "отсутствует"}}

    product = parse_product(data)

    assert product.specs == {"взрывозащита": "нет", "подсветка шкалы": "отсутствует"}
    assert product.empty_specs == []


def test_spec_without_a_name_is_skipped():
    data = {**DM02, "specs": {"": "24 В", "класс точности": "1,5"}}

    product = parse_product(data)

    assert product.specs == {"класс точности": "1,5"}
    assert any("без названия" in note for note in product.to_clarify)


def test_numeric_spec_values_are_kept_as_text():
    data = {**DM02, "specs": {"диаметр корпуса": 100, "класс точности": 1.5}}

    product = parse_product(data)

    assert product.specs == {"диаметр корпуса": "100", "класс точности": "1.5"}


def test_unreadable_spec_value_is_treated_as_empty():
    data = {**DM02, "specs": {"интерфейсы": ["RS-485", "HART"]}}

    product = parse_product(data)

    assert product.empty_specs == ["интерфейсы"]
    assert any("интерфейсы" in note for note in product.to_clarify)


@pytest.mark.parametrize(
    "field, value",
    [("name", 123), ("manufacturer", {"title": "Манотомь"}), ("description", ["текст"]), ("specs", "0–1,6 МПа")],
)
def test_wrong_field_type_is_rejected_with_field_name(field, value):
    data = {**DM02, field: value}
    with pytest.raises(InputError, match=field):
        parse_product(data)


def test_unknown_fields_are_reported():
    product = parse_product({**DM02, "price": 4500})

    assert any("price" in note for note in product.to_clarify)


def test_source_text_contains_every_input_value():
    product = parse_product(DM02)

    text = product.source_text()

    for piece in ["Манометр показывающий DM 02", "Манотомь", "диапазон измерений", "0–1,6 МПа", "G1/2", "избыточного"]:
        assert piece in text
