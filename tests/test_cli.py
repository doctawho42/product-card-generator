import json

import pytest

from card_generator.__main__ import main
from card_generator.llm import LLMClient
from fakes import SENSOR, FakeLLM, answer


@pytest.fixture
def fake_model(monkeypatch):
    llm = FakeLLM(answer(), answer())
    monkeypatch.setattr(LLMClient, "from_env", classmethod(lambda cls: llm))
    return llm


def write(path, text: str):
    path.write_text(text, encoding="utf-8")
    return str(path)


def test_cards_are_saved_as_markdown_and_json(tmp_path, fake_model):
    product = write(tmp_path / "sensor.json", json.dumps(SENSOR, ensure_ascii=False))

    code = main([product, "--out", str(tmp_path / "out")])

    assert code == 0
    card = json.loads((tmp_path / "out" / "sensor.json").read_text(encoding="utf-8"))
    assert card["product"] == "Преобразователь давления ПД-И"
    assert (tmp_path / "out" / "sensor.md").read_text(encoding="utf-8").startswith("# Преобразователь давления ПД-И")


def test_bad_files_are_reported_and_the_rest_still_processed(tmp_path, fake_model, capsys):
    broken = write(tmp_path / "broken.json", '{"name": "Манометр"')
    cp1251 = tmp_path / "cp1251.json"
    cp1251.write_bytes(json.dumps(SENSOR, ensure_ascii=False).encode("cp1251"))
    good = write(tmp_path / "good.json", json.dumps(SENSOR, ensure_ascii=False))

    folder = tmp_path / "folder.json"
    folder.mkdir()

    code = main([broken, str(cp1251), str(tmp_path / "missing.json"), str(folder), good])

    assert code == 1
    output = capsys.readouterr()
    assert "# Преобразователь давления ПД-И" in output.out
    for name in ["broken.json", "cp1251.json", "missing.json", "folder.json"]:
        assert name in output.err
    assert "Traceback" not in output.err
    assert len(fake_model.conversations) == 1


def test_missing_model_setting_stops_before_any_work(tmp_path, monkeypatch, capsys):
    monkeypatch.delenv("LLM_MODEL", raising=False)
    monkeypatch.setattr("card_generator.__main__.load_dotenv", lambda: None)
    product = write(tmp_path / "sensor.json", json.dumps(SENSOR, ensure_ascii=False))

    code = main([product])

    assert code == 2
    assert "LLM_MODEL" in capsys.readouterr().err
