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


def _glob_regex(pattern: str) -> re.Pattern[str]:
    """Compile one include/exclude pattern.

    fnmatch semantics, kept for compatibility: `*` and `?` match any character,
    slashes included, so `src/*.tsx` matches `src/a/b.tsx`. The one addition is
    that `**/` anywhere in a pattern means "zero or more directories", so
    `src/**/*.tsx` matches `src/Card.tsx` as well as `src/a/Card.tsx`. Under
    plain fnmatch that pattern needed a real subdirectory, and every file at
    the top of `src/` silently fell out of the review.
    """
    chunks = pattern.split("**/")
    bodies = []
    for chunk in chunks:
        translated = fnmatch.translate(chunk)
        # fnmatch.translate wraps the body as "(?s:BODY)\Z"; keep BODY.
        assert translated.startswith("(?s:") and translated.endswith(")\Z")
        bodies.append(translated[4:-3])
    return re.compile("(?s:" + "(?:.*/)?".join(bodies) + ")\Z")


def matches_path(path: str, patterns: list[str]) -> bool:
    return any(_glob_regex(pattern).match(path) for pattern in patterns)


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


def changed_paths(repo_root: Path, base_sha: str, head_sha: str) -> list[tuple[str, str]]:
    """Every (status, path) between the two commits, before policy filtering."""
    name_status = str(
        _git(repo_root, "diff", "--name-status", "--no-renames", base_sha, head_sha, "--")
    )
    out: list[tuple[str, str]] = []
    for raw in name_status.splitlines():
        if not raw.strip():
            continue
        parts = raw.split("\t", 1)
        if len(parts) != 2:
            continue
        out.append((parts[0], parts[1]))
    return out


def selection(
    repo_root: Path, base_sha: str, head_sha: str, config: ReviewConfig
) -> list[tuple[str, str, str]]:
    """(verdict, status, path) per changed file: keep, excluded, or not-included.

    What `px-review files` prints, and the first thing to run after editing
    `.pxreview.yml`: it needs no model and no key, and it is where a glob that
    quietly matches nothing shows up.
    """
    out: list[tuple[str, str, str]] = []
    for status, path in changed_paths(repo_root, base_sha, head_sha):
        if not matches_path(path, config.include):
            verdict = "not-included"
        elif matches_path(path, config.exclude):
            verdict = "excluded"
        else:
            verdict = "keep"
        out.append((verdict, status, path))
    return out


def build_diff(
    repo_root: Path,
    base_sha: str,
    head_sha: str,
    config: ReviewConfig,
) -> DiffBundle:
    files: list[ChangedFile] = []
    for status, path in changed_paths(repo_root, base_sha, head_sha):
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
