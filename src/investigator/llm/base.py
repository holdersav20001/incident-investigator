"""LLM provider abstraction.

All LLM calls go through this interface so CI can swap in a mock and
production can plug in Anthropic, OpenAI, or any other provider without
touching business logic.
"""

from abc import ABC, abstractmethod
from typing import TypeVar

from pydantic import BaseModel

T = TypeVar("T", bound=BaseModel)


class LLMProvider(ABC):
    @abstractmethod
    def complete(
        self,
        *,
        system: str,
        user: str,
        response_model: type[T],
    ) -> T:
        """Call the LLM and return validated structured output.

        The implementation must:
        - Pass `system` as the system prompt
        - Pass `user` as the human turn
        - Validate the response against `response_model`
        - Raise on validation failure (never return partial/invalid data)
        """
