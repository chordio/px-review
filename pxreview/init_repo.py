from __future__ import annotations

from pathlib import Path

TEMPLATE_DIR = Path(__file__).resolve().parent / "templates"

POLICY_NAME = ".pxreview.yml"
WORKFLOW_PATH = Path(".github") / "workflows" / "px-review.yml"
AGENTS_NAME = "AGENTS.md"


def looks_like_px_review_source(repo: Path) -> bool:
    pyproject = repo / "pyproject.toml"
    if not (repo / "pxreview" / "cli.py").is_file() or not pyproject.is_file():
        return False
    return 'name = "px-review"' in pyproject.read_text()


def _write(path: Path, content: str, *, force: bool) -> str:
    if path.exists() and not force:
        return f"skip {path} (already exists)"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content)
    return f"write {path}"


def init_product_repo(repo: Path, *, force: bool = False) -> list[str]:
    """Install PX Review policy, PR workflow, and an AGENTS.md pointer."""
    repo = repo.resolve()
    actions: list[str] = []
    policy = (TEMPLATE_DIR / "pxreview.yml").read_text()
    workflow = (TEMPLATE_DIR / "github-workflow.yml").read_text()
    snippet = (TEMPLATE_DIR / "agents-snippet.md").read_text().strip() + "\n"

    actions.append(_write(repo / POLICY_NAME, policy, force=force))
    actions.append(_write(repo / WORKFLOW_PATH, workflow, force=force))

    agents = repo / AGENTS_NAME
    if agents.exists() and "github.com/chordio/px-review" in agents.read_text() and not force:
        actions.append(f"skip {agents} (already points at PX Review)")
    elif agents.exists() and not force:
        existing = agents.read_text().rstrip() + "\n\n"
        agents.write_text(existing + snippet)
        actions.append(f"append {agents}")
    else:
        actions.append(_write(agents, snippet, force=True))
    return actions
