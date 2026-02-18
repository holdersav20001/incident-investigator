"""OpenRouterLLMProvider — OpenAI-compatible LLM via OpenRouter.

OpenRouter exposes an OpenAI-compatible chat completions endpoint, so we
use the openai SDK pointed at https://openrouter.ai/api/v1.

The JSON schema of the expected response_model is appended to the system
prompt; the raw text is then validated with Pydantic.  Markdown code fences
(```json ... ```) are stripped before validation in case the model wraps its
response.
"""

from __future__ import annotations

import json
import logging
import re
import time
from typing import TypeVar

from pydantic import BaseModel

from investigator.llm.base import LLMProvider

try:
    from openai import OpenAI, RateLimitError
except ImportError as exc:  # pragma: no cover
    raise ImportError(
        "openai package is required for OpenRouterLLMProvider. "
        "Install it with: pip install 'openai>=1.0'"
    ) from exc

log = logging.getLogger(__name__)

# Retry config for 429 rate-limit responses from the free-tier model.
_MAX_RETRIES = 4
_RETRY_BASE_DELAY_S = 15.0   # first wait; doubles each attempt

T = TypeVar("T", bound=BaseModel)

_BASE_URL = "https://openrouter.ai/api/v1"
_DEFAULT_MODEL = "openai/gpt-4o-mini:free"

# Matches optional ```json ... ``` or ``` ... ``` fences
_CODE_FENCE_RE = re.compile(r"```(?:json)?\s*([\s\S]*?)\s*```")


def _extract_json(text: str) -> str:
    """Strip markdown code fences if present, otherwise return text as-is."""
    m = _CODE_FENCE_RE.search(text)
    return m.group(1) if m else text.strip()


class OpenRouterLLMProvider(LLMProvider):
    """Calls OpenRouter's chat completions API and validates against a Pydantic model."""

    def __init__(self, *, api_key: str, model: str = _DEFAULT_MODEL) -> None:
        if not api_key:
            raise ValueError("api_key must be a non-empty string")
        self._client = OpenAI(
            api_key=api_key,
            base_url=_BASE_URL,
        )
        self.model = model

    def complete(
        self,
        *,
        system: str,
        user: str,
        response_model: type[T],
    ) -> T:
        """Call OpenRouter and return a validated Pydantic instance.

        The response_model JSON schema is injected into the system prompt so
        the model knows exactly what structure to return.
        """
        schema = response_model.model_json_schema()
        system_with_schema = (
            f"{system}\n\n"
            f"IMPORTANT: Respond ONLY with a valid JSON object matching this schema:\n"
            f"{json.dumps(schema, indent=2)}\n"
            f"Do not include any explanatory text, markdown, or code fences — "
            f"only the raw JSON object."
        )

        delay = _RETRY_BASE_DELAY_S
        for attempt in range(1, _MAX_RETRIES + 2):  # +2: attempts 1…N+1, last raises
            try:
                response = self._client.chat.completions.create(
                    model=self.model,
                    max_tokens=2048,
                    messages=[
                        {"role": "system", "content": system_with_schema},
                        {"role": "user",   "content": user},
                    ],
                    extra_headers={
                        "HTTP-Referer": "https://github.com/incident-investigator",
                        "X-Title":      "Incident Investigator",
                    },
                )
                break  # success — exit retry loop
            except RateLimitError:
                if attempt > _MAX_RETRIES:
                    raise
                log.warning(
                    "OpenRouter rate limit (attempt %d/%d) — waiting %.0fs before retry",
                    attempt, _MAX_RETRIES, delay,
                )
                time.sleep(delay)
                delay *= 2  # exponential backoff

        raw: str = response.choices[0].message.content or ""
        return response_model.model_validate_json(_extract_json(raw))
