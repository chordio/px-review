import json
import subprocess
from pathlib import Path

import pytest

from pxreview.cli import BUILTIN_FIXTURE, _actions_pull_number, _demo, _files, main, parser


@pytest.fixture(autouse=True)
def _outside_github_actions(monkeypatch):
    """The CLI reads these to recognise an outdated workflow run. Tests that
    want that set them on purpose; nothing leaks in from a CI job running
    this suite."""
    for name in (
        "GITHUB_ACTIONS", "GITHUB_EVENT_NAME", "GITHUB_EVENT_PATH", "GITHUB_REF",
        "GITHUB_STEP_SUMMARY",
    ):
        monkeypatch.delenv(name, raising=False)


def _git(repo: Path, *args: str) -> None:
    subprocess.run(["git", *args], cwd=repo, check=True, capture_output=True)


def test_local_cli_runs_end_to_end_with_fixture(
    tmp_path: Path, monkeypatch, capsys
):
    _git(tmp_path, "init", "-q")
    _git(tmp_path, "config", "user.email", "test@example.com")
    _git(tmp_path, "config", "user.name", "Test")
    component = tmp_path / "Dialog.tsx"
    component.write_text("export const Dialog = () => null;\n")
    _git(tmp_path, "add", ".")
    _git(tmp_path, "commit", "-qm", "base")
    base = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=tmp_path,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()
    component.write_text(
        "export const Dialog = () => <button>Delete</button>;\n"
    )
    _git(tmp_path, "add", ".")
    _git(tmp_path, "commit", "-qm", "head")
    fixture = tmp_path / "review.json"
    fixture.write_text(
        json.dumps(
            {
                "summary": "The destructive path needs a recovery affordance.",
                "findings": [
                    {
                        "category": "pathway_completeness",
                        "severity": "high",
                        "title": "Delete has no recovery path",
                        "body": "The new destructive action has no cancel or undo path.",
                        "recommendation": "Use the existing undo pattern after deletion.",
                        "path": "Dialog.tsx",
                        "line": 1,
                        "confidence": 0.95,
                        "evidence": ["The changed line adds an immediate delete action."],
                    }
                ],
                "categories": [
                    {
                        "category": "pathway_completeness",
                        "status": "findings",
                        "summary": "Deletion has no way back.",
                    }
                ],
            }
        )
    )
    monkeypatch.setattr(
        "sys.argv",
        [
            "px-review",
            "local",
            "--repo",
            str(tmp_path),
            "--base",
            base,
            "--head",
            "HEAD",
            "--fixture",
            str(fixture),
        ],
    )

    try:
        main()
    except SystemExit as exit:
        assert exit.code == 0

    output = capsys.readouterr().out
    assert "Delete has no recovery path" in output
    assert "`Dialog.tsx:1`" in output
    assert "not a PX-bench score" in output


def _repo_with_one_change(tmp_path: Path) -> str:
    _git(tmp_path, "init", "-q")
    _git(tmp_path, "config", "user.email", "test@example.com")
    _git(tmp_path, "config", "user.name", "Test")
    (tmp_path / "Card.tsx").write_text("export const Card = () => null;\n")
    (tmp_path / "worker.py").write_text("VALUE = 1\n")
    _git(tmp_path, "add", ".")
    _git(tmp_path, "commit", "-qm", "base")
    base = subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=tmp_path, check=True, capture_output=True, text=True
    ).stdout.strip()
    (tmp_path / "Card.tsx").write_text("export const Card = () => <button>Go</button>;\n")
    (tmp_path / "worker.py").write_text("VALUE = 2\n")
    _git(tmp_path, "add", ".")
    _git(tmp_path, "commit", "-qm", "head")
    return base


def test_builtin_fixture_runs_the_pipeline_without_a_key(tmp_path: Path, monkeypatch, capsys):
    """The no-credentials smoke test the README and skill point at."""
    assert BUILTIN_FIXTURE.is_file()
    base = _repo_with_one_change(tmp_path)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.setattr(
        "sys.argv",
        ["px-review", "local", "--repo", str(tmp_path), "--base", base, "--fixture", "builtin"],
    )
    try:
        main()
    except SystemExit as exit:
        assert exit.code == 0
    out = capsys.readouterr().out
    assert "PX Review" in out and "Fixture run" in out
    assert "Model: `fixture`" in out


