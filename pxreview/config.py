from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel, ConfigDict, Field

from .models import Severity
from .taxonomy import CATEGORY_BY_ID

DEFAULT_INCLUDE = [
    "**/*.css",
    "**/*.html",
    "**/*.jsx",
    "**/*.mdx",
    "**/*.svelte",
    "**/*.tsx",
    "**/*.vue",
    "**/components/**",
    "**/pages/**",
    "**/routes/**",
    "**/screens/**",
]

DEFAULT_EXCLUDE = [
    "**/*.snap",
    "**/dist/**",
    "**/generated/**",
    "**/node_modules/**",
    "**/vendor/**",
]


class ReviewConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    include: list[str] = Field(default_factory=lambda: list(DEFAULT_INCLUDE))
    exclude: list[str] = Field(default_factory=lambda: list(DEFAULT_EXCLUDE))
    context: list[str] = Field(
        default_factory=lambda: [
            "AGENTS.md",
            "CLAUDE.md",
            "README.md",
            "package.json",
            "**/components/ui/**/*",
            "**/design-system/**/*",
            "**/tokens.css",
            "**/tokens.json",
            "**/tokens.ts",
            "**/tokens.tsx",
        ]
    )
    brief: list[str] = Field(default_factory=list)
    categories: list[str] = Field(default_factory=lambda: list(CATEGORY_BY_ID))
    model: str = "gpt-5.6-terra"
    reasoning_effort: Literal["none", "low", "medium", "high", "xhigh", "max"] = "medium"
    max_inline_comments: int = Field(default=12, ge=0, le=30)
    min_confidence: float = Field(default=0.78, ge=0, le=1)
    block_on: list[Severity] = Field(default_factory=lambda: [Severity.BLOCKING])
    review_drafts: bool = False
    review_forks: bool = False
    max_diff_chars: int = Field(default=140_000, ge=10_000, le=500_000)
    max_context_chars: int = Field(default=80_000, ge=5_000, le=300_000)
    max_file_chars: int = Field(default=20_000, ge=1_000, le=100_000)


def load_config(repo_root: Path, *, ref: str | None = None) -> ReviewConfig:
    """Load policy from the working tree or a trusted git ref.

    The GitHub service always uses the PR's base SHA so a pull request cannot
    raise its own spend limits, enable fork review, or disable categories.
    """
    if ref is None:
        path = repo_root / ".pxreview.yml"
        if not path.exists():
            return ReviewConfig()
        text = path.read_text()
    else:
        result = subprocess.run(
            ["git", "show", f"{ref}:.pxreview.yml"],
            cwd=repo_root,
            capture_output=True,
            text=True,
            check=False,
        )
        if result.returncode != 0:
            return ReviewConfig()
        text = result.stdout
    raw = yaml.safe_load(text) or {}
    if not isinstance(raw, dict):
        raise ValueError(".pxreview.yml must contain a YAML object.")
    config = ReviewConfig.model_validate(raw)
    unknown_categories = set(config.categories) - set(CATEGORY_BY_ID)
    if unknown_categories:
        names = ", ".join(sorted(unknown_categories))
        raise ValueError(f".pxreview.yml contains unknown categories: {names}")
    return config
