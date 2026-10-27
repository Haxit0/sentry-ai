"""Model access shared by the agents: receipt accounting and tolerant JSON extraction."""

import json
import re
from collections.abc import Mapping, Sequence
from typing import Any

from app.agents.schemas import ModelUsage
from app.integrations.meterless import Completion, InferenceProvider

_FENCE = re.compile(r"^```(?:json)?\s*|\s*```$", re.IGNORECASE)


def extract_json(text: str) -> dict[str, Any] | None:
    """Return the first JSON object in model text (fences and chatter tolerated), else None."""
    cleaned = _FENCE.sub("", text.strip())
    start = cleaned.find("{")
    while start != -1:
        depth = 0
        in_string = escaped = False
        for index in range(start, len(cleaned)):
            char = cleaned[index]
            if in_string:
                if escaped:
                    escaped = False
                elif char == "\\":
                    escaped = True
                elif char == '"':
                    in_string = False
                continue
            if char == '"':
                in_string = True
            elif char == "{":
                depth += 1
            elif char == "}":
                depth -= 1
                if depth == 0:
                    try:
                        value = json.loads(cleaned[start:index + 1])
                    except ValueError:
                        break
                    return value if isinstance(value, dict) else None
        start = cleaned.find("{", start + 1)
    return None


class RecordingModel:
    """Wraps the Nightshift client and keeps every completion's routing and receipt metadata."""

    def __init__(self, provider: InferenceProvider, requested_model: str) -> None:
        self.provider = provider
        self.requested_model = requested_model
        self.completions: list[Completion] = []

    def ask_json(self, system: str, user: str, *, max_tokens: int = 600) -> tuple[dict[str, Any] | None, Completion]:
        completion = self.provider.chat(
            [{"role": "system", "content": system}, {"role": "user", "content": user}],
            max_tokens=max_tokens, temperature=0.0,
        )
        self.completions.append(completion)
        return extract_json(completion.text), completion

    def usage(self) -> ModelUsage:
        unique = lambda values: sorted({value for value in values if value})  # noqa: E731
        return ModelUsage(
            requested_model=self.requested_model,
            models_used=unique(c.model_id for c in self.completions),
            providers=unique(c.provider for c in self.completions),
            receipt_ids=[c.receipt_id for c in self.completions if c.receipt_id],
            signed_receipts=sum(c.receipt_signed for c in self.completions),
            calls=len(self.completions),
            prompt_tokens=sum(c.prompt_tokens for c in self.completions),
            completion_tokens=sum(c.completion_tokens for c in self.completions),
        )


def compact(value: Any) -> str:
    return json.dumps(value, separators=(",", ":"), default=str)


def as_str_list(value: Any, limit: int = 20) -> list[str]:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes)):
        return []
    return [str(item)[:200] for item in value if isinstance(item, (str, int))][:limit]


def as_text(value: Any, limit: int = 1200) -> str:
    return value.strip()[:limit] if isinstance(value, str) else ""


def first(mapping: Mapping[str, Any], *keys: str) -> Any:
    for key in keys:
        if key in mapping:
            return mapping[key]
    return None
