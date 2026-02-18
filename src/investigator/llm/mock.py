"""MockLLMProvider — deterministic stub for tests and CI.

Configure with a dict mapping response_model type → scripted instance.
Every call is logged in `self.calls` for assertion in tests.
"""

from typing import Any, TypeVar

from pydantic import BaseModel

from investigator.llm.base import LLMProvider

T = TypeVar("T", bound=BaseModel)


class MockLLMProvider(LLMProvider):
    def __init__(self, responses: dict[type, BaseModel]) -> None:
        # response_model_type → scripted return value
        self._responses = responses
        self.calls: list[dict[str, Any]] = []

    def complete(
        self,
        *,
        system: str,
        user: str,
        response_model: type[T],
    ) -> T:
        self.calls.append(
            {"system": system, "user": user, "response_model": response_model}
        )
        # KeyError is intentional — misconfigured mock should fail loudly
        return self._responses[response_model]  # type: ignore[return-value]
