from pxreview.models import (
    CategoryAssessment,
    PullRequest,
    ReviewFinding,
    ReviewOutcome,
    Severity,
)
from pxreview.render import (
    render_check_summary,
    render_inline_comment,
    render_pr_summary,
)


def test_render_distinguishes_not_evaluated_from_no_findings():
    finding = ReviewFinding(
        category="accessibility",
        severity=Severity.HIGH,
        title="Input has no accessible name",
        body="The newly added input is not associated with @team's visible label.",
        recommendation="Connect the label with htmlFor and a stable input id.",
        path="app/Form.tsx",
        line=18,
        confidence=0.99,
    )
    outcome = ReviewOutcome(
        summary="One accessibility issue is actionable.",
        findings=(finding,),
        categories=(
            CategoryAssessment(
                category="accessibility",
                status="findings",
                summary="The new field is unlabeled.",
            ),
            CategoryAssessment(
                category="resilience",
                status="not_evaluated",
                summary="No runtime or viewport evidence was available.",
            ),
        ),
        conclusion="neutral",
        model="fixture",
    )

    summary = render_check_summary(outcome)
    inline = render_inline_comment(finding)

    assert "Not evaluated" in summary
    assert "not a PX-bench score" in summary
    assert "PX · 🔴 Accessibility · high" in inline
    assert "<!-- px-review:" in inline
    assert "@\u200bteam" in inline

    pull = PullRequest(
        repository="acme/app",
        number=4,
        title="Add field",
        body="",
        base_sha="base1234567890",
        head_sha="head1234567890",
        clone_url="https://github.test/acme/app.git",
    )
    pr_summary = render_pr_summary(outcome, pull)
    assert "<!-- px-review:summary -->" in pr_summary
    assert "Policy source: base commit `base12345678`" in pr_summary
    assert "Reviewed head: `head12345678`" in pr_summary
    assert "px-review local --base base12345678 --head head12345678" in pr_summary
    assert "2/2 categories evaluated" not in pr_summary
    assert "1/2 categories evaluated" in pr_summary


def _finding(**changes) -> ReviewFinding:
    values = {
        "category": "pathway_completeness",
        "severity": Severity.MEDIUM,
        "title": "Delete has no recovery path",
        "body": "The destructive action completes immediately with no undo.",
        "recommendation": "Use the existing undo toast after deletion.",
        "path": "app/ViewRow.tsx",
        "line": 42,
        "confidence": 0.94,
        "evidence": [],
    }
    values.update(changes)
    return ReviewFinding(**values)


def _assessment(category: str, status: str) -> CategoryAssessment:
    return CategoryAssessment(category=category, status=status, summary=f"About {category}.")


def _outcome(findings, categories, **changes) -> ReviewOutcome:
    values = {
        "summary": "Two problems on the delete path, one in the copy.",
        "findings": tuple(findings),
        "categories": tuple(categories),
        "conclusion": "neutral",
        "model": "fixture",
    }
    values.update(changes)
    return ReviewOutcome(**values)


def test_report_reads_like_a_status_page():
    """Colour per category, findings grouped under their category, an agent prompt."""
    high = _finding(
        category="accessibility", severity=Severity.HIGH, title="Icon button is unnamed",
        path="app/Toolbar.tsx", line=7,
    )
    medium = _finding()
    low = _finding(
        category="content_language", severity=Severity.LOW, title="Vague error copy",
        path=None, line=None,
    )
    outcome = _outcome(
        [high, medium, low],
        [
            _assessment("intent_fidelity", "no_findings"),
            _assessment("pathway_completeness", "findings"),
            _assessment("content_language", "findings"),
            _assessment("resilience", "not_evaluated"),
            _assessment("accessibility", "findings"),
        ],
    )
    pull = PullRequest(
        repository="acme/app", number=4, title="Delete views", body="",
        base_sha="base1234567890", head_sha="head1234567890",
        clone_url="https://github.test/acme/app.git",
    )

    report = render_pr_summary(outcome, pull)

    # Headline: the worst severity sets the colour; high is red, not a failed check.
    assert "## 🔴 PX Review · 3 findings · check passed" in report
    assert "The check fails only on `blocking` findings (`block_on` in `.pxreview.yml`)." in report
    assert "Highest severity here: **high**." in report
    # One row per category, coloured, with a severity count where there are findings.
    assert "| 🟢 | 1. Intent fidelity | No finding · About intent_fidelity. |" in report
    assert "| 🟡 | 5. Pathway completeness | **1 medium** · About pathway_completeness. |" in report
    assert "| 🟡 | 6. Content & language | **1 low** ·" in report
    assert "| ⚪ | 7. Resilience | Not evaluated · About resilience. |" in report
    assert "| 🔴 | 8. Accessibility | **1 high** ·" in report
    # Findings are grouped under their category, in taxonomy order.
    assert report.index("### 🟡 5. Pathway completeness · 1 medium") < report.index(
        "### 🟡 6. Content & language · 1 low"
    ) < report.index("### 🔴 8. Accessibility · 1 high")
    assert "- **[medium] Delete has no recovery path** · `app/ViewRow.tsx:42`" in report
    assert "- **[low] Vague error copy**\n" in report          # feature-level: no location
    assert "**Fix:** Use the existing undo toast after deletion." in report
    # One prompt hands every finding to a coding agent.
    assert "<summary><b>Prompt for a coding agent</b> · fixes all 3 findings</summary>" in report
    assert (
        "Fix the following PX Review findings in acme/app (pull request #4, head head12345678)."
        in report
    )
    assert "1. [high] Accessibility: Icon button is unnamed" in report
    assert "2. [medium] Pathway completeness: Delete has no recovery path" in report
    assert "   Where: app/ViewRow.tsx:42" in report
    assert "   Where: feature-level, not one line" in report
    assert "   Fix: Use the existing undo toast after deletion." in report


def test_report_colours_and_check_line_follow_policy_and_conclusion():
    blocking = _finding(severity=Severity.BLOCKING, title="Delete cannot be reached")
    failed = _outcome(
        [blocking],
        [_assessment("pathway_completeness", "findings")],
        conclusion="failure",
        block_on=(Severity.BLOCKING, Severity.HIGH),
    )
    report = render_check_summary(failed)
    assert "## 🔴 PX Review · 1 finding · check failed" in report
    assert "The check fails only on `blocking`, `high` findings" in report

    clean = _outcome(
        [],
        [_assessment("intent_fidelity", "no_findings"), _assessment("resilience", "not_evaluated")],
        conclusion="success",
        block_on=(),
    )
    report = render_check_summary(clean)
    assert "## 🟢 PX Review · 0 findings · check passed" in report
    assert "The check never fails on findings" in report
    assert "No high-confidence PX findings" in report
    assert "Prompt for a coding agent" not in report

    skipped = _outcome(
        [], [], conclusion="success", skipped=True, skip_reason="No UI files changed."
    )
    report = render_check_summary(skipped)
    assert "## ⚪ PX Review · skipped" in report
    assert "Skipped: No UI files changed." in report
    assert "block_on" not in report


def test_agent_prompts_cannot_break_out_of_their_fence_or_mention_anyone():
    finding = _finding(
        title="Ping @team ``` now",
        body="Body with ``` a fence and a <!-- comment -->.",
    )
    outcome = _outcome([finding], [_assessment("pathway_completeness", "findings")])
    for text in (render_check_summary(outcome), render_inline_comment(finding)):
        fenced = text.split("```text", 1)[1].split("```", 1)[0]
        assert "'''" in fenced and "@​team" in fenced
        assert "@team" not in text and "<!-- comment" not in text
