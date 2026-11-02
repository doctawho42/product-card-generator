"""Talking to the model through any OpenAI-compatible Chat Completions API.

OpenAI itself, OpenRouter, a local Ollama or LM Studio all speak it:
only the address, the key and the model name change.
"""

import logging
import os

import openai

DEFAULT_TEMPERATURE = 0.3
DEFAULT_TIMEOUT = 120
# A whole card is about 1000–1500 tokens. The cap stops a model that got stuck repeating itself.
DEFAULT_MAX_TOKENS = 2500

log = logging.getLogger(__name__)


class LLMError(Exception):
    """The model can't be reached or didn't answer properly."""


class LLMClient:
    def __init__(
        self,
        base_url: str,
        model: str,
        api_key: str = "",
        temperature: float | None = DEFAULT_TEMPERATURE,
        max_tokens: int | None = DEFAULT_MAX_TOKENS,
        timeout: float = DEFAULT_TIMEOUT,
        max_retries: int = 2,
    ):
        self.base_url = base_url
        self.model = model
        self.temperature = temperature
        self.max_tokens = max_tokens
        self.timeout = timeout
        # A local server doesn't need a key, but the SDK refuses to start without one.
        self._client = openai.OpenAI(
            base_url=base_url, api_key=api_key or "not-needed", timeout=timeout, max_retries=max_retries
        )

    @classmethod
    def from_env(cls) -> "LLMClient":
        model = os.getenv("LLM_MODEL")
        if not model:
            raise LLMError("Не задана модель: укажите LLM_MODEL в файле .env (примеры в .env.example)")
        # An empty LLM_TEMPERATURE or LLM_MAX_TOKENS means "don't send it", an empty LLM_TIMEOUT means the default.
        max_tokens = _number_from_env("LLM_MAX_TOKENS", default=DEFAULT_MAX_TOKENS)
        return cls(
            base_url=os.getenv("LLM_BASE_URL") or "https://api.openai.com/v1",
            model=model,
            api_key=os.getenv("LLM_API_KEY", ""),
            temperature=_number_from_env("LLM_TEMPERATURE", default=DEFAULT_TEMPERATURE),
            max_tokens=int(max_tokens) if max_tokens else None,
            timeout=_number_from_env("LLM_TIMEOUT", default=DEFAULT_TIMEOUT) or DEFAULT_TIMEOUT,
        )

    def complete_json(self, messages: list[dict]) -> str:
        """Sends the conversation and returns the model's answer, which should be a JSON object."""
        options: dict = {"response_format": {"type": "json_object"}}
        # Reasoning models (o-series, gpt-5) take neither a custom temperature nor max_tokens.
        if self.temperature is not None:
            options["temperature"] = self.temperature
        if self.max_tokens is not None:
            options["max_tokens"] = self.max_tokens

        try:
            response = self._client.chat.completions.create(model=self.model, messages=messages, **options)
        except openai.APIError as error:
            raise LLMError(self._explain(error)) from error

        if not response.choices or not response.choices[0].message.content:
            raise LLMError("Модель вернула пустой ответ")
        choice = response.choices[0]
        if choice.finish_reason == "length":
            # The cut-off answer is broken JSON, so the generator will ask the model to try again.
            log.info("Ответ модели оборвался на лимите в %s токенов", self.max_tokens)
        return choice.message.content

    def _explain(self, error: openai.APIError) -> str:
        if isinstance(error, openai.APITimeoutError):
            return f"Модель не ответила за {self.timeout:g} с. Повторите запрос или увеличьте LLM_TIMEOUT"
        if isinstance(error, openai.APIConnectionError):
            return f"Не удалось подключиться к {self.base_url}. Проверьте LLM_BASE_URL и сеть, а если это Ollama, запущена ли она"
        if isinstance(error, openai.AuthenticationError):
            return "Ключ не подошёл (401): проверьте LLM_API_KEY"
        if isinstance(error, openai.PermissionDeniedError):
            return f"Провайдер отказал в доступе (403): {error.message}"
        if isinstance(error, openai.NotFoundError):
            return f"Модель {self.model} не найдена (404). Проверьте LLM_MODEL; для Ollama: ollama pull {self.model}"
        if isinstance(error, openai.RateLimitError):
            return "Превышен лимит запросов или закончились деньги на счёте (429). Подождите и повторите"
        if isinstance(error, openai.APIStatusError):
            return f"Провайдер вернул ошибку {error.status_code}: {error.message}"
        return f"Ошибка API: {error}"


def _number_from_env(name: str, default: float) -> float | None:
    raw = os.getenv(name, str(default)).strip()
    if not raw:
        return None
    try:
        return float(raw)
    except ValueError:
        raise LLMError(f"{name} должно быть числом, а сейчас: {raw}") from None
