"""The model side of an eval run: Claude with its replies recorded, the recorded replies played
back, a planted regression, and what tokens cost."""

import hashlib
import json
import re
from collections.abc import Callable
from dataclasses import asdict, dataclass, field
from decimal import Decimal
from pathlib import Path
from typing import Any

from anthropic.types import MessageParam, ToolParam

from cornerpin.outreach import agent
from cornerpin.outreach.model import AgentModel, ModelReply, ToolCall, Usage
from cornerpin.outreach.tools import tool_params

RECORDINGS = Path(__file__).parent / "recordings"


@dataclass(frozen=True)
class Rates:
    """US dollars per million tokens (platform.claude.com pricing, October 2026)."""

    input: Decimal
    output: Decimal
    cache_write: Decimal  # 5-minute cache
    cache_read: Decimal


RATES: dict[str, Rates] = {
    "claude-sonnet-5-5": Rates(Decimal(2), Decimal(10), Decimal("2.50"), Decimal("0.20")),
    "claude-opus-5-5": Rates(Decimal(4), Decimal(20), Decimal(5), Decimal("0.20")),
    "claude-haiku-4-5": Rates(Decimal(1), Decimal(5), Decimal("1.25"), Decimal("0.10")),
}


def cost(model: str, usage: Usage) -> Decimal | None:
    """What `usage` costs on `model`, or None for a model without known rates."""
    rates = next((r for name, r in RATES.items() if model.startswith(name)), None)
    if rates is None:
        return None
    million = Decimal(1_000_000)
    return (
        usage.input_tokens * rates.input
        + usage.output_tokens * rates.output
        + usage.cache_write_tokens * rates.cache_write
        + usage.cache_read_tokens * rates.cache_read
    ) / million


class RecordingExhausted(Exception):
    """The agent asked the model more often than the recording answered: it's out of date."""


@dataclass
class EvalModel:
    """Wraps the model one scenario uses: live (recording what it says) or a recording."""

    name: str
    live: AgentModel | None = None
    replies: list[ModelReply] = field(default_factory=lambda: list[ModelReply]())
    used: int = 0
    usage: Usage = field(default_factory=Usage)
    exhausted: bool = False

    def reply(
        self, *, system: str, messages: list[MessageParam], tools: list[ToolParam]
    ) -> ModelReply:
        if self.live is not None:
            answer = self.live.reply(system=system, messages=messages, tools=tools)
            self.replies.append(answer)
        elif self.used < len(self.replies):
            answer = self.replies[self.used]
        else:
            self.exhausted = True
            raise RecordingExhausted("the recording has no more replies")
        self.used += 1
        self.usage += answer.usage
        return answer

    @property
    def unused(self) -> int:
        return 0 if self.live else len(self.replies) - self.used


def fingerprint(model: str) -> str:
    """What a recording depends on besides the code: the model, the prompt and the tools. A
    recording made under another fingerprint is out of date and must be made again live."""
    contract = json.dumps(
        {"model": model, "system": agent.SYSTEM, "tools": tool_params()}, sort_keys=True
    )
    return hashlib.sha256(contract.encode()).hexdigest()[:16]


def recording_path(scenario: str) -> Path:
    return RECORDINGS / f"{scenario}.json"


@dataclass(frozen=True)
class Recording:
    model: str
    fingerprint: str
    replies: list[ModelReply]


def load(scenario: str) -> Recording | None:
    path = recording_path(scenario)
    if not path.exists():
        return None
    data: dict[str, Any] = json.loads(path.read_text(encoding="utf-8"))
    replies = [
        ModelReply(
            text=r["text"],
            tool_calls=tuple(ToolCall(**c) for c in r["tool_calls"]),
            stop_reason=r["stop_reason"],
            usage=Usage(**r["usage"]),
        )
        for r in data["replies"]
    ]
    return Recording(data["model"], data["fingerprint"], replies)


def save(scenario: str, model: str, replies: list[ModelReply]) -> None:
    RECORDINGS.mkdir(exist_ok=True)
    data = {
        "model": model,
        "fingerprint": fingerprint(model),
        "replies": [asdict(r) for r in replies],
    }
    recording_path(scenario).write_text(
        json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )


# --- planted regressions -----------------------------------------------------------------------

_MONEY = re.compile(r"\$\s?(\d{1,3}(?:,\d{3})+|\d+)")


@dataclass
class InventedPrice:
    """A regression the suite must catch: the model's emails raise every price by $5,000, as
    if the prompt had stopped holding it to the listings."""

    inner: AgentModel
    name: str = field(init=False)

    def __post_init__(self) -> None:
        self.name = self.inner.name

    def reply(
        self, *, system: str, messages: list[MessageParam], tools: list[ToolParam]
    ) -> ModelReply:
        answer = self.inner.reply(system=system, messages=messages, tools=tools)
        if answer.tool_calls:
            return answer

        def raise_price(match: re.Match[str]) -> str:
            return f"${int(match.group(1).replace(',', '')) + 5000:,}"

        return ModelReply(
            text=_MONEY.sub(raise_price, answer.text),
            tool_calls=answer.tool_calls,
            stop_reason=answer.stop_reason,
            usage=answer.usage,
        )


PLANTS: dict[str, Callable[[AgentModel], AgentModel]] = {"invented-price": InventedPrice}
