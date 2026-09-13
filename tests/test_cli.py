import json
import subprocess
from pathlib import Path

from pxreview.cli import BUILTIN_FIXTURE, _demo, _files, main, parser


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
    assert "PX review" in out and "Fixture run" in out
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
    assert "PX · Accessibility · medium" in review["comments"][0]["body"]
    summary = posted["/repos/acme/app/issues/9/comments"]
    assert "<!-- px-review:summary -->" in summary["body"]
    assert "Button has no accessible name" in summary["body"]
    assert "Run workflow" in summary["body"] and "/px review" not in summary["body"]
    assert all(t == "ghs_test" for _, _, t, _ in reqs)
    out = capsys.readouterr().out
    assert "Posted to acme/app#9" in out and "1 new inline comment(s)" in out


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
