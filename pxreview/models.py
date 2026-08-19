from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class Severity(StrEnum):
    BLOCKING = "blocking"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


SEVERITY_ORDER = {
    Severity.BLOCKING: 0,
    Severity.HIGH: 1,
    Severity.MEDIUM: 2,
    Severity.LOW: 3,
}


class ReviewFinding(BaseModel):
    """One actionable PX defect, filed to exactly one taxonomy category."""

    model_config = ConfigDict(extra="forbid")

    category: str = Field(description="Taxonomy category ID, for example intent_fidelity.")
    severity: Severity
    title: str = Field(min_length=4, max_length=100)
    body: str = Field(
        min_length=10,
        max_length=1200,
        description="Why this creates a product-experience problem in this PR.",
    )
    recommendation: str = Field(
        min_length=4,
        max_length=800,
        description="A concrete, scoped change that resolves the finding.",
    )
    path: str | None = Field(
        default=None,
        description="Repository-relative changed file path when the finding is line-addressable.",
    )
    line: int | None = Field(
        default=None,
        ge=1,
        description="RIGHT-side changed line in the pull-request diff.",
    )
    confidence: float = Field(ge=0, le=1)
    evidence: list[str] = Field(
        default_factory=list,
        max_length=5,
        description="Specific evidence from the diff, brief, or repository context.",
    )


class CategoryAssessment(BaseModel):
    model_config = ConfigDict(extra="forbid")

    category: str
    status: Literal["findings", "no_findings", "not_evaluated"]
    summary: str = Field(min_length=2, max_length=300)


class ReviewDraft(BaseModel):
    """The provider's structured output before deterministic post-processing."""

    model_config = ConfigDict(extra="forbid")

    summary: str = Field(min_length=5, max_length=1200)
    findings: list[ReviewFinding] = Field(default_factory=list, max_length=30)
    categories: list[CategoryAssessment] = Field(default_factory=list, max_length=8)


@dataclass(frozen=True)
class ChangedFile:
    path: str
    status: str
    patch: str
    changed_lines: frozenset[int]


@dataclass(frozen=True)
class DiffBundle:
    base_sha: str
    head_sha: str
    files: tuple[ChangedFile, ...]

    @property
    def patch(self) -> str:
        return "\n".join(file.patch for file in self.files)

    @property
    def changed_paths(self) -> tuple[str, ...]:
        return tuple(file.path for file in self.files)

    def is_commentable(self, path: str | None, line: int | None) -> bool:
        if not path or line is None:
            return False
        return any(file.path == path and line in file.changed_lines for file in self.files)


@dataclass(frozen=True)
class ReviewContext:
    repo_root: Path
    repository: str
    pull_number: int | None
    title: str
    body: str
    diff: DiffBundle
    documents: tuple[tuple[str, str], ...] = ()


@dataclass(frozen=True)
class ReviewOutcome:
    summary: str
    findings: tuple[ReviewFinding, ...]
    categories: tuple[CategoryAssessment, ...]
    conclusion: Literal["success", "neutral", "failure"]
    skipped: bool = False
    skip_reason: str | None = None
    model: str | None = None
    inline_fingerprints: tuple[str, ...] = field(default_factory=tuple)


@dataclass(frozen=True)
class PullRequest:
    repository: str
    number: int
    title: str
    body: str
    base_sha: str
    head_sha: str
    clone_url: str
    draft: bool = False
    from_fork: bool = False
    html_url: str | None = None
