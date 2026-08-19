from __future__ import annotations

from pathlib import Path

from .config import ReviewConfig
from .diffing import head_file
from .models import DiffBundle


def _safe_repo_file(repo_root: Path, candidate: Path) -> bool:
    try:
        resolved = candidate.resolve()
        resolved.relative_to(repo_root.resolve())
    except (OSError, ValueError):
        return False
    return (
        candidate.is_file()
        and ".git" not in candidate.parts
        and candidate.stat().st_size <= 1_000_000
    )


def _read_text(path: Path, max_chars: int) -> str | None:
    try:
        text = path.read_text()
    except (OSError, UnicodeDecodeError):
        return None
    if len(text) <= max_chars:
        return text
    return text[:max_chars] + "\n… [truncated by PX review]"


def collect_documents(
    repo_root: Path,
    diff: DiffBundle,
    config: ReviewConfig,
) -> tuple[tuple[str, str], ...]:
    """Collect bounded product context from explicit docs and changed head files."""
    candidates: list[tuple[str, str]] = []
    seen: set[str] = set()
    remaining = config.max_context_chars

    def add(path: str, text: str | None) -> None:
        nonlocal remaining
        if not text or path in seen or remaining <= 0:
            return
        clipped = text[: min(config.max_file_chars, remaining)]
        if len(clipped) < len(text):
            clipped += "\n… [truncated by PX review]"
        candidates.append((path, clipped))
        seen.add(path)
        remaining -= len(clipped)

    # Explicit briefs get first claim on the context budget.
    for pattern in config.brief:
        for path in sorted(repo_root.glob(pattern)):
            if _safe_repo_file(repo_root, path):
                add(path.relative_to(repo_root).as_posix(), _read_text(path, config.max_file_chars))

    # The final form of changed files helps the model reason about render guards,
    # component composition, and local code that a unified hunk can omit.
    for changed in diff.files:
        if changed.status != "D":
            add(
                changed.path,
                head_file(repo_root, diff.head_sha, changed.path),
            )

    # Repository conventions and design-system sources fill the remaining budget.
    for pattern in config.context:
        for path in sorted(repo_root.glob(pattern)):
            if _safe_repo_file(repo_root, path):
                add(path.relative_to(repo_root).as_posix(), _read_text(path, config.max_file_chars))

    return tuple(candidates)

