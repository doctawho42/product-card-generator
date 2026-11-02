import json

GOOD_TITLE = "Преобразователь давления ПД-И 0–1,0 МПа, 4–20 мА"

SENSOR = {
    "name": "Преобразователь давления ПД-И",
    "manufacturer": "",
    "specs": {"диапазон измерений": "0–1,0 МПа", "выходной сигнал": "4–20 мА", "питание": ""},
    "description": "Преобразователь измеряет избыточное давление жидкостей и газов. "
                   "Корпус из нержавеющей стали, степень защиты IP65.",
}


def answer(**changes) -> str:
    """A model answer for SENSOR that passes every check, with some fields replaced."""
    data = {
        "seo_title": GOOD_TITLE,
        "seo_description": "Преобразователь избыточного давления для жидкостей и газов. " * 15,
        "search_queries": ["преобразователь давления пд-и", "датчик давления 4-20 ма", "преобразователь давления 1 мпа"],
        "commercial": {"audience": ["Службы КИПиА"], "tasks": ["Измерение давления в трубопроводах"]},
        "extra_specs": [],
        "missing_specs": [],
        "to_clarify": [],
    }
    data.update(changes)
    return json.dumps(data, ensure_ascii=False)


class FakeLLM:
    """Gives prepared answers in order and keeps every conversation it was sent."""

    def __init__(self, *answers: str):
        self.answers = list(answers)
        self.conversations = []

    def complete_json(self, messages: list[dict]) -> str:
        self.conversations.append(list(messages))
        return self.answers.pop(0)
