"""The card: what the model has to return and what the user gets back."""

from typing import Literal

from pydantic import BaseModel, Field

NO_DATA = "данных нет"

TITLE_MAX = 70
DESCRIPTION_MIN = 800
DESCRIPTION_MAX = 1200
QUERIES_MIN = 3
QUERIES_MAX = 5


class ExtraSpec(BaseModel):
    """A spec the model found in the free-text description."""

    name: str
    value: str


class Commercial(BaseModel):
    audience: list[str] = Field(min_length=1)
    tasks: list[str] = Field(min_length=1)


class Draft(BaseModel):
    """The model's answer, with the same fields as described in the prompt."""

    seo_title: str = Field(min_length=1)
    seo_description: str = Field(min_length=1)
    search_queries: list[str]
    commercial: Commercial
    extra_specs: list[ExtraSpec] = []
    missing_specs: list[str] = []
    to_clarify: list[str] = []

    def texts(self) -> dict[str, str]:
        """The text that goes to the shop page, by card section."""
        return {
            "SEO-заголовок": self.seo_title,
            "SEO-описание": self.seo_description,
            "Поисковые запросы": "\n".join(self.search_queries),
            "Для менеджера": "\n".join(self.commercial.audience + self.commercial.tasks),
        }


class Spec(BaseModel):
    name: str
    value: str
    source: Literal["input", "description", "missing"]


SOURCE_LABELS = {"input": "исходные данные", "description": "из описания", "missing": "—"}


class ProductCard(BaseModel):
    product: str
    seo_title: str
    seo_description: str
    specs: list[Spec]
    search_queries: list[str]
    commercial: Commercial
    to_clarify: list[str]
    warnings: list[str]

    def to_markdown(self) -> str:
        lines = [
            f"# {self.product}",
            "",
            "## SEO-заголовок",
            "",
            self.seo_title,
            "",
            f"_Длина {len(self.seo_title)} (норма до {TITLE_MAX} символов)_",
            "",
            "## SEO-описание",
            "",
            # Markdown needs an empty line between paragraphs, models often put just one line break.
            "\n\n".join(line.strip() for line in self.seo_description.splitlines() if line.strip()),
            "",
            f"_Длина {len(self.seo_description)} (норма {DESCRIPTION_MIN}–{DESCRIPTION_MAX} символов)_",
            "",
            "## Характеристики",
            "",
            "| Характеристика | Значение | Источник |",
            "|---|---|---|",
            *[f"| {_cell(spec.name)} | {_cell(spec.value)} | {SOURCE_LABELS[spec.source]} |" for spec in self.specs],
            "",
            "## Поисковые запросы",
            "",
            *_bullets(self.search_queries),
            "",
            "## Для менеджера",
            "",
            "**Кому подходит**",
            "",
            *_bullets(self.commercial.audience),
            "",
            "**Какие задачи решает**",
            "",
            *_bullets(self.commercial.tasks),
        ]
        if self.to_clarify:
            lines += ["", "## Что уточнить", "", *_bullets(self.to_clarify)]
        if self.warnings:
            lines += ["", "## Проверьте перед публикацией", "", *_bullets(self.warnings)]
        return "\n".join(lines) + "\n"


def _bullets(items: list[str]) -> list[str]:
    return [f"- {item}" for item in items]


def _cell(text: str) -> str:
    return text.replace("|", "\\|").replace("\n", " ")
