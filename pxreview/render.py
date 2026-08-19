from __future__ import annotations

from .engine import finding_fingerprint
from .models import PullRequest, ReviewFinding, ReviewOutcome
from .taxonomy import CATEGORY_BY_ID, TAXONOMY_VERSION

_STATUS_LABELS = {
    "findings": "Finding",
    "no_findings": "No finding",
    "not_evaluated": "Not evaluated",
}

SUMMARY_MARKER = "<!-- px-review:summary -->"


def _escape_table(text: str) -> str:
    return _safe_markdown(text).replace("|", "\\|").replace("\n", " ")


def _safe_markdown(text: str) -> str:
    """Prevent model/repository text from generating mentions or HTML comments."""
    return text.replace("@", "@\u200b").replace("<!--", "<\u200b!--")


def _code_path(path: str) -> str:
    return path.replace("`", "'").replace("\n", "")


def render_inline_comment(finding: ReviewFinding) -> str:
    category = CATEGORY_BY_ID[finding.category]
    evidence = ""
    if finding.evidence:
        evidence = "\n\nEvidence: " + "; ".join(
            _safe_markdown(item) for item in finding.evidence
        )
    return (
        f"**PX · {category.name} · {finding.severity.value}**\n\n"
        f"**{_safe_markdown(finding.title)}**\n\n"
        f"{_safe_markdown(finding.body)}\n\n"
        f"Suggested change: {_safe_markdown(finding.recommendation)}"
        f"{evidence}\n\n"
        f"<!-- px-review:{finding_fingerprint(finding)} -->"
    )


def render_check_summary(outcome: ReviewOutcome) -> str:
    lines = [
        f"## PX review · taxonomy v{TAXONOMY_VERSION}",
        "",
        _safe_markdown(outcome.summary),
        "",
    ]
    if outcome.skipped:
        lines.extend([f"Skipped: {outcome.skip_reason}", ""])
    if outcome.categories:
        lines.extend(
            [
                "| Category | Status | Assessment |",
                "|---|---|---|",
            ]
        )
        for assessment in outcome.categories:
            category = CATEGORY_BY_ID[assessment.category]
            lines.append(
                f"| {category.number}. {category.name} | "
                f"{_STATUS_LABELS[assessment.status]} | "
                f"{_escape_table(assessment.summary)} |"
            )
        lines.append("")

    if outcome.findings:
        lines.extend([f"### Findings ({len(outcome.findings)})", ""])
        for finding in outcome.findings:
            category = CATEGORY_BY_ID[finding.category]
            location = (
                f" — `{_code_path(finding.path)}:{finding.line}`"
                if finding.path is not None
                else ""
            )
            lines.extend(
                [
                    f"- **[{finding.severity.value}] {_safe_markdown(finding.title)}** "
                    f"({category.name}){location}",
                    f"  {_safe_markdown(finding.body)}",
                    f"  Suggested change: {_safe_markdown(finding.recommendation)}",
                ]
            )
    else:
        lines.append("No high-confidence PX findings in the reviewed change.")

    lines.extend(
        [
            "",
            "_This is a change review, not a PX-bench score. “Not evaluated” means "
            "the diff did not provide enough evidence for that category._",
        ]
    )
    if outcome.model:
        lines.append(f"\nModel: `{outcome.model}`")
    return "\n".join(lines)


def render_review_body(outcome: ReviewOutcome, *, inline_count: int | None = None) -> str:
    if inline_count is None:
        inline_count = sum(finding.path is not None for finding in outcome.findings)
    summary_count = len(outcome.findings) - sum(
        finding.path is not None for finding in outcome.findings
    )
    pieces = [f"PX review found {len(outcome.findings)} high-confidence issue(s)."]
    if inline_count:
        pieces.append(f"{inline_count} new finding(s) are attached to changed lines.")
    if summary_count:
        pieces.append(f"{summary_count} are feature-level findings in the PR summary.")
    pieces.append("See the persistent **PX Review** comment for coverage and the full report.")
    return " ".join(pieces)


def render_pr_summary(outcome: ReviewOutcome, pull: PullRequest) -> str:
    """Render the persistent PR-conversation report and its reproducibility receipt."""
    evaluated = sum(
        assessment.status != "not_evaluated" for assessment in outcome.categories
    )
    total = len(outcome.categories)
    status = (
        "Skipped"
        if outcome.skipped
        else f"{len(outcome.findings)} finding(s) · {evaluated}/{total} categories evaluated"
    )
    model = f"`{_safe_markdown(outcome.model)}`" if outcome.model else "not recorded"
    receipt = "\n".join(
        [
            "<details>",
            "<summary>Review receipt</summary>",
            "",
            f"- Taxonomy: PX v{TAXONOMY_VERSION}",
            f"- Policy source: base commit `{pull.base_sha[:12]}`",
            f"- Reviewed head: `{pull.head_sha[:12]}`",
            f"- Model: {model}",
            "- Reproduce: "
            f"`px-review local --base {pull.base_sha[:12]} --head {pull.head_sha[:12]}`",
            "",
            "The taxonomy, policy, evidence, and exact code location are shown so each "
            "finding can be challenged and reproduced.",
            "</details>",
        ]
    )
    return "\n\n".join(
        [
            SUMMARY_MARKER,
            f"**{status}**",
            render_check_summary(outcome),
            receipt,
            "New pushes are reviewed automatically. To rerun now, comment `/px review` "
            "or `@px-review review`.",
        ]
    )
