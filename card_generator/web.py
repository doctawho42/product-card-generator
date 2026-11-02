"""A one-page form for content managers and a JSON endpoint.

Run with: uvicorn card_generator.web:app
"""

from functools import lru_cache
from pathlib import Path
from typing import Any

from dotenv import load_dotenv
from fastapi import FastAPI, Form, Request
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.templating import Jinja2Templates

from .card import DESCRIPTION_MAX, DESCRIPTION_MIN, SOURCE_LABELS, TITLE_MAX
from .generator import generate_card
from .llm import LLMClient, LLMError
from .product import InputError, parse_product, parse_product_json

load_dotenv()

app = FastAPI(title="Черновик карточки товара")
templates = Jinja2Templates(directory=Path(__file__).parent / "templates")
templates.env.globals.update(
    TITLE_MAX=TITLE_MAX, DESCRIPTION_MIN=DESCRIPTION_MIN, DESCRIPTION_MAX=DESCRIPTION_MAX, SOURCE_LABELS=SOURCE_LABELS
)


@lru_cache
def get_llm() -> LLMClient:
    return LLMClient.from_env()


@app.get("/", response_class=HTMLResponse)
def show_form(request: Request):
    return templates.TemplateResponse(request, "index.html", {"form": {}})


# Plain `def` rather than `async def`: FastAPI runs it in a thread pool,
# so waiting for a slow model doesn't block other requests.
@app.post("/", response_class=HTMLResponse)
def submit_form(
    request: Request,
    name: str = Form(""),
    manufacturer: str = Form(""),
    specs: str = Form(""),
    description: str = Form(""),
):
    form = {"name": name, "manufacturer": manufacturer, "specs": specs, "description": description}
    context: dict[str, Any] = {"form": form}
    try:
        product = parse_product({**form, "specs": parse_spec_lines(specs)})
        context["card"] = generate_card(product, get_llm())
    except (InputError, LLMError) as error:
        context["error"] = str(error)
    return templates.TemplateResponse(request, "index.html", context)


@app.post("/api/cards")
async def create_card(request: Request):
    # The raw body goes through the same parser as files, so broken JSON gets the same explanation.
    try:
        product = parse_product_json(await request.body())
    except InputError as error:
        return JSONResponse({"error": str(error)}, status_code=422)
    try:
        card = await run_in_threadpool(generate_card, product, get_llm())
    except LLMError as error:
        return JSONResponse({"error": str(error)}, status_code=502)
    return card.model_dump()


def parse_spec_lines(text: str) -> dict[str, str]:
    """Turns form lines like "Класс точности: 1,5" into a specs dict."""
    specs = {}
    for line in text.splitlines():
        if not line.strip():
            continue
        name, colon, value = line.partition(":")
        if not colon:
            raise InputError(f"Строка «{line.strip()}» не в формате «название: значение»")
        specs[name.strip()] = value.strip()
    return specs
