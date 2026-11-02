import json

import pytest

from card_generator.generator import generate_card
from card_generator.llm import LLMError
from card_generator.product import parse_product
from card_generator.prompts import product_message
from fakes import GOOD_TITLE, SENSOR, FakeLLM, answer

PRODUCT = parse_product(SENSOR)


def rows(card) -> dict[str, str]:
    return {spec.name: spec.value for spec in card.specs}


def test_good_answer_is_accepted_on_first_try():
    llm = FakeLLM(answer())

    card = generate_card(PRODUCT, llm)

    assert len(llm.conversations) == 1
    assert card.seo_title == GOOD_TITLE
    assert card.warnings == []


def test_answer_wrapped_in_a_code_block_is_accepted():
    llm = FakeLLM(f"```json\n{answer()}\n```")

    card = generate_card(PRODUCT, llm)

    assert len(llm.conversations) == 1
    assert card.seo_title == GOOD_TITLE


def test_problems_are_sent_back_to_the_model():
    too_long = answer(seo_title="Преобразователь давления ПД-И " * 3)
    llm = FakeLLM(too_long, answer())

    card = generate_card(PRODUCT, llm)

    retry = llm.conversations[1]
    assert retry[-2] == {"role": "assistant", "content": too_long}
    assert "SEO-заголовок" in retry[-1]["content"]
    assert card.seo_title == GOOD_TITLE
    assert card.warnings == []


def test_fix_may_contain_only_the_changed_fields():
    first = answer(seo_title="Преобразователь давления ПД-И " * 3, search_queries=["пд-и", "датчик пд-и", "пд-и купить"])
    llm = FakeLLM(first, json.dumps({"seo_title": GOOD_TITLE}, ensure_ascii=False))

    card = generate_card(PRODUCT, llm)

    assert card.seo_title == GOOD_TITLE
    assert card.search_queries == ["пд-и", "датчик пд-и", "пд-и купить"]
    assert card.warnings == []


def test_missing_fields_can_be_sent_in_the_next_round():
    without_commercial = json.loads(answer())
    commercial = without_commercial.pop("commercial")
    llm = FakeLLM(json.dumps(without_commercial, ensure_ascii=False), json.dumps({"commercial": commercial}))

    card = generate_card(PRODUCT, llm)

    assert card.commercial.audience == ["Службы КИПиА"]
    assert card.warnings == []


def test_empty_title_is_sent_back_for_fixing():
    llm = FakeLLM(answer(seo_title=""), answer())

    card = generate_card(PRODUCT, llm)

    assert len(llm.conversations) == 2
    assert card.seo_title == GOOD_TITLE


def test_broken_json_is_sent_back_to_the_model():
    llm = FakeLLM("Вот карточка: {", answer())

    card = generate_card(PRODUCT, llm)

    assert len(llm.conversations) == 2
    assert card.warnings == []


def test_gives_up_after_two_fixes_and_reports_what_is_left():
    short = answer(seo_description="Слишком коротко.")
    llm = FakeLLM(short, short, short, answer())

    card = generate_card(PRODUCT, llm)

    assert len(llm.conversations) == 3
    assert any("SEO-описание" in warning for warning in card.warnings)


def test_no_usable_answer_at_all_is_an_error():
    with pytest.raises(LLMError):
        generate_card(PRODUCT, FakeLLM("не JSON", "не JSON", "не JSON"))


def test_input_specs_are_copied_unchanged():
    card = generate_card(PRODUCT, FakeLLM(answer()))

    sources = {spec.name: (spec.value, spec.source) for spec in card.specs}
    assert sources["Диапазон измерений"] == ("0–1,0 МПа", "input")
    assert sources["Выходной сигнал"] == ("4–20 мА", "input")


def test_missing_manufacturer_and_empty_spec_say_no_data():
    card = generate_card(PRODUCT, FakeLLM(answer()))

    assert rows(card)["Производитель"] == "данных нет"
    assert rows(card)["Питание"] == "данных нет"


def test_spec_from_description_is_added_when_its_value_is_written_there():
    extra = {"name": "Степень защиты", "value": "IP65"}

    card = generate_card(PRODUCT, FakeLLM(answer(extra_specs=[extra])))

    spec = next(spec for spec in card.specs if spec.name == "Степень защиты")
    assert (spec.value, spec.source) == ("IP65", "description")


