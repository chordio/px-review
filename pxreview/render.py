from __future__ import annotations

from collections import defaultdict

from .engine import finding_fingerprint
from .models import (
    SEVERITY_ORDER,
    CategoryAssessment,
    PullRequest,
    ReviewFinding,
    ReviewOutcome,
    Severity,
)
from .taxonomy import CATEGORY_BY_ID, TAXONOMY_VERSION

SUMMARY_MARKER = "<!-- px-review:summary -->"

# One colour per category, the way a status page reads at a glance:
#   red     a blocking or high finding lives here
#   yellow  a medium or low finding lives here
#   green   evaluated, nothing found
#   white   the diff gave no evidence for this category
RED, YELLOW, GREEN, WHITE = "🔴", "🟡", "🟢", "⚪"


def _safe_markdown(text: str) -> str:
    """Prevent model/repository text from generating mentions or HTML comments."""
    return text.replace("@", "@\u200b").replace("<!--", "<\u200b!--")


def _escape_table(text: str) -> str:
    return _safe_markdown(text).replace("|", "\\|").replace("\n", " ")


def _code_path(path: str) -> str:
    return path.replace("`", "'").replace("\n", "")


def _evidence(items: list[str]) -> str:
    """Inline code, so `<button>` and friends survive GitHub's HTML filter."""
    return "; ".join(f"`{_safe_markdown(_code_path(item))}`" for item in items)


def _plain(text: str) -> str:
    """Text for inside a fenced block: only a backtick fence could close it early.

    Mentions and HTML comments are inert inside a code block, and this text is
    pasted into a coding agent, so it must not carry the zero-width spaces that
    `_safe_markdown` adds: those turn `@/components/Button.tsx` into a path no
    agent can find.
    """
    return text.replace("```", "'''").strip()


def _location(finding: ReviewFinding) -> str:
    return f"{finding.path}:{finding.line}" if finding.path is not None else ""


def _severity_colour(severity: Severity) -> str:
    return RED if SEVERITY_ORDER[severity] <= SEVERITY_ORDER[Severity.HIGH] else YELLOW


def _worst(findings: list[ReviewFinding]) -> Severity | None:
    if not findings:
        return None
    return min((finding.severity for finding in findings), key=SEVERITY_ORDER.__getitem__)


def category_colour(
    assessment: CategoryAssessment, findings: list[ReviewFinding]
) -> str:
    if findings:
        worst = _worst(findings)
        assert worst is not None
        return _severity_colour(worst)
    if assessment.status == "not_evaluated":
        return WHITE
    return GREEN


def outcome_colour(outcome: ReviewOutcome) -> str:
    if outcome.skipped:
        return WHITE
    worst = _worst(list(outcome.findings))
    return GREEN if worst is None else _severity_colour(worst)


def _findings_by_category(
    outcome: ReviewOutcome,
) -> dict[str, list[ReviewFinding]]:
    grouped: dict[str, list[ReviewFinding]] = defaultdict(list)
    for finding in outcome.findings:
        grouped[finding.category].append(finding)
    return grouped


def _count(findings: list[ReviewFinding]) -> str:
    """'1 high, 2 medium' in severity order."""
    counts: dict[Severity, int] = {}
    for finding in findings:
        counts[finding.severity] = counts.get(finding.severity, 0) + 1
    return ", ".join(
        f"{counts[severity]} {severity.value}"
        for severity in sorted(counts, key=SEVERITY_ORDER.__getitem__)
    )


def _coverage(outcome: ReviewOutcome) -> str:
    evaluated = sum(item.status != "not_evaluated" for item in outcome.categories)
    return f"{evaluated}/{len(outcome.categories)} categories evaluated."


def _check_line(outcome: ReviewOutcome) -> str:
    fails_on = ", ".join(f"`{severity.value}`" for severity in outcome.block_on)
    policy = (
        f"The check fails only on {fails_on} findings"
        if outcome.block_on
        else "The check never fails on findings"
    )
    worst = _worst(list(outcome.findings))
    highest = (
        f" Highest severity here: **{worst.value}**." if worst is not None else ""
    )
    return f"{policy} (`block_on` in `.pxreview.yml`).{highest}"


