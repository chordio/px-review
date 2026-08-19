from __future__ import annotations

import json
from pathlib import Path
from typing import Protocol

from openai import OpenAI

from .models import ReviewDraft


class ReviewProvider(Protocol):
    model: str

    def review(self, system_prompt: str, user_prompt: str) -> ReviewDraft: ...


class OpenAIReviewProvider:
    """Responses API adapter with a Pydantic-backed Structured Output."""

    def __init__(
        self,
        *,
        model: str,
        api_key: str | None = None,
        reasoning_effort: str = "medium",
    ) -> None:
        self.model = model
        self.reasoning_effort = reasoning_effort
        self._client = OpenAI(api_key=api_key, timeout=300, max_retries=2)

    def review(self, system_prompt: str, user_prompt: str) -> ReviewDraft:
        response = self._client.responses.parse(
            model=self.model,
            reasoning={"effort": self.reasoning_effort},
            input=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            text_format=ReviewDraft,
            store=False,
        )
        if response.output_parsed is None:
            raise RuntimeError("The review model returned no parseable review.")
        return response.output_parsed


class FixtureReviewProvider:
    """Deterministic provider used by tests, demos, and no-spend local runs."""

    model = "fixture"

    def __init__(self, fixture: Path | ReviewDraft) -> None:
        self._fixture = fixture

    def review(self, system_prompt: str, user_prompt: str) -> ReviewDraft:
        del system_prompt, user_prompt
        if isinstance(self._fixture, ReviewDraft):
            return self._fixture
        return ReviewDraft.model_validate(json.loads(self._fixture.read_text()))
