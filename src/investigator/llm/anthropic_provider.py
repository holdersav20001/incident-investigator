"""AnthropicLLMProvider — production LLM integration.

Wraps the Anthropic Messages API to implement LLMProvider.  The JSON schema
of the expected response_model is appended to the system prompt so the model
is instructed to return ONLY valid JSON matching that schema.

Install the dependency:
    pip install anthropic>=0.40
"""

from __future__ import annotations

import json
from typing import TypeVar

from pydantic import BaseModel

from investigator.llm.base import LLMProvider

try:
    from anthropic import Anthropic
except ImportError as exc:  # pragma: no cover
    raise ImportError(
        "anthropic package is required for AnthropicLLMProvider. "
        "Install it with: pip install 'anthropic>=0.40'"
    ) from exc

T = TypeVar("T", bound=BaseModel)

_DEFAULT_MODEL = "claude-haiku-4-5-20251001"


class AnthropicLLMProvider(LLMProvider):
    """Calls the Anthropic Messages API and validates the response against a Pydantic model."""

    def __init__(self, *, api_key: str, model: str = _DEFAULT_MODEL) -> None:
        if not api_key:
            raise ValueError("api_key must be a non-empty string")
        self._client = Anthropic(api_key=api_key)
        self.model = model

    def complete(
        self,
        *,
        system: str,
        user: str,
        response_model: type[T],
    ) -> T:
        """Call the Anthropic API and return a validated Pydantic instance.

        The response_model JSON schema is appended to the system prompt so the
        LLM knows exactly what structure to return.  The raw text is then
        validated with Pydantic — any schema violation raises immediately.
        """
        schema = response_model.model_json_schema()
        system_with_schema = (
            f"{system}\n\n"
            f"IMPORTANT: Respond ONLY with a valid JSON object matching this schema:\n"
            f"{json.dumps(schema, indent=2)}\n"
            f"Do not include explanatory text — only the JSON object."
        )

        message = self._client.messages.create(
            model=self.model,
            max_tokens=1024,
            system=system_with_schema,
            messages=[{"role": "user", "content": user}],
        )

        raw: str = message.content[0].text
        return response_model.model_validate_json(raw)
