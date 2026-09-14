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


# The workflow gained these after the first release. An installed workflow
# missing any of them predates PR comments on the pull request, so its report
# only reaches the job log.
_WORKFLOW_MARKERS = ("--pull", "pull-requests: write", "GITHUB_STEP_SUMMARY")


def workflow_is_current(text: str) -> bool:
    return all(marker in text for marker in _WORKFLOW_MARKERS)


def init_product_repo(
    repo: Path, *, force: bool = False, update_workflow: bool = False
) -> list[str]:
    """Install PX Review policy, PR workflow, and an AGENTS.md pointer.

    `update_workflow` rewrites only the workflow file, so an install from an
    earlier release picks up PR comments and current actions without losing a
    customised policy or AGENTS.md.
    """
    repo = repo.resolve()
    actions: list[str] = []
    policy = (TEMPLATE_DIR / "pxreview.yml").read_text()
    workflow = (TEMPLATE_DIR / "github-workflow.yml").read_text()
    snippet = (TEMPLATE_DIR / "agents-snippet.md").read_text().strip() + "\n"

    actions.append(_write(repo / POLICY_NAME, policy, force=force))
    workflow_path = repo / WORKFLOW_PATH
    if workflow_path.exists() and not (force or update_workflow):
        state = "current" if workflow_is_current(workflow_path.read_text()) else (
            "outdated: findings stay in the job log; rerun with --update-workflow"
        )
        actions.append(f"skip {workflow_path} (already exists, {state})")
    else:
        actions.append(_write(workflow_path, workflow, force=True))

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
