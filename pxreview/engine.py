from __future__ import annotations

import hashlib
import re

from .config import ReviewConfig
from .models import (
    SEVERITY_ORDER,
    CategoryAssessment,
    ReviewContext,
    ReviewDraft,
    ReviewFinding,
    ReviewOutcome,
)
from .prompts import SYSTEM_PROMPT, build_user_prompt
from .provider import ReviewProvider
from .taxonomy import CATEGORY_BY_ID


def finding_fingerprint(finding: ReviewFinding) -> str:
    normalized_title = re.sub(r"\s+", " ", finding.title.strip().lower())
    raw = f"{finding.category}|{finding.path or ''}|{finding.line or ''}|{normalized_title}"
    return hashlib.sha256(raw.encode()).hexdigest()[:16]


def _normalize_categories(
    draft: ReviewDraft,
    config: ReviewConfig,
    findings: list[ReviewFinding],
) -> tuple[CategoryAssessment, ...]:
    enabled = set(config.categories)
    supplied = {
        item.category: item
        for item in draft.categories
        if item.category in enabled
    }
    finding_categories = {finding.category for finding in findings}
    result: list[CategoryAssessment] = []
    for category_id in config.categories:
        item = supplied.get(category_id)
        if item is None:
            result.append(
                CategoryAssessment(
                    category=category_id,
                    status="not_evaluated",
                    summary="The model did not return an assessment for this category.",
                )
            )
        elif category_id in finding_categories and item.status != "findings":
            result.append(item.model_copy(update={"status": "findings"}))
        elif category_id not in finding_categories and item.status == "findings":
            result.append(item.model_copy(update={"status": "no_findings"}))
        else:
            result.append(item)
    return tuple(result)


def finalize_review(
    draft: ReviewDraft,
    context: ReviewContext,
    config: ReviewConfig,
    *,
    model: str | None,
) -> ReviewOutcome:
    enabled = set(config.categories)
    seen: set[str] = set()
    accepted: list[ReviewFinding] = []
    for finding in draft.findings:
        if finding.category not in enabled or finding.category not in CATEGORY_BY_ID:
            continue
        if finding.confidence < config.min_confidence:
            continue
        # A partial location is never publishable. Keep honest summary-only
        # findings, and drop fabricated/non-commentable line locations.
        if (finding.path is None) != (finding.line is None):
            continue
        if finding.path is not None and not context.diff.is_commentable(
            finding.path, finding.line
        ):
            finding = finding.model_copy(update={"path": None, "line": None})
        fingerprint = finding_fingerprint(finding)
        if fingerprint in seen:
            continue
        seen.add(fingerprint)
        accepted.append(finding)

    accepted.sort(
        key=lambda item: (
            SEVERITY_ORDER[item.severity],
            item.path is None,
            item.path or "",
            item.line or 0,
            item.title.lower(),
        )
    )

    # max_inline_comments caps the expensive/noisy line-level surface. Summary
    # findings remain visible in the check output even when not posted inline.
    inline_seen = 0
    inline_fingerprints: list[str] = []
    normalized: list[ReviewFinding] = []
    for finding in accepted:
        if finding.path is not None:
            if inline_seen >= config.max_inline_comments:
                finding = finding.model_copy(update={"path": None, "line": None})
            else:
                inline_seen += 1
                inline_fingerprints.append(finding_fingerprint(finding))
        normalized.append(finding)

    categories = _normalize_categories(draft, config, normalized)
    if any(finding.severity in config.block_on for finding in normalized):
        conclusion = "failure"
    elif normalized:
        conclusion = "neutral"
    else:
        conclusion = "success"
    return ReviewOutcome(
        summary=draft.summary,
        findings=tuple(normalized),
        categories=categories,
        conclusion=conclusion,
        model=model,
        inline_fingerprints=tuple(inline_fingerprints),
    )


def run_review(
    context: ReviewContext,
    config: ReviewConfig,
    provider: ReviewProvider,
) -> ReviewOutcome:
    if not context.diff.files:
        return ReviewOutcome(
            summary="No PX-relevant files changed.",
            findings=(),
            categories=(),
            conclusion="success",
            skipped=True,
            skip_reason="No changed files matched `.pxreview.yml` include/exclude rules.",
            model=getattr(provider, "model", None),
        )
    draft = provider.review(SYSTEM_PROMPT, build_user_prompt(context, config))
    return finalize_review(
        draft,
        context,
        config,
        model=getattr(provider, "model", None),
    )