def _headline(outcome: ReviewOutcome) -> str:
    if outcome.skipped:
        return f"## {WHITE} PX Review · skipped"
    count = len(outcome.findings)
    noun = "finding" if count == 1 else "findings"
    verdict = "check failed" if outcome.conclusion == "failure" else "check passed"
    return f"## {outcome_colour(outcome)} PX Review · {count} {noun} · {verdict}"


def render_finding(finding: ReviewFinding) -> list[str]:
    """One finding as a markdown list item: what, where, why, and the fix."""
    location = _location(finding)
    where = f" · `{_code_path(location)}`" if location else ""
    lines = [
        f"- **[{finding.severity.value}] {_safe_markdown(finding.title)}**{where}",
        f"  {_safe_markdown(finding.body)}",
        f"  **Fix:** {_safe_markdown(finding.recommendation)}",
    ]
    if finding.evidence:
        lines.append("  Evidence: " + _evidence(finding.evidence))
    return lines


def agent_prompt(
    outcome: ReviewOutcome,
    *,
    repository: str | None = None,
    pull_number: int | None = None,
    head_sha: str | None = None,
) -> str:
    """Plain text a person can paste into a coding agent to fix every finding."""
    where = ""
    if repository:
        where = f" in {repository}"
        if pull_number is not None:
            where += f" (pull request #{pull_number}"
            where += f", head {head_sha[:12]})" if head_sha else ")"
    lines = [
        f"Fix the following PX Review findings{where}.",
        "Each one names the file and line, the product-experience problem, and the",
        "change that resolves it. Make the smallest change that resolves each finding,",
        "keep the product's existing components and conventions, and do not touch",
        "unrelated code.",
        "",
    ]
    for index, finding in enumerate(outcome.findings, start=1):
        category = CATEGORY_BY_ID[finding.category]
        lines.append(
            f"{index}. [{finding.severity.value}] {category.name}: {_plain(finding.title)}"
        )
        location = _location(finding)
        lines.append(
            f"   Where: {location}" if location else "   Where: feature-level, not one line"
        )
        lines.append(f"   Problem: {_plain(finding.body)}")
        lines.append(f"   Fix: {_plain(finding.recommendation)}")
        if finding.evidence:
            lines.append("   Evidence: " + "; ".join(_plain(item) for item in finding.evidence))
        lines.append("")
    return "\n".join(lines).rstrip()


def _agent_prompt_section(
    outcome: ReviewOutcome,
    *,
    repository: str | None,
    pull_number: int | None,
    head_sha: str | None,
) -> list[str]:
    """The prompt as a plain fenced block, not inside a collapsible.

    GitHub's copy button sits on the block itself. Kept at the top level so
    the button is always there to hover, with no section to expand first and
    no heading that reads like a button and does nothing when clicked.
    """
    count = len(outcome.findings)
    noun = "finding" if count == 1 else "findings"
    return [
        f"**Prompt for a coding agent** · fixes all {count} {noun} · copy the block below",
        "",
        "```text",
        agent_prompt(
            outcome, repository=repository, pull_number=pull_number, head_sha=head_sha
        ),
        "```",
    ]


