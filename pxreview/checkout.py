from __future__ import annotations

import base64
import os
import subprocess
import tempfile
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path


class CheckoutError(RuntimeError):
    pass


def _run(repo_root: Path, env: dict[str, str], *args: str) -> None:
    result = subprocess.run(
        ["git", *args],
        cwd=repo_root,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        raise CheckoutError(f"git {args[0]} failed: {result.stderr.strip()}")


@contextmanager
def checkout_pull(
    repository: str,
    token: str,
    base_sha: str,
    head_sha: str,
    pull_number: int | None = None,
) -> Iterator[Path]:
    """Create a detached checkout without placing the installation token in a URL."""
    with tempfile.TemporaryDirectory(prefix="px-review-") as tmp:
        root = Path(tmp)
        auth = base64.b64encode(f"x-access-token:{token}".encode()).decode()
        env = os.environ.copy()
        env.update(
            {
                "GIT_TERMINAL_PROMPT": "0",
                "GIT_CONFIG_GLOBAL": os.devnull,
                "GIT_CONFIG_NOSYSTEM": "1",
                "GIT_CONFIG_COUNT": "1",
                "GIT_CONFIG_KEY_0": "http.https://github.com/.extraheader",
                "GIT_CONFIG_VALUE_0": f"AUTHORIZATION: basic {auth}",
            }
        )
        _run(root, env, "init", "--quiet")
        _run(
            root,
            env,
            "remote",
            "add",
            "origin",
            f"https://github.com/{repository}.git",
        )
        for sha in dict.fromkeys((base_sha, head_sha)):
            try:
                _run(
                    root,
                    env,
                    "fetch",
                    "--quiet",
                    "--no-tags",
                    "--depth=1",
                    "origin",
                    sha,
                )
            except CheckoutError:
                if sha != head_sha or pull_number is None:
                    raise
                # A fork's head SHA is not necessarily advertised by the base
                # repository, but GitHub exposes the pull ref there.
                _run(
                    root,
                    env,
                    "fetch",
                    "--quiet",
                    "--no-tags",
                    "--depth=1",
                    "origin",
                    f"refs/pull/{pull_number}/head",
                )
        _run(root, env, "-c", "advice.detachedHead=false", "checkout", "--quiet", head_sha)
        yield root
