from __future__ import annotations

import argparse
import asyncio
import os
import webbrowser
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from .config import load_config
from .context import collect_documents
from .diffing import build_diff, resolve_ref, selection
from .engine import run_review
from .github import GitHubClient, GitHubError
from .init_repo import init_product_repo, looks_like_px_review_source
from .models import PullRequest, ReviewContext
from .provider import FixtureReviewProvider, OpenAIReviewProvider
from .render import CI_RERUN_HINT, render_check_summary
from .taxonomy import CATEGORIES, TAXONOMY_VERSION

# The packaged fixture: a valid ReviewDraft, so `px-review local --fixture
# builtin` exercises the whole pipeline (policy, diff, context, rendering)
# with no key and no network. Its one finding names a file that will not be
# in the diff, so it prints summary-only; the point is that everything runs.
BUILTIN_FIXTURE = Path(__file__).with_name("templates") / "review-fixture.json"


def _fixture_path(arg: str) -> Path:
    return BUILTIN_FIXTURE if arg == "builtin" else Path(arg)


def _files(args: argparse.Namespace) -> int:
    """Dry run: which changed files the policy selects, and why not for the rest."""
    repo_root = Path(args.repo).resolve()
    config = load_config(repo_root)
    base_sha = resolve_ref(repo_root, args.base)
    head_sha = resolve_ref(repo_root, args.head)
    rows = selection(repo_root, base_sha, head_sha, config)
    kept = [r for r in rows if r[0] == "keep"]
    for verdict, status, path in rows:
        print(f"{verdict:<13} {status:<2} {path}")
    print(
        f"\n{len(kept)} of {len(rows)} changed files selected by "
        f"{'.pxreview.yml' if (repo_root / '.pxreview.yml').exists() else 'the default policy'}."
    )
    if rows and not kept:
        print(
            "Nothing selected. Check `include` in .pxreview.yml: `*` crosses directories, "
            "and `**/` means zero or more directories (see README, Policy globs)."
        )
    return 0


def _local(args: argparse.Namespace) -> int:
    repo_root = Path(args.repo).resolve()
    config = load_config(repo_root)
    base_sha = resolve_ref(repo_root, args.base)
    head_sha = resolve_ref(repo_root, args.head)
    diff = build_diff(repo_root, base_sha, head_sha, config)
    context = ReviewContext(
        repo_root=repo_root,
        repository=args.repository or repo_root.name,
        pull_number=None,
        title=args.title,
        body=args.body,
        diff=diff,
        documents=collect_documents(repo_root, diff, config),
    )
    if args.fixture:
        provider = FixtureReviewProvider(_fixture_path(args.fixture))
    else:
        provider = OpenAIReviewProvider(
            model=args.model or config.model,
            api_key=os.environ.get("OPENAI_API_KEY"),
            reasoning_effort=config.reasoning_effort,
        )
    outcome = run_review(context, config, provider)
    rendered = render_check_summary(outcome)
    if args.output:
        Path(args.output).write_text(rendered)
    else:
        print(rendered)
    if args.pull is not None:
        _post_to_pull(args, base_sha, head_sha, outcome)
    return 1 if outcome.conclusion == "failure" else 0


def _post_to_pull(args: argparse.Namespace, base_sha: str, head_sha: str, outcome) -> None:
    """Leave the findings on the pull request, the way the GitHub App does.

    Same two surfaces, same code: one review with a comment on each changed
    line that has a finding (deduplicated on fingerprints, so a re-run after
    a push does not repeat itself), and one persistent summary comment that
    is updated in place. The token comes from an environment variable, never
    an argument, so it cannot land in a process list or a log. A failure to
    post is a warning, not a failed review: the report already printed.
    """
    token = os.environ.get(args.github_token_env or "", "")
    if not args.repository:
        print("::warning::PX review: --pull needs --repository owner/name; nothing posted.")
        return
    if not token:
        print(
            f"::warning::PX review: ${args.github_token_env} is empty; nothing posted to the "
            "pull request. In GitHub Actions set GITHUB_TOKEN: ${{ github.token }} and give "
            "the job `pull-requests: write`."
        )
        return
    pull = PullRequest(
        repository=args.repository,
        number=int(args.pull),
        title=args.title,
        body=args.body,
        base_sha=base_sha,
        head_sha=head_sha,
        clone_url=f"https://github.com/{args.repository}.git",
    )
    client = GitHubClient(api_url=os.environ.get("GITHUB_API_URL", "https://api.github.com"))

    async def post() -> tuple[int, int]:
        inline = await client.publish_review(token, pull, outcome)
        comment_id = await client.upsert_summary_comment(
            token, pull, outcome, rerun_hint=CI_RERUN_HINT
        )
        return inline, comment_id

    try:
        inline, _ = asyncio.run(post())
    except GitHubError as error:
        print(f"::warning::PX review: could not post to the pull request: {error}")
        return
    print(f"\nPosted to {args.repository}#{pull.number}: summary comment updated, "
          f"{inline} new inline comment(s).")


