from pathlib import Path

from pxreview.config import ReviewConfig
from pxreview.diffing import (
    build_diff,
    matches_path,
    parse_changed_lines,
    resolve_ref,
    selection,
)

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


def test_double_star_in_the_middle_means_zero_or_more_directories():
    # The case that silently dropped files before: a prefixed pattern and a
    # file directly under the prefix.
    assert matches_path("render/announce.html", ["render/**/*.html"])
    assert matches_path("render/a/b/c.html", ["render/**/*.html"])
    assert not matches_path("other/announce.html", ["render/**/*.html"])
    assert matches_path("site/app/page.tsx", ["site/app/**/*.tsx"])
    assert matches_path("site/app/terms/page.tsx", ["site/app/**/*.tsx"])
    assert matches_path("a/components/x/y.tsx", ["**/components/**"])
    assert matches_path("components/y.tsx", ["**/components/**"])
    assert not matches_path("componentsx/y.tsx", ["**/components/**"])


def test_star_still_crosses_directories_as_fnmatch_did():
    # Compatibility: policies written against the old matcher keep working.
    assert matches_path("src/a/b.css", ["src/*.css"])
    assert matches_path("src/a/b.css", ["*.css"])
    assert matches_path("dist/x/y.js", ["**/dist/**"])
    assert matches_path("node_modules/pkg/index.js", ["**/node_modules/**"])
    assert matches_path("Card.tsx", ["Card.[tj]sx"])
    assert not matches_path("Card.ts", ["**/*.tsx"])


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

    # The dry run explains every changed file, selected or not.
    rows = selection(tmp_path, base, head, ReviewConfig())
    assert rows == [("keep", "M", "Card.tsx"), ("not-included", "M", "worker.py")]
    rows = selection(tmp_path, base, head, ReviewConfig(exclude=["Card.tsx"]))
    assert rows[0] == ("excluded", "M", "Card.tsx")
