from pathlib import Path

from pxreview.config import ReviewConfig
from pxreview.diffing import build_diff, matches_path, parse_changed_lines, resolve_ref

PATCH = """\
diff --git a/app/Card.tsx b/app/Card.tsx
index 111..222 100644
--- a/app/Card.tsx
+++ b/app/Card.tsx
@@ -10,3 +10,5 @@
 keep
-old
+new
+another
 tail
"""


def test_parse_changed_lines_returns_right_side_additions():
    assert parse_changed_lines(PATCH) == {11, 12}


def test_parse_changed_lines_keeps_added_content_that_begins_with_pluses():
    patch = """\
diff --git a/a.ts b/a.ts
--- a/a.ts
+++ b/a.ts
@@ -0,0 +1 @@
+++literal
"""
    assert parse_changed_lines(patch) == {1}


def test_double_star_patterns_match_root_and_nested_paths():
    assert matches_path("Card.tsx", ["**/*.tsx"])
    assert matches_path("app/Card.tsx", ["**/*.tsx"])
    assert not matches_path("app/Card.py", ["**/*.tsx"])


def _git(repo: Path, *args: str) -> None:
    import subprocess

    subprocess.run(["git", *args], cwd=repo, check=True, capture_output=True)


def test_build_diff_filters_non_px_files(tmp_path: Path):
    _git(tmp_path, "init", "-q")
    _git(tmp_path, "config", "user.email", "test@example.com")
    _git(tmp_path, "config", "user.name", "Test")
    (tmp_path / "Card.tsx").write_text("export const Card = () => null;\n")
    (tmp_path / "worker.py").write_text("VALUE = 1\n")
    _git(tmp_path, "add", ".")
    _git(tmp_path, "commit", "-qm", "base")
    base = resolve_ref(tmp_path, "HEAD")
    (tmp_path / "Card.tsx").write_text("export const Card = () => <button>Save</button>;\n")
    (tmp_path / "worker.py").write_text("VALUE = 2\n")
    _git(tmp_path, "add", ".")
    _git(tmp_path, "commit", "-qm", "head")
    head = resolve_ref(tmp_path, "HEAD")

    diff = build_diff(tmp_path, base, head, ReviewConfig())

    assert diff.changed_paths == ("Card.tsx",)
    assert diff.files[0].changed_lines == {1}
