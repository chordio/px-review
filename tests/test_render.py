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
    assert "PX · Accessibility · high" in inline
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
