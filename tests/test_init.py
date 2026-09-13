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
