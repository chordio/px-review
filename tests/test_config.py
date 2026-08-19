import subprocess
from pathlib import Path

from pxreview.config import load_config


def _git(repo: Path, *args: str) -> str:
    return subprocess.run(
        ["git", *args],
        cwd=repo,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()


def test_service_can_load_policy_from_base_ref(tmp_path: Path):
    _git(tmp_path, "init", "-q")
    _git(tmp_path, "config", "user.email", "test@example.com")
    _git(tmp_path, "config", "user.name", "Test")
    (tmp_path / ".pxreview.yml").write_text(
        "model: gpt-5.6-terra\nreview_forks: false\n"
    )
    _git(tmp_path, "add", ".")
    _git(tmp_path, "commit", "-qm", "base policy")
    base = _git(tmp_path, "rev-parse", "HEAD")

    # The proposed head tries to widen its own authority and spend.
    (tmp_path / ".pxreview.yml").write_text(
        "model: gpt-5.6-sol\nreasoning_effort: max\nreview_forks: true\n"
    )
    _git(tmp_path, "add", ".")
    _git(tmp_path, "commit", "-qm", "untrusted policy change")

    trusted = load_config(tmp_path, ref=base)
    working_tree = load_config(tmp_path)

    assert trusted.model == "gpt-5.6-terra"
    assert trusted.reasoning_effort == "medium"
    assert trusted.review_forks is False
    assert working_tree.model == "gpt-5.6-sol"
    assert working_tree.review_forks is True