def _taxonomy() -> int:
    print(f"PX taxonomy v{TAXONOMY_VERSION}\n")
    for category in CATEGORIES:
        print(f"{category.number}. {category.name} ({category.id})")
        print(f"   {category.definition}\n")
    return 0


def _serve(args: argparse.Namespace) -> int:
    import uvicorn

    uvicorn.run(
        "pxreview.app:create_app",
        factory=True,
        host=args.host,
        port=args.port,
    )
    return 0


def _demo(args: argparse.Namespace) -> int:
    demo_root = Path(__file__).with_name("demo")
    if not demo_root.joinpath("index.html").is_file():
        raise RuntimeError(f"Demo assets not found at {demo_root}")

    handler = partial(SimpleHTTPRequestHandler, directory=str(demo_root))
    server = ThreadingHTTPServer((args.host, args.port), handler)
    url = f"http://{args.host}:{server.server_port}"
    print(f"PX Review demo ready at {url}")
    print("Press Ctrl-C to stop.")
    if not args.no_open:
        webbrowser.open(url)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nStopping PX Review demo.")
    finally:
        server.server_close()
    return 0


def _init(args: argparse.Namespace) -> int:
    repo = Path(args.repo).resolve()
    if looks_like_px_review_source(repo):
        print(
            "This is the PX Review source repo, not a product app.\n"
            "Pass --repo /path/to/the/frontend/app you want reviewed."
        )
        return 2
    for line in init_product_repo(repo, force=args.force):
        print(line)
    print(
        "\nNext:\n"
        "  1. Check what the policy selects: px-review files --repo .\n"
        "  2. Add repository secret OPENAI_API_KEY\n"
        "  3. Run one review: uvx --from git+https://github.com/chordio/px-review "
        "px-review local --repo .   (no key? add --fixture builtin)\n"
        "  4. Do not deploy the GitHub App unless asked"
    )
    return 0


def parser() -> argparse.ArgumentParser:
    root = argparse.ArgumentParser(
        prog="px-review",
        description="Review pull-request changes through the PX taxonomy.",
    )
    sub = root.add_subparsers(dest="command", required=True)
    local = sub.add_parser("local", help="Review a local git diff.")
    local.add_argument("--repo", default=".")
    local.add_argument("--base", default="origin/main")
    local.add_argument("--head", default="HEAD")
    local.add_argument("--repository")
    local.add_argument("--title", default="Local PX review")
    local.add_argument("--body", default="")
    local.add_argument("--model")
    local.add_argument(
        "--pull",
        type=int,
        help="Pull request number: post the findings there as review comments "
        "(needs --repository and a token in the env var named by --github-token-env).",
    )
    local.add_argument(
        "--github-token-env",
        default="GITHUB_TOKEN",
        help="Environment variable holding the token used with --pull (default GITHUB_TOKEN).",
    )
    local.add_argument(
        "--fixture",
        help="Use a ReviewDraft JSON file instead of an API call; `builtin` for the packaged one.",
    )
    local.add_argument("--output")
    local.set_defaults(func=_local)

    files = sub.add_parser(
        "files",
        help="Dry run: list the changed files the policy selects (no key, no network).",
    )
    files.add_argument("--repo", default=".")
    files.add_argument("--base", default="origin/main")
    files.add_argument("--head", default="HEAD")
    files.set_defaults(func=_files)

    taxonomy = sub.add_parser("taxonomy", help="Print the embedded taxonomy.")
    taxonomy.set_defaults(func=lambda args: _taxonomy())

    serve = sub.add_parser("serve", help="Run the GitHub App webhook service.")
    serve.add_argument("--host", default="0.0.0.0")
    serve.add_argument("--port", type=int, default=8000)
    serve.set_defaults(func=_serve)

    demo = sub.add_parser("demo", help="Run the deterministic product demo.")
    demo.add_argument("--host", default="127.0.0.1")
    demo.add_argument("--port", type=int, default=4173)
    demo.add_argument("--no-open", action="store_true")
    demo.set_defaults(func=_demo)

    init = sub.add_parser(
        "init",
        help="Install PX Review into a frontend product repo (policy + PR workflow).",
    )
    init.add_argument("--repo", default=".")
    init.add_argument(
        "--force",
        action="store_true",
        help="Overwrite existing .pxreview.yml, workflow, and AGENTS.md snippet.",
    )
    init.set_defaults(func=_init)
    return root


def main() -> None:
    args = parser().parse_args()
    raise SystemExit(args.func(args))


if __name__ == "__main__":
    main()