class _CaptureGitHub:
    """Stands in for pxreview.cli.GitHubClient: records what would be posted."""

    instances: list = []

    def __init__(self, *, api_url="https://api.github.com"):
        self.api_url = api_url
        self.requests = []
        _CaptureGitHub.instances.append(self)

    async def _request(self, method, path, token, *, json=None):
        self.requests.append((method, path, token, json))
        if method == "GET":
            return []                       # no existing comments or fingerprints
        return {"id": 7}

    # the two real methods, unchanged, so the CI path posts what the App posts
    from pxreview.github import GitHubClient as _Real
    _list_pages = _Real._list_pages
    existing_fingerprints = _Real.existing_fingerprints
    publish_review = _Real.publish_review
    upsert_summary_comment = _Real.upsert_summary_comment


def test_local_with_pull_posts_inline_review_and_summary_comment(
    tmp_path: Path, monkeypatch, capsys
):
    """--pull leaves the findings on the PR with the repository token: one review
    with a comment per changed-line finding, and one summary comment."""
    _CaptureGitHub.instances.clear()
    monkeypatch.setattr("pxreview.cli.GitHubClient", _CaptureGitHub)
    monkeypatch.setenv("GITHUB_TOKEN", "ghs_test")
    base = _repo_with_one_change(tmp_path)
    fixture = tmp_path / "review.json"
    fixture.write_text(json.dumps({
        "summary": "One keyboard problem.",
        "findings": [{
            "category": "accessibility", "severity": "medium",
            "title": "Button has no accessible name",
            "body": "The new button renders an icon with no text alternative.",
            "recommendation": "Add an aria-label.",
            "path": "Card.tsx", "line": 1, "confidence": 0.9, "evidence": ["Card.tsx:1"],
        }],
        "categories": [{"category": "accessibility", "status": "findings", "summary": "One."}],
    }))
    args = parser().parse_args([
        "local", "--repo", str(tmp_path), "--base", base, "--fixture", str(fixture),
        "--repository", "acme/app", "--pull", "9", "--title", "Add card",
    ])
    assert args.func(args) == 0
    reqs = _CaptureGitHub.instances[0].requests
    methods = [(m, p) for m, p, _, _ in reqs]
    assert ("GET", "/repos/acme/app/pulls/9/comments?per_page=100&page=1") in methods
    posted = {p: j for m, p, _, j in reqs if m == "POST"}
    review = posted["/repos/acme/app/pulls/9/reviews"]
    assert review["event"] == "COMMENT" and review["comments"][0]["path"] == "Card.tsx"
    assert review["comments"][0]["line"] == 1
    assert "PX · 🟡 Accessibility · medium" in review["comments"][0]["body"]
    assert "Prompt for a coding agent" in review["comments"][0]["body"]
    summary = posted["/repos/acme/app/issues/9/comments"]
    assert "<!-- px-review:summary -->" in summary["body"]
    assert "Button has no accessible name" in summary["body"]
    assert "## 🟡 PX Review · 1 finding · check passed" in summary["body"]
    assert "Fix the following PX Review findings in acme/app (pull request #9" in summary["body"]
    assert "Run workflow" in summary["body"] and "/px review" not in summary["body"]
    assert all(t == "ghs_test" for _, _, t, _ in reqs)
    out = capsys.readouterr().out
    assert "Posted to acme/app#9" in out and "1 new inline comment(s)" in out


def _repo_with_no_ui_change(tmp_path: Path) -> str:
    """Two commits whose diff touches nothing the default policy selects."""
    _git(tmp_path, "init", "-q")
    _git(tmp_path, "config", "user.email", "test@example.com")
    _git(tmp_path, "config", "user.name", "Test")
    (tmp_path / "worker.py").write_text("VALUE = 1\n")
    _git(tmp_path, "add", ".")
    _git(tmp_path, "commit", "-qm", "base")
    base = subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=tmp_path, check=True, capture_output=True, text=True
    ).stdout.strip()
    (tmp_path / "worker.py").write_text("VALUE = 2\n")
    _git(tmp_path, "add", ".")
    _git(tmp_path, "commit", "-qm", "head")
    return base


