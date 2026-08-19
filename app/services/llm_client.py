"""LLM client (any OpenAI-compatible provider).

Works with Google Gemini, Groq, OpenRouter, Ollama (local), Kimi/Moonshot, etc.
— they all speak the OpenAI Chat Completions API, so we use the official `openai`
SDK and point it at the provider's base URL. Switching providers is purely config
(llm_base_url / llm_model / llm_api_key); no code changes here.

Everything in the app that talks to the model goes through this one class, so
prompts, model choice, and error handling live in a single place.

This client is deliberately "dumb": it only does plumbing —
  - chat():      messages in, text out
  - chat_json(): messages in, parsed JSON dict out (for structured answers)
  - ping():      cheap connectivity/auth check
The pipeline-specific prompts (propose a statistical plan, write a script,
write the Results section) live in their own service files and *use* this client.

Design note: the client never executes anything. It only produces text.
"""

from __future__ import annotations

import json
from typing import Any

from openai import OpenAI

from app.config import settings

# A message is the OpenAI-style dict: {"role": "user"|"system"|"assistant", "content": "..."}
Message = dict[str, str]


class LLMError(RuntimeError):
    """Raised when the model call fails or returns unusable output."""


class LLMClient:
    def __init__(
        self,
        api_key: str | None = None,
        base_url: str | None = None,
        model: str | None = None,
    ):
        self.api_key = api_key or settings.llm_api_key
        self.base_url = base_url or settings.llm_base_url
        self.model = model or settings.llm_model

        if not self.api_key:
            # Fail loudly at construction rather than deep inside a request.
            raise LLMError(
                "LLM_API_KEY is not set. Add it to your .env file."
            )

        self._client = OpenAI(api_key=self.api_key, base_url=self.base_url)

    # ------------------------------------------------------------------ #
    # Core calls
    # ------------------------------------------------------------------ #
    def chat(
        self,
        messages: list[Message],
        *,
        model: str | None = None,
        temperature: float | None = None,
        max_tokens: int | None = None,
    ) -> str:
        """Send messages to the model and return the reply text.

        `temperature` is optional and only passed when explicitly given — some
        providers/models restrict its range or fix it, so we don't force a value.
        """
        kwargs: dict[str, Any] = {
            "model": model or self.model,
            "messages": messages,
        }
        if temperature is not None:
            kwargs["temperature"] = temperature
        if max_tokens is not None:
            kwargs["max_tokens"] = max_tokens

        try:
            completion = self._client.chat.completions.create(**kwargs)
        except Exception as exc:  # noqa: BLE001 - surface any SDK/HTTP error uniformly
            raise LLMError(f"LLM request failed: {exc}") from exc

        content = completion.choices[0].message.content
        if not content:
            raise LLMError("The model returned an empty response.")
        return content

    def chat_json(
        self,
        messages: list[Message],
        *,
        model: str | None = None,
        temperature: float | None = None,
        max_tokens: int | None = None,
    ) -> dict[str, Any]:
        """Like chat(), but expects and returns a JSON object.

        The caller's prompt must instruct the model to reply with JSON only.
        We tolerate a ```json ... ``` code fence if the model adds one.
        """
        raw = self.chat(
            messages,
            model=model,
            temperature=temperature,
            max_tokens=max_tokens,
        )
        cleaned = _strip_code_fence(raw)
        try:
            return json.loads(cleaned)
        except json.JSONDecodeError as exc:
            raise LLMError(
                f"Expected JSON from the model but could not parse it: {exc}\n"
                f"---\n{raw}\n---"
            ) from exc

    def ping(self) -> bool:
        """Cheap round-trip to confirm the key and endpoint work."""
        reply = self.chat(
            [{"role": "user", "content": "Reply with the single word: pong"}]
        )
        return "pong" in reply.lower()


# Backward-compatible alias (older imports referenced KimiClient).
KimiClient = LLMClient


def _strip_code_fence(text: str) -> str:
    """Remove a surrounding ```json ... ``` (or plain ```) fence if present."""
    t = text.strip()
    if t.startswith("```"):
        # drop the first line (``` or ```json) and a trailing ```
        t = t.split("\n", 1)[1] if "\n" in t else t
        if t.rstrip().endswith("```"):
            t = t.rstrip()[:-3]
    return t.strip()
