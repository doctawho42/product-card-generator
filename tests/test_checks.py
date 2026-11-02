import pytest

from card_generator.card import Commercial, Draft
from card_generator.checks import appears_in, find_problems, fluff_words, unknown_numbers, unsupported_claims
from card_generator.product import parse_product

PRODUCT = parse_product({
    "name": "Манометр показывающий DM 02",
    "manufacturer": "Манотомь",
    "specs": {"диапазон измерений": "0–1,6 МПа", "класс точности": "1,5", "присоединение": "G1/2", "диаметр корпуса": "100 мм"},
    "description": "Прибор предназначен для измерения избыточного давления.",
})


def make_draft(**changes) -> Draft:
    draft = Draft(
        seo_title="Манометр DM 02 Манотомь 0–1,6 МПа, G1/2",
        seo_description="Текст описания. " * 60,
        search_queries=["манометр dm 02", "манометр 1,6 мпа g1/2", "манометр 100 мм"],
        commercial=Commercial(audience=["Службы КИПиА"], tasks=["Контроль давления в трубопроводе"]),
    )
    return draft.model_copy(update=changes)


@pytest.mark.parametrize(
    "text, source, expected",
    [
        ("до 1,6 МПа", "0–1,6 МПа", []),
        ("до 1.6 МПа", "0–1,6 МПа", []),
        ("Манометр DM 02, резьба G1/2", "DM 02, G1/2", []),
        ("корпус IP65, гарантия 3 года", "0–1,6 МПа", ["65", "3"]),
        ("5 лет, а потом ещё 5 лет", "0–1,6 МПа", ["5"]),
    ],
)
def test_unknown_numbers(text, source, expected):
    assert unknown_numbers(text, source) == expected


@pytest.mark.parametrize(
    "fragment, expected",
    [
        ("корпус из нержавеющей стали", True),
        ("Корпус  из нержавеющей стали", True),
        ("диапазон 0-1,6 МПа", True),
        ("корпус из латуни", False),
        ("", False),
    ],
)
def test_appears_in(fragment, expected):
    source = "Диапазон 0–1,6 МПа. Корпус из нержавеющей стали, класс 1,5."
    assert appears_in(fragment, source) is expected


@pytest.mark.parametrize(
    "text, expected",
    [
        ("Прибор идеально подходит и надёжно работает, надёжно!", ["идеально", "надежно"]),
        ("Уникальный манометр, лучший в классе", ["уникальный", "лучший"]),
        ("Класс точности 1,5, корпус 100 мм", []),
    ],
)
def test_fluff_words(text, expected):
    assert fluff_words(text) == expected


@pytest.mark.parametrize(
    "text, source, expected",
    [
        ("Соответствует ГОСТ, гарантия два года.", "Манометр DM 02", ["гост", "гарантия"]),
        ("Соответствует ГОСТ 2405-88.", "Изготовлен по ГОСТ 2405-88", []),
        ("Прибор внесён в Госреестр СИ, поверка не требуется.", "Манометр DM 02", ["госреестр", "поверка"]),
        ("Подходит для пищевой промышленности и агрессивных сред.", "Манометр DM 02", ["пищевой", "агрессивных"]),
        ("Измеряет давление неагрессивных сред.", "Для неагрессивных жидкостей и газов", []),
        ("Класс точности 1,5, корпус 100 мм", "Манометр DM 02", []),
    ],
)
def test_unsupported_claims(text, source, expected):
    assert unsupported_claims(text, source) == expected


def test_claim_missing_from_input_is_a_problem():
    draft = make_draft(seo_description="Текст описания. " * 60 + "Прибор выпускается во взрывозащищённом исполнении.")

    problems = find_problems(draft, PRODUCT)

    assert len(problems) == 1
    assert "взрывозащищенном" in problems[0]


def test_advertising_words_are_a_problem():
    draft = make_draft(commercial=Commercial(audience=["Котельные"], tasks=["Надежный контроль давления"]))

    problems = find_problems(draft, PRODUCT)

    assert len(problems) == 1
    assert "надежный" in problems[0]


def test_good_draft_has_no_problems():
    assert find_problems(make_draft(), PRODUCT) == []


@pytest.mark.parametrize("length, ok", [(70, True), (71, False)])
def test_title_length_limit(length, ok):
    draft = make_draft(seo_title="М" * length)
    assert (find_problems(draft, PRODUCT) == []) is ok


@pytest.mark.parametrize("length, ok", [(799, False), (800, True), (1200, True), (1201, False)])
def test_description_length_limits(length, ok):
    draft = make_draft(seo_description="а" * length)
    assert (find_problems(draft, PRODUCT) == []) is ok


def test_short_description_problem_says_how_much_to_add():
    problems = find_problems(make_draft(seo_description="а" * 640), PRODUCT)

    assert len(problems) == 1
    assert "640" in problems[0]
    assert "260 символов" in problems[0]
    assert "характеристик" in problems[0]


@pytest.mark.parametrize("count, ok", [(2, False), (3, True), (5, True), (6, False)])
def test_number_of_search_queries(count, ok):
    draft = make_draft(search_queries=["манометр"] * count)
    assert (find_problems(draft, PRODUCT) == []) is ok


def test_invented_number_in_description_is_a_problem():
    draft = make_draft(seo_description="Текст описания. " * 60 + "Степень защиты IP65.")

    problems = find_problems(draft, PRODUCT)

    assert len(problems) == 1
    assert "65" in problems[0]


def test_invented_number_in_manager_block_is_a_problem():
    draft = make_draft(commercial=Commercial(audience=["Котельные"], tasks=["Работа до 250 °C"]))

    problems = find_problems(draft, PRODUCT)

    assert len(problems) == 1
    assert "250" in problems[0]