def _clean_fixture(tmp_path: Path) -> Path:
    fixture = tmp_path / "clean.json"
    fixture.write_text(json.dumps({
        "summary": "The change is consistent with the existing components.",
        "findings": [],
        "categories": [
            {"category": "accessibility", "status": "no_findings", "summary": "Labelled."},
        ],
    }))
    return fixture


def test_local_with_pull_posts_summary_comment_when_green(tmp_path: Path, monkeypatch, capsys):
    """No findings still leaves the PX Review comment, the way Vercel and CodeRabbit
    comment on every pull request: a green run is visible on the PR, not silent.
    Only the inline review is skipped, since there is no line to attach to."""
    _CaptureGitHub.instances.clear()
    monkeypatch.setattr("pxreview.cli.GitHubClient", _CaptureGitHub)
    monkeypatch.setenv("GITHUB_TOKEN", "ghs_test")
    base = _repo_with_one_change(tmp_path)
    args = parser().parse_args([
        "local", "--repo", str(tmp_path), "--base", base,
        "--fixture", str(_clean_fixture(tmp_path)),
        "--repository", "acme/app", "--pull", "9", "--title", "Add card",
    ])
    assert args.func(args) == 0
    reqs = _CaptureGitHub.instances[0].requests
    posted = {p: j for m, p, _, j in reqs if m == "POST"}
    assert "/repos/acme/app/pulls/9/reviews" not in posted
    summary = posted["/repos/acme/app/issues/9/comments"]
    assert "<!-- px-review:summary -->" in summary["body"]
    assert "## 🟢 PX Review · 0 findings · check passed" in summary["body"]
    assert "No high-confidence PX findings in the reviewed change." in summary["body"]
    assert "| 🟢 | 8. Accessibility | No finding · Labelled. |" in summary["body"]
    out = capsys.readouterr().out
    assert "Posted to acme/app#9" in out and "(no findings)" in out
    assert "inline comment" not in out


def test_local_with_pull_posts_summary_comment_when_skipped(tmp_path: Path, monkeypatch, capsys):
    """A diff with no PX-relevant files is still a run, so it still comments."""
    _CaptureGitHub.instances.clear()
    monkeypatch.setattr("pxreview.cli.GitHubClient", _CaptureGitHub)
    monkeypatch.setenv("GITHUB_TOKEN", "ghs_test")
    base = _repo_with_no_ui_change(tmp_path)
    args = parser().parse_args([
        "local", "--repo", str(tmp_path), "--base", base, "--fixture", "builtin",
        "--repository", "acme/app", "--pull", "9",
    ])
    assert args.func(args) == 0
    reqs = _CaptureGitHub.instances[0].requests
    posted = {p: j for m, p, _, j in reqs if m == "POST"}
    assert list(posted) == ["/repos/acme/app/issues/9/comments"]
    body = posted["/repos/acme/app/issues/9/comments"]["body"]
    assert "## ⚪ PX Review · skipped" in body
    assert "No changed files matched" in body
    out = capsys.readouterr().out
    assert "Posted to acme/app#9" in out and "(skipped)" in out


