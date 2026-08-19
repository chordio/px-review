from pathlib import Path

from pxreview.config import ReviewConfig
from pxreview.engine import finalize_review
from pxreview.models import (
    CategoryAssessment,
    ChangedFile,
    DiffBundle,
    ReviewContext,
    ReviewDraft,
    ReviewFinding,
    Severity,
)


def _context() -> ReviewContext:
    return ReviewContext(
        repo_root=Path("."),
        repository="acme/app",
        pull_number=12,
        title="Add destructive action",
        body="Let people remove a saved view.",
        diff=DiffBundle(
            base_sha="base",
            head_sha="head",
            files=(
                ChangedFile(
                    path="app/ViewRow.tsx",
                    status="M",
                    patch="+<button>Delete</button>",
                    changed_lines=frozenset({42}),
                ),
            ),
        ),
    )


def _finding(**changes) -> ReviewFinding:
    values = {
        "category": "pathway_completeness",
        "severity": Severity.HIGH,
        "title": "Delete has no recovery path",
        "body": "The new destructive action completes immediately with no cancel or undo.",
        "recommendation": "Use the existing undo toast after deletion.",
        "path": "app/ViewRow.tsx",
        "line": 42,
        "confidence": 0.94,
        "evidence": ["The added handler deletes immediately."],
    }
    values.update(changes)
    return ReviewFinding(**values)


def test_finalize_filters_deduplicates_and_validates_locations():
    draft = ReviewDraft(
        summary="The delete path needs a recovery affordance.",
        findings=[
            _finding(),
            _finding(),  # duplicate
            _finding(
                title="Wrong line becomes summary-only",
                line=99,
            ),
            _finding(
                title="Below the confidence floor",
                confidence=0.4,
            ),
            _finding(
                title="Unknown category is removed",
                category="code_quality",
            ),
        ],
        categories=[
            CategoryAssessment(
                category="pathway_completeness",
                status="no_findings",
                summary="The model contradicted its own finding.",
            )
        ],
    )
    config = ReviewConfig(max_inline_comments=1)

    outcome = finalize_review(draft, _context(), config, model="fixture")

    assert outcome.conclusion == "neutral"
    assert len(outcome.findings) == 2
    assert outcome.findings[0].path == "app/ViewRow.tsx"
    assert outcome.findings[1].path is None
    pathway = next(
        item for item in outcome.categories if item.category == "pathway_completeness"
    )
    assert pathway.status == "findings"


def test_blocking_findings_fail_the_check_when_configured():
    draft = ReviewDraft(
        summary="The requested action cannot be reached.",
        findings=[_finding(severity=Severity.BLOCKING)],
    )
    outcome = finalize_review(draft, _context(), ReviewConfig(), model="fixture")
    assert outcome.conclusion == "failure"


def test_partial_locations_are_dropped():
    draft = ReviewDraft(
        summary="Malformed evidence should not publish.",
        findings=[_finding(line=None)],
    )
    outcome = finalize_review(draft, _context(), ReviewConfig(), model="fixture")
    assert outcome.findings == ()
    assert outcome.conclusion == "success"

