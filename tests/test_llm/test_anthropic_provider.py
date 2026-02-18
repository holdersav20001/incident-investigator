"""Tests for AnthropicLLMProvider.

Uses unittest.mock to avoid real API calls — all Anthropic SDK interactions
are patched at the module boundary.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from investigator.llm.anthropic_provider import AnthropicLLMProvider
from investigator.models.diagnosis import DiagnosisResult


def _make_mock_message(text: str) -> MagicMock:
    """Build a mock Anthropic Message response object."""
    msg = MagicMock()
    block = MagicMock()
    block.text = text
    msg.content = [block]
    return msg


class TestAnthropicProviderInit:
    def test_rejects_empty_api_key(self):
        with pytest.raises(ValueError, match="api_key"):
            AnthropicLLMProvider(api_key="")

    def test_accepts_valid_api_key(self):
        with patch("investigator.llm.anthropic_provider.Anthropic"):
            provider = AnthropicLLMProvider(api_key="sk-ant-test")
        assert provider is not None

    def test_default_model_contains_claude(self):
        with patch("investigator.llm.anthropic_provider.Anthropic"):
            provider = AnthropicLLMProvider(api_key="sk-ant-test")
        assert "claude" in provider.model

    def test_custom_model_accepted(self):
        with patch("investigator.llm.anthropic_provider.Anthropic"):
            provider = AnthropicLLMProvider(api_key="sk-ant-test", model="claude-opus-4-6")
        assert provider.model == "claude-opus-4-6"


class TestAnthropicProviderComplete:
    _VALID_DIAGNOSIS_JSON = (
        '{"root_cause": "disk full", "confidence": 0.9, '
        '"next_checks": ["check disk"], "evidence": []}'
    )

    def test_returns_validated_pydantic_model(self):
        with patch("investigator.llm.anthropic_provider.Anthropic") as mock_cls:
            mock_cls.return_value.messages.create.return_value = _make_mock_message(
                self._VALID_DIAGNOSIS_JSON
            )
            provider = AnthropicLLMProvider(api_key="sk-ant-test")
            result = provider.complete(
                system="You are a diagnosis engine",
                user="What failed?",
                response_model=DiagnosisResult,
            )
        assert isinstance(result, DiagnosisResult)
        assert result.root_cause == "disk full"

    def test_calls_anthropic_messages_create(self):
        with patch("investigator.llm.anthropic_provider.Anthropic") as mock_cls:
            client = mock_cls.return_value
            client.messages.create.return_value = _make_mock_message(
                self._VALID_DIAGNOSIS_JSON
            )
            provider = AnthropicLLMProvider(api_key="sk-ant-test")
            provider.complete(
                system="sys",
                user="usr",
                response_model=DiagnosisResult,
            )
        assert client.messages.create.called

    def test_system_prompt_forwarded(self):
        with patch("investigator.llm.anthropic_provider.Anthropic") as mock_cls:
            client = mock_cls.return_value
            client.messages.create.return_value = _make_mock_message(
                self._VALID_DIAGNOSIS_JSON
            )
            provider = AnthropicLLMProvider(api_key="sk-ant-test")
            provider.complete(
                system="custom system prompt",
                user="user turn",
                response_model=DiagnosisResult,
            )
        kwargs = client.messages.create.call_args.kwargs
        assert "custom system prompt" in kwargs["system"]

    def test_user_turn_forwarded(self):
        with patch("investigator.llm.anthropic_provider.Anthropic") as mock_cls:
            client = mock_cls.return_value
            client.messages.create.return_value = _make_mock_message(
                self._VALID_DIAGNOSIS_JSON
            )
            provider = AnthropicLLMProvider(api_key="sk-ant-test")
            provider.complete(
                system="sys",
                user="my user turn content",
                response_model=DiagnosisResult,
            )
        kwargs = client.messages.create.call_args.kwargs
        messages = kwargs["messages"]
        assert any("my user turn content" in str(m) for m in messages)

    def test_raises_on_invalid_json_response(self):
        with patch("investigator.llm.anthropic_provider.Anthropic") as mock_cls:
            mock_cls.return_value.messages.create.return_value = _make_mock_message(
                "not json at all"
            )
            provider = AnthropicLLMProvider(api_key="sk-ant-test")
            with pytest.raises(Exception):
                provider.complete(
                    system="sys",
                    user="user",
                    response_model=DiagnosisResult,
                )

    def test_raises_on_schema_mismatch(self):
        with patch("investigator.llm.anthropic_provider.Anthropic") as mock_cls:
            mock_cls.return_value.messages.create.return_value = _make_mock_message(
                '{"totally_wrong_field": 42}'
            )
            provider = AnthropicLLMProvider(api_key="sk-ant-test")
            with pytest.raises(Exception):
                provider.complete(
                    system="sys",
                    user="user",
                    response_model=DiagnosisResult,
                )