def test_local_with_pull_keeps_summary_when_inline_review_fails(
    tmp_path: Path, monkeypatch, capsys
):
    """The summary comment is posted first and on its own: a failing review call
    (a read-only token, a line GitHub will not accept) warns, and the comment stays."""
    from pxreview.github import GitHubError

    class _ReviewFails(_CaptureGitHub):
        async def publish_review(self, token, pull, outcome):
            raise GitHubError("GitHub POST /reviews failed (403): Resource not accessible")

    _CaptureGitHub.instances.clear()
    monkeypatch.setattr("pxreview.cli.GitHubClient", _ReviewFails)
    monkeypatch.setenv("GITHUB_TOKEN", "ghs_test")
    base = _repo_with_one_change(tmp_path)
    fixture = tmp_path / "review.json"
    fixture.write_text(json.dumps({
        "summary": "One keyboard problem.",
        "findings": [{
            "category": "accessibility", "severity": "medium",
            "title": "Button has no accessible name",
            "body": "The new button renders an icon with no text alternative.",
            "recommendation": "Add an aria-label.",
            "path": "Card.tsx", "line": 1, "confidence": 0.9,
        }],
        "categories": [],
    }))
    args = parser().parse_args([
        "local", "--repo", str(tmp_path), "--base", base, "--fixture", str(fixture),
        "--repository", "acme/app", "--pull", "9",
    ])
    assert args.func(args) == 0
    reqs = _CaptureGitHub.instances[0].requests
    posted = {p: j for m, p, _, j in reqs if m == "POST"}
    assert list(posted) == ["/repos/acme/app/issues/9/comments"]
    assert "Button has no accessible name" in posted["/repos/acme/app/issues/9/comments"]["body"]
    out = capsys.readouterr().out
    assert "Posted to acme/app#9" in out and "(1 finding)" in out
    assert "::warning::PX review: summary comment posted, but the inline review" in out


def test_local_with_pull_but_no_token_warns_and_still_reports(tmp_path: Path, monkeypatch, capsys):
    _CaptureGitHub.instances.clear()
    monkeypatch.setattr("pxreview.cli.GitHubClient", _CaptureGitHub)
    monkeypatch.delenv("GITHUB_TOKEN", raising=False)
    base = _repo_with_one_change(tmp_path)
    args = parser().parse_args([
        "local", "--repo", str(tmp_path), "--base", base, "--fixture", "builtin",
        "--repository", "acme/app", "--pull", "9",
    ])
    assert args.func(args) == 0
    out = capsys.readouterr().out
    assert "PX review" in out and "::warning::" in out and "$GITHUB_TOKEN is empty" in out
    assert not _CaptureGitHub.instances


def test_files_command_lists_selection_with_reasons(tmp_path: Path, capsys):
    base = _repo_with_one_change(tmp_path)
    args = parser().parse_args(["files", "--repo", str(tmp_path), "--base", base])
    assert args.func is _files
    assert args.func(args) == 0
    out = capsys.readouterr().out
    assert "keep          M  Card.tsx" in out
    assert "not-included  M  worker.py" in out
    assert "1 of 2 changed files selected by the default policy." in out
    # A policy that selects nothing says so and points at the glob rules.
    (tmp_path / ".pxreview.yml").write_text('include:\n  - "src/**/*.tsx"\n')
    args = parser().parse_args(["files", "--repo", str(tmp_path), "--base", base])
    args.func(args)
    out = capsys.readouterr().out
    assert "0 of 2 changed files selected by .pxreview.yml." in out
    assert "Nothing selected" in out and "`**/`" in out


def test_demo_command_is_registered_and_assets_exist():
    args = parser().parse_args(["demo", "--no-open", "--port", "4317"])
    assert args.func is _demo
    assert args.port == 4317
    assert args.no_open is True

    demo_root = Path(__file__).parents[1] / "pxreview" / "demo"
    html = demo_root.joinpath("index.html").read_text()
    assert "Automatic review queued" in html
    assert "window.setTimeout(runReview" in html
    assert "Review receipt" in html


def _pull_request_job(monkeypatch, tmp_path: Path, *, number: int | None = 46) -> Path:
    """What a pull_request job looks like from inside: Actions, the event, and
    the step-summary file GitHub gives every job. Returns that file."""
    monkeypatch.setenv("GITHUB_ACTIONS", "true")
    monkeypatch.setenv("GITHUB_EVENT_NAME", "pull_request")
    summary = tmp_path / "step-summary.md"
    summary.write_text("")
    monkeypatch.setenv("GITHUB_STEP_SUMMARY", str(summary))
    if number is not None:
        event = tmp_path / "event.json"
        event.write_text(json.dumps({"pull_request": {"number": number}}))
        monkeypatch.setenv("GITHUB_EVENT_PATH", str(event))
    return summary


