"""Kimi (Moonshot AI) LLM client.

Kimi exposes an OpenAI-compatible API, so we use the official `openai` SDK and
just point it at Kimi's base URL. Everything in the app that talks to the model
goes through this one class, so prompts, model choice, and error handling live
in a single place.

This client is deliberately "dumb": it only does plumbing —
  - chat():      messages in, text out
  - chat_json(): messages in, parsed JSON dict out (for structured answers)
  - ping():      cheap connectivity/auth check
The pipeline-specific prompts (propose a statistical plan, write a script,
write the Results section) live in their own service files and *use* this client.

Design note: the client never executes anything. It only produces text.

Docs: https://platform.moonshot.ai/docs/guide/migrating-from-openai-to-kimi
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


class KimiClient:
    def __init__(
        self,
        api_key: str | None = None,
        base_url: str | None = None,
        model: str | None = None,
    ):
        self.api_key = api_key or settings.moonshot_api_key
        self.base_url = base_url or settings.kimi_base_url
        self.model = model or settings.kimi_model

        if not self.api_key:
            # Fail loudly at construction rather than deep inside a request.
            raise LLMError(
                "MOONSHOT_API_KEY is not set. Add it to your .env file."
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
        """Send messages to Kimi and return the reply text.

        `temperature` is optional. Kimi's range is [0, 1] (unlike OpenAI's [0, 2]).
        For k2.x models Kimi has fixed temperature rules, so we only pass it when
        explicitly given.
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
            raise LLMError(f"Kimi request failed: {exc}") from exc

        content = completion.choices[0].message.content
        if not content:
            raise LLMError("Kimi returned an empty response.")
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
                f"Expected JSON from Kimi but could not parse it: {exc}\n"
                f"---\n{raw}\n---"
            ) from exc

    def ping(self) -> bool:
        """Cheap round-trip to confirm the key and endpoint work."""
        reply = self.chat(
            [{"role": "user", "content": "Reply with the single word: pong"}]
        )
        return "pong" in reply.lower()


def _strip_code_fence(text: str) -> str:
    """Remove a surrounding ```json ... ``` (or plain ```) fence if present."""
    t = text.strip()
    if t.startswith("```"):
        # drop the first line (``` or ```json) and a trailing ```
        t = t.split("\n", 1)[1] if "\n" in t else t
        if t.rstrip().endswith("```"):
            t = t.rstrip()[:-3]
    return t.strip()
