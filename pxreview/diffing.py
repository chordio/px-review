from __future__ import annotations

import fnmatch
import re
import subprocess
from pathlib import Path

from .config import ReviewConfig
from .models import ChangedFile, DiffBundle

_HUNK_RE = re.compile(r"^@@ -\d+(?:,\d+)? \+(?P<start>\d+)(?:,(?P<count>\d+))? @@")


class GitError(RuntimeError):
    pass


def _git(repo_root: Path, *args: str, binary: bool = False) -> str | bytes:
    result = subprocess.run(
        ["git", *args],
        cwd=repo_root,
        capture_output=True,
        text=not binary,
        check=False,
    )
    if result.returncode != 0:
        stderr = result.stderr if isinstance(result.stderr, str) else result.stderr.decode(
            "utf-8", "replace"
        )
        raise GitError(f"git {' '.join(args)} failed: {stderr.strip()}")
    return result.stdout


def matches_path(path: str, patterns: list[str]) -> bool:
    return any(
        fnmatch.fnmatchcase(path, pattern)
        or (pattern.startswith("**/") and fnmatch.fnmatchcase(path, pattern[3:]))
        for pattern in patterns
    )


def is_relevant_path(path: str, config: ReviewConfig) -> bool:
    return matches_path(path, config.include) and not matches_path(path, config.exclude)


def parse_changed_lines(patch: str) -> frozenset[int]:
    """Return commentable RIGHT-side line numbers from a unified diff."""
    changed: set[int] = set()
    right_line: int | None = None
    for raw in patch.splitlines():
        if raw.startswith("diff --git "):
            right_line = None
            continue
        hunk = _HUNK_RE.match(raw)
        if hunk:
            right_line = int(hunk.group("start"))
            continue
        if right_line is None:
            continue
        if raw.startswith("+"):
            changed.add(right_line)
            right_line += 1
        elif raw.startswith("-"):
            continue
        elif raw.startswith(" "):
            right_line += 1
        elif raw.startswith("\\ No newline"):
            continue
    return frozenset(changed)


def build_diff(
    repo_root: Path,
    base_sha: str,
    head_sha: str,
    config: ReviewConfig,
) -> DiffBundle:
    name_status = str(
        _git(repo_root, "diff", "--name-status", "--no-renames", base_sha, head_sha, "--")
    )
    files: list[ChangedFile] = []
    for raw in name_status.splitlines():
        if not raw.strip():
            continue
        parts = raw.split("\t", 1)
        if len(parts) != 2:
            continue
        status, path = parts
        if not is_relevant_path(path, config):
            continue
        patch = str(
            _git(
                repo_root,
                "diff",
                "--unified=40",
                "--no-renames",
                "--no-color",
                base_sha,
                head_sha,
                "--",
                path,
            )
        )
        files.append(
            ChangedFile(
                path=path,
                status=status[:1],
                patch=patch,
                changed_lines=parse_changed_lines(patch),
            )
        )
    return DiffBundle(base_sha=base_sha, head_sha=head_sha, files=tuple(files))


def resolve_ref(repo_root: Path, ref: str) -> str:
    return str(_git(repo_root, "rev-parse", f"{ref}^{{commit}}")).strip()


def head_file(repo_root: Path, head_sha: str, path: str) -> str | None:
    result = subprocess.run(
        ["git", "show", f"{head_sha}:{path}"],
        cwd=repo_root,
        capture_output=True,
        check=False,
    )
    if result.returncode != 0:
        return None
    try:
        return result.stdout.decode("utf-8")
    except UnicodeDecodeError:
        return None
