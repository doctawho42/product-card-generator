from fastapi.testclient import TestClient

from card_generator import web
from card_generator.llm import LLMError
from fakes import GOOD_TITLE, SENSOR, FakeLLM, answer

client = TestClient(web.app)

FORM = {
    "name": SENSOR["name"],
    "manufacturer": "",
    "specs": "диапазон измерений: 0–1,0 МПа\nвыходной сигнал: 4–20 мА\nпитание:",
    "description": SENSOR["description"],
}


class BrokenLLM:
    def complete_json(self, messages):
        raise LLMError("Не удалось подключиться к http://localhost:11434/v1")


def test_form_page_opens():
    response = client.get("/")

    assert response.status_code == 200
    assert "<form" in response.text


def test_form_lines_become_specs_and_the_card_is_shown(monkeypatch):
    llm = FakeLLM(answer())
    monkeypatch.setattr(web, "get_llm", lambda: llm)

    response = client.post("/", data=FORM)

    assert response.status_code == 200
    assert GOOD_TITLE in response.text
    assert '"выходной сигнал": "4–20 мА"' in llm.conversations[0][1]["content"]
    assert "Питание" in response.text and "данных нет" in response.text


def test_form_shows_why_input_was_rejected():
    response = client.post("/", data={**FORM, "name": ""})

    assert response.status_code == 200
    assert "Не заполнено название товара" in response.text


def test_form_line_without_colon_is_rejected_not_lost(monkeypatch):
    llm = FakeLLM(answer())
    monkeypatch.setattr(web, "get_llm", lambda: llm)

    response = client.post("/", data={**FORM, "specs": "Диапазон измерений 0–1,0 МПа"})

    assert "«Диапазон измерений 0–1,0 МПа»" in response.text
    assert llm.conversations == []


def test_form_shows_model_errors(monkeypatch):
    monkeypatch.setattr(web, "get_llm", lambda: BrokenLLM())

    response = client.post("/", data=FORM)

    assert "Не удалось подключиться" in response.text


def test_api_returns_card_as_json(monkeypatch):
    monkeypatch.setattr(web, "get_llm", lambda: FakeLLM(answer()))

    response = client.post("/api/cards", json=SENSOR)

    assert response.status_code == 200
    assert response.json()["seo_title"] == GOOD_TITLE


def test_api_rejects_bad_input_with_a_reason():
    response = client.post("/api/cards", json={"specs": {"класс точности": "1,5"}})

    assert response.status_code == 422
    assert "name" in response.json()["error"]


def test_api_explains_broken_json_the_same_way():
    broken = '{"name": "Манометр",'.encode()
    response = client.post("/api/cards", content=broken, headers={"Content-Type": "application/json"})

    assert response.status_code == 422
    assert "Некорректный JSON" in response.json()["error"]


def test_api_reports_model_failure_as_bad_gateway(monkeypatch):
    monkeypatch.setattr(web, "get_llm", lambda: BrokenLLM())

    response = client.post("/api/cards", json=SENSOR)

    assert response.status_code == 502
    assert "Не удалось подключиться" in response.json()["error"]
