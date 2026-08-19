import json
import subprocess
from pathlib import Path

from pxreview.cli import _demo, main, parser


def _git(repo: Path, *args: str) -> None:
    subprocess.run(["git", *args], cwd=repo, check=True, capture_output=True)


def test_local_cli_runs_end_to_end_with_fixture(
    tmp_path: Path, monkeypatch, capsys
):
    _git(tmp_path, "init", "-q")
    _git(tmp_path, "config", "user.email", "test@example.com")
    _git(tmp_path, "config", "user.name", "Test")
    component = tmp_path / "Dialog.tsx"
    component.write_text("export const Dialog = () => null;\n")
    _git(tmp_path, "add", ".")
    _git(tmp_path, "commit", "-qm", "base")
    base = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=tmp_path,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()
    component.write_text(
        "export const Dialog = () => <button>Delete</button>;\n"
    )
    _git(tmp_path, "add", ".")
    _git(tmp_path, "commit", "-qm", "head")
    fixture = tmp_path / "review.json"
    fixture.write_text(
        json.dumps(
            {
                "summary": "The destructive path needs a recovery affordance.",
                "findings": [
                    {
                        "category": "pathway_completeness",
                        "severity": "high",
                        "title": "Delete has no recovery path",
                        "body": "The new destructive action has no cancel or undo path.",
                        "recommendation": "Use the existing undo pattern after deletion.",
                        "path": "Dialog.tsx",
                        "line": 1,
                        "confidence": 0.95,
                        "evidence": ["The changed line adds an immediate delete action."],
                    }
                ],
                "categories": [
                    {
                        "category": "pathway_completeness",
                        "status": "findings",
                        "summary": "Deletion has no way back.",
                    }
                ],
            }
        )
    )
    monkeypatch.setattr(
        "sys.argv",
        [
            "px-review",
            "local",
            "--repo",
            str(tmp_path),
            "--base",
            base,
            "--head",
            "HEAD",
            "--fixture",
            str(fixture),
        ],
    )

    try:
        main()
    except SystemExit as exit:
        assert exit.code == 0

    output = capsys.readouterr().out
    assert "Delete has no recovery path" in output
    assert "`Dialog.tsx:1`" in output
    assert "not a PX-bench score" in output


def test_demo_command_is_registered_and_assets_exist():
    args = parser().parse_args(["demo", "--no-open", "--port", "4317"])
    assert args.func is _demo
    assert args.port == 4317
    assert args.no_open is True

    demo_root = Path(__file__).parents[1] / "pxreview" / "demo"
    html = demo_root.joinpath("index.html").read_text()
    assert "Automatic review queued" in html
    assert "window.setTimeout(runReview" in html
    assert "Review receipt" in html
