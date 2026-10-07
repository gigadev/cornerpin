"""The model behind the outreach agent (ADR-038), behind a small interface so tests and evals
can script it. Only outbox handlers call it, never a request (ADR-010)."""

from dataclasses import dataclass, field
from functools import lru_cache
from typing import Any, Protocol

import anthropic
import httpx2
from anthropic.types import MessageParam, ToolParam

from cornerpin.core.config import get_settings

MAX_TOKENS = 1024


@dataclass(frozen=True)
class ToolCall:
    id: str
    name: str
    input: dict[str, Any]


@dataclass(frozen=True)
class Usage:
    input_tokens: int = 0
    output_tokens: int = 0
    cache_read_tokens: int = 0
    cache_write_tokens: int = 0

    def __add__(self, other: "Usage") -> "Usage":
        return Usage(
            input_tokens=self.input_tokens + other.input_tokens,
            output_tokens=self.output_tokens + other.output_tokens,
            cache_read_tokens=self.cache_read_tokens + other.cache_read_tokens,
            cache_write_tokens=self.cache_write_tokens + other.cache_write_tokens,
        )


@dataclass(frozen=True)
class ModelReply:
    text: str
    tool_calls: tuple[ToolCall, ...] = ()
    stop_reason: str | None = "end_turn"
    usage: Usage = field(default_factory=Usage)


class AgentModel(Protocol):
    name: str

    def reply(
        self, *, system: str, messages: list[MessageParam], tools: list[ToolParam]
    ) -> ModelReply: ...


class ClaudeModel:
    """Claude through the Messages API. The system prompt and tools are the same on every call
    of a turn, so the request asks for prompt caching."""

    def __init__(self, api_key: str, name: str, http_client: httpx2.Client | None = None) -> None:
        self.name = name
        self._client = anthropic.Anthropic(
            api_key=api_key, http_client=http_client, max_retries=2, timeout=60.0
        )

    def reply(
        self, *, system: str, messages: list[MessageParam], tools: list[ToolParam]
    ) -> ModelReply:
        message = self._client.messages.create(
            model=self.name,
            max_tokens=MAX_TOKENS,
            system=system,
            messages=messages,
            tools=tools,
            cache_control={"type": "ephemeral"},
        )
        text = "".join(block.text for block in message.content if block.type == "text")
        calls = tuple(
            ToolCall(id=block.id, name=block.name, input=dict(block.input))
            for block in message.content
            if block.type == "tool_use"
        )
        usage = message.usage
        return ModelReply(
            text=text,
            tool_calls=calls,
            stop_reason=message.stop_reason,
            usage=Usage(
                input_tokens=usage.input_tokens,
                output_tokens=usage.output_tokens,
                cache_read_tokens=usage.cache_read_input_tokens or 0,
                cache_write_tokens=usage.cache_creation_input_tokens or 0,
            ),
        )


@lru_cache
def _claude(api_key: str, name: str) -> ClaudeModel:
    return ClaudeModel(api_key, name)


def get_model() -> AgentModel | None:
    """The configured model, or None while the agent is dormant (no ANTHROPIC_API_KEY)."""
    settings = get_settings()
    if not settings.anthropic_api_key:
        return None
    return _claude(settings.anthropic_api_key, settings.agent_model)
