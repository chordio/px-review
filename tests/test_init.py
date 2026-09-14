from pathlib import Path

from pxreview.cli import parser
from pxreview.init_repo import init_product_repo, looks_like_px_review_source


def test_init_writes_policy_workflow_and_agents(tmp_path: Path):
    actions = init_product_repo(tmp_path)
    assert (tmp_path / ".pxreview.yml").is_file()
    assert (tmp_path / ".github" / "workflows" / "px-review.yml").is_file()
    agents = (tmp_path / "AGENTS.md").read_text()
    assert "github.com/chordio/px-review" in agents
    workflow = (tmp_path / ".github" / "workflows" / "px-review.yml").read_text()
    assert "uvx --from git+https://github.com/chordio/px-review@main" in workflow
    # Manual runs, a report on the run's summary page, and a clear error when
    # the secret is missing: what every install needed on its first day.
    assert "workflow_dispatch:" in workflow
    assert "GITHUB_STEP_SUMMARY" in workflow
    assert "::error title=PX Review needs a key::" in workflow
    assert "github.event.pull_request.base.sha || 'origin/main'" in workflow
    assert "shell: bash" in workflow            # pipefail, so tee cannot hide a failure
    # Node 24 actions: checkout@v4 and setup-uv@v6 and below print a Node 20
    # deprecation warning on every run.
    assert "actions/checkout@v5" in workflow and "astral-sh/setup-uv@v7" in workflow
    # Findings land on the pull request with the repository's own token.
    assert "pull-requests: write" in workflow
    assert "GITHUB_TOKEN: ${{ github.token }}" in workflow
    assert '${PR_NUMBER:+--pull "$PR_NUMBER"}' in workflow
    policy = (tmp_path / ".pxreview.yml").read_text()
    assert "`**/` means zero or more directories" in policy
    assert any(a.startswith("write") for a in actions)


def test_init_does_not_overwrite_without_force(tmp_path: Path):
    init_product_repo(tmp_path)
    (tmp_path / ".pxreview.yml").write_text("include: []\n")
    actions = init_product_repo(tmp_path)
    assert (tmp_path / ".pxreview.yml").read_text() == "include: []\n"
    assert any("skip" in a and ".pxreview.yml" in a for a in actions)


def test_init_refuses_source_repo(monkeypatch, capsys):
    source = Path(__file__).resolve().parents[1]
    assert looks_like_px_review_source(source)
    args = parser().parse_args(["init", "--repo", str(source)])
    assert args.func(args) == 2
    assert "product app" in capsys.readouterr().out


def test_init_reports_an_outdated_workflow_and_updates_only_that(tmp_path: Path):
    """An install from before PR comments existed: only the workflow needs replacing."""
    old_workflow = "name: PX Review\non: [pull_request]\n"
    workflow = tmp_path / ".github" / "workflows" / "px-review.yml"
    workflow.parent.mkdir(parents=True)
    workflow.write_text(old_workflow)
    (tmp_path / ".pxreview.yml").write_text("include: []\n")
    (tmp_path / "AGENTS.md").write_text("# App\n")

    actions = init_product_repo(tmp_path)
    assert workflow.read_text() == old_workflow
    assert any("outdated" in a and "--update-workflow" in a for a in actions)

    actions = init_product_repo(tmp_path, update_workflow=True)
    assert any(a.startswith("write") and "px-review.yml" in a for a in actions)
    assert "--pull" in workflow.read_text()
    assert (tmp_path / ".pxreview.yml").read_text() == "include: []\n"  # untouched
    assert "PX Review" in (tmp_path / "AGENTS.md").read_text()  # appended, not replaced

    actions = init_product_repo(tmp_path)
    assert any("already exists, current" in a for a in actions)

    args = parser().parse_args(["init", "--repo", str(tmp_path), "--update-workflow"])
    assert args.update_workflow is True
