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