@pytest.mark.parametrize(
    "extra",
    [
        {"name": "Материал корпуса", "value": "латунь"},
        {"name": "Степень защиты", "value": "IP67"},
    ],
)
def test_spec_value_missing_from_description_is_dropped_with_a_warning(extra):
    card = generate_card(PRODUCT, FakeLLM(answer(extra_specs=[extra])))

    assert extra["name"] not in rows(card)
    assert any(extra["value"] in warning for warning in card.warnings)


def test_spec_from_description_without_a_value_is_ignored():
    extra = {"name": "Питание", "value": "не указано"}

    card = generate_card(PRODUCT, FakeLLM(answer(extra_specs=[extra])))

    assert rows(card)["Питание"] == "данных нет"
    assert card.warnings == []


def test_missing_specs_named_by_the_model_say_no_data():
    card = generate_card(PRODUCT, FakeLLM(answer(missing_specs=["Температура рабочей среды"])))

    assert rows(card)["Температура рабочей среды"] == "данных нет"
    assert any("Температура рабочей среды" in item for item in card.to_clarify)


@pytest.mark.parametrize("name", ["выходной сигнал", "Тип выходного сигнала"])
def test_model_cannot_mark_a_given_spec_as_missing(name):
    card = generate_card(PRODUCT, FakeLLM(answer(missing_specs=[name])))

    assert [spec.value for spec in card.specs if "сигнал" in spec.name.lower()] == ["4–20 мА"]


def test_specs_sharing_a_word_are_still_different_specs():
    card = generate_card(PRODUCT, FakeLLM(answer(missing_specs=["Диапазон рабочих температур"])))

    assert rows(card)["Диапазон рабочих температур"] == "данных нет"
    assert rows(card)["Диапазон измерений"] == "0–1,0 МПа"


def test_one_letter_spec_name_does_not_hide_other_specs():
    product = parse_product({**SENSOR, "specs": {**SENSOR["specs"], "U": "24 В"}})

    card = generate_card(product, FakeLLM(answer(missing_specs=["Температура рабочей среды"])))

    assert rows(card)["Температура рабочей среды"] == "данных нет"


def test_to_clarify_lists_input_gaps_and_model_notes():
    card = generate_card(PRODUCT, FakeLLM(answer(to_clarify=["В описании нет диапазона температур"])))

    text = "\n".join(card.to_clarify)
    assert "производитель" in text.lower()
    assert "питание" in text
    assert "В описании нет диапазона температур" in text


def test_model_notes_that_only_repeat_a_spec_name_are_dropped():
    contradiction = "В характеристиках выходной сигнал 4–20 мА, а в описании 0–5 мА"
    notes = ["температура рабочей среды", "диапазон измерений", contradiction]

    card = generate_card(PRODUCT, FakeLLM(answer(missing_specs=["Температура рабочей среды"], to_clarify=notes)))

    assert contradiction in card.to_clarify
    assert "диапазон измерений" not in card.to_clarify
    assert "температура рабочей среды" not in card.to_clarify
    assert "Нет данных: Температура рабочей среды" in card.to_clarify


def test_title_starts_with_a_capital_letter():
    card = generate_card(PRODUCT, FakeLLM(answer(seo_title=GOOD_TITLE.lower())))

    assert card.seo_title == "П" + GOOD_TITLE.lower()[1:]


def test_markdown_shows_every_section_and_gaps():
    card = generate_card(PRODUCT, FakeLLM(answer(missing_specs=["Температура рабочей среды"])))

    markdown = card.to_markdown()

    for heading in ["SEO-заголовок", "SEO-описание", "Характеристики", "Поисковые запросы", "Для менеджера", "Что уточнить"]:
        assert f"## {heading}" in markdown
    assert "| Питание | данных нет |" in markdown
    assert "| Температура рабочей среды | данных нет |" in markdown


def test_product_message_carries_all_input_data_and_names_the_gaps():
    message = product_message(PRODUCT)

    for piece in ["Преобразователь давления ПД-И", "0–1,0 МПа", "4–20 мА", "степень защиты IP65"]:
        assert piece in message
    assert "производитель" in message
    assert "питание" in message