def test_outdated_workflow_run_warns_and_puts_the_report_on_the_summary_page(
    tmp_path: Path, monkeypatch, capsys
):
    """The August workflow runs the CLI on a pull request without --pull, so the
    check is green and the pull request silent. The run must say so: one warning
    annotation naming the upgrade command, and the report on the run's summary
    page, not only in the log. The exit code is unchanged."""
    summary = _pull_request_job(monkeypatch, tmp_path)
    base = _repo_with_one_change(tmp_path)
    args = parser().parse_args([
        "local", "--repo", str(tmp_path), "--base", base, "--fixture", "builtin",
        "--repository", "acme/app", "--title", "Add card",
    ])
    assert args.func(args) == 0
    out = capsys.readouterr().out
    assert "PX Review" in out and "Model: `fixture`" in out       # the log still has the report
    warnings = [line for line in out.splitlines() if line.startswith("::warning")]
    assert len(warnings) == 1
    assert warnings[0].startswith("::warning title=PX Review workflow is outdated::")
    assert "pull request #46" in warnings[0]
    assert "px-review init --repo . --update-workflow" in warnings[0]
    page = summary.read_text()
    assert page.startswith("> **This workflow predates PX Review's pull-request comments.**")
    assert "--update-workflow" in page
    assert "PX Review · 1 finding · check passed" in page and "Model: `fixture`" in page


def test_outdated_workflow_falls_back_to_the_ref_for_the_pull_number(monkeypatch, tmp_path):
    assert _actions_pull_number() is None
    monkeypatch.setenv("GITHUB_REF", "refs/pull/7/merge")
    assert _actions_pull_number() == 7
    broken = tmp_path / "event.json"
    broken.write_text("{not json")
    monkeypatch.setenv("GITHUB_EVENT_PATH", str(broken))
    assert _actions_pull_number() == 7                             # unreadable payload, ref wins
    _pull_request_job(monkeypatch, tmp_path, number=46)
    assert _actions_pull_number() == 46                            # payload wins over the ref


@pytest.mark.parametrize(
    "env",
    [
        {},                                                        # a developer's terminal
        {"GITHUB_ACTIONS": "true", "GITHUB_EVENT_NAME": "workflow_dispatch"},  # Run workflow
    ],
)
def test_local_without_pull_is_quiet_outside_a_pull_request_job(
    tmp_path: Path, monkeypatch, capsys, env
):
    """No annotation and nothing appended to the summary file: the current
    template's manual run tees stdout into it already, and a terminal run has
    nothing to upgrade."""
    summary = tmp_path / "step-summary.md"
    summary.write_text("")
    monkeypatch.setenv("GITHUB_STEP_SUMMARY", str(summary))
    for name, value in env.items():
        monkeypatch.setenv(name, value)
    base = _repo_with_one_change(tmp_path)
    args = parser().parse_args(
        ["local", "--repo", str(tmp_path), "--base", base, "--fixture", "builtin"]
    )
    assert args.func(args) == 0
    assert "::warning" not in capsys.readouterr().out
    assert summary.read_text() == ""


def test_current_workflow_with_pull_gets_no_outdated_warning(tmp_path: Path, monkeypatch, capsys):
    """--pull inside a pull_request job is the current workflow: it posts, and
    the outdated-workflow path stays out of the way."""
    _CaptureGitHub.instances.clear()
    monkeypatch.setattr("pxreview.cli.GitHubClient", _CaptureGitHub)
    monkeypatch.setenv("GITHUB_TOKEN", "ghs_test")
    summary = _pull_request_job(monkeypatch, tmp_path)
    base = _repo_with_one_change(tmp_path)
    args = parser().parse_args([
        "local", "--repo", str(tmp_path), "--base", base, "--fixture", "builtin",
        "--repository", "acme/app", "--pull", "46",
    ])
    assert args.func(args) == 0
    out = capsys.readouterr().out
    assert "Posted to acme/app#46" in out
    assert "outdated" not in out and "::warning" not in out
    assert summary.read_text() == ""