def render_report(
    outcome: ReviewOutcome,
    *,
    repository: str | None = None,
    pull_number: int | None = None,
    head_sha: str | None = None,
) -> str:
    """The report body shared by the check output, the job log, and the PR comment.

    Reads top-down the way a status page does: a coloured headline, one coloured
    row per category, then the findings grouped under the categories that have
    them, then a prompt that hands all of them to a coding agent.
    """
    grouped = _findings_by_category(outcome)
    lines = [_headline(outcome), "", _safe_markdown(outcome.summary), ""]
    if outcome.skipped:
        lines.extend([f"Skipped: {outcome.skip_reason}", ""])
    elif outcome.categories:
        lines.extend([f"{_coverage(outcome)} {_check_line(outcome)}", ""])
    else:
        lines.extend([_check_line(outcome), ""])

    if outcome.categories:
        lines.extend(["| | Category | Result |", "|:-:|---|---|"])
        for assessment in outcome.categories:
            category = CATEGORY_BY_ID[assessment.category]
            findings = grouped.get(assessment.category, [])
            colour = category_colour(assessment, findings)
            if findings:
                result = f"**{_count(findings)}**"
            elif assessment.status == "not_evaluated":
                result = "Not evaluated"
            else:
                result = "No finding"
            lines.append(
                f"| {colour} | {category.number}. {category.name} | "
                f"{result} · {_escape_table(assessment.summary)} |"
            )
        lines.append("")

    if outcome.findings:
        ordered = [
            category_id for category_id in CATEGORY_BY_ID if category_id in grouped
        ] + [category_id for category_id in grouped if category_id not in CATEGORY_BY_ID]
        for category_id in ordered:
            findings = grouped[category_id]
            category = CATEGORY_BY_ID[category_id]
            worst = _worst(findings)
            assert worst is not None
            lines.append(
                f"### {_severity_colour(worst)} {category.number}. {category.name} · "
                f"{_count(findings)}"
            )
            lines.append("")
            for finding in findings:
                lines.extend(render_finding(finding))
            lines.append("")
        lines.extend(
            _agent_prompt_section(
                outcome, repository=repository, pull_number=pull_number, head_sha=head_sha
            )
        )
    elif not outcome.skipped:
        lines.append("No high-confidence PX findings in the reviewed change.")

    lines.extend(
        [
            "",
            f"_PX taxonomy v{TAXONOMY_VERSION}. This is a change review, not a PX-bench "
            f"score. {WHITE} Not evaluated means the diff did not provide enough evidence "
            "for that category._",
        ]
    )
    if outcome.model:
        lines.append(f"\nModel: `{outcome.model}`")
    return "\n".join(lines)


def render_check_summary(outcome: ReviewOutcome) -> str:
    """The check-run output and the job log: the report without PR coordinates."""
    return render_report(outcome)


def render_inline_comment(finding: ReviewFinding) -> str:
    category = CATEGORY_BY_ID[finding.category]
    evidence = ""
    if finding.evidence:
        evidence = "\n\nEvidence: " + _evidence(finding.evidence)
    prompt = "\n".join(
        [
            f"Fix this PX Review finding at {_location(finding)}.",
            f"Problem ({category.name}, {finding.severity.value}): {_plain(finding.title)}. "
            f"{_plain(finding.body)}",
            f"Fix: {_plain(finding.recommendation)}",
        ]
    )
    return (
        f"**PX · {_severity_colour(finding.severity)} {category.name} · "
        f"{finding.severity.value}**\n\n"
        f"**{_safe_markdown(finding.title)}**\n\n"
        f"{_safe_markdown(finding.body)}\n\n"
        f"**Fix:** {_safe_markdown(finding.recommendation)}"
        f"{evidence}\n\n"
        "**Prompt for a coding agent** · copy the block below\n\n"
        f"```text\n{prompt}\n```\n\n"
        f"<!-- px-review:{finding_fingerprint(finding)} -->"
    )


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


APP_RERUN_HINT = (
    "New pushes are reviewed automatically. To rerun now, comment `/px review` "
    "or `@px-review review`."
)
CI_RERUN_HINT = (
    "New pushes are reviewed automatically. To rerun now, use **Run workflow** on "
    "the PX Review action, or re-run the check."
)


def render_pr_summary(
    outcome: ReviewOutcome, pull: PullRequest, *, rerun_hint: str = APP_RERUN_HINT
) -> str:
    """Render the persistent PR-conversation report and its reproducibility receipt."""
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
            render_report(
                outcome,
                repository=pull.repository,
                pull_number=pull.number,
                head_sha=pull.head_sha,
            ),
            receipt,
            rerun_hint,
        ]
    )
