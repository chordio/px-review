from __future__ import annotations

import re
import time
from typing import Any

import httpx
import jwt

from .engine import finding_fingerprint
from .models import PullRequest, ReviewOutcome
from .render import (
    SUMMARY_MARKER,
    render_check_summary,
    render_inline_comment,
    render_pr_summary,
    render_review_body,
)


class GitHubError(RuntimeError):
    pass


class GitHubAppAuth:
    def __init__(self, app_id: str, private_key: str, *, api_url: str) -> None:
        self.app_id = app_id
        self.private_key = private_key
        self.api_url = api_url.rstrip("/")

    def app_jwt(self) -> str:
        now = int(time.time())
        return jwt.encode(
            {"iat": now - 60, "exp": now + 9 * 60, "iss": self.app_id},
            self.private_key,
            algorithm="RS256",
        )

    async def installation_token(self, installation_id: int) -> str:
        async with httpx.AsyncClient(timeout=30) as client:
            response = await client.post(
                f"{self.api_url}/app/installations/{installation_id}/access_tokens",
                headers=_headers(self.app_jwt()),
            )
        if response.is_error:
            raise GitHubError(
                f"GitHub installation-token request failed ({response.status_code}): "
                f"{response.text[:500]}"
            )
        return str(response.json()["token"])


def _headers(token: str) -> dict[str, str]:
    return {
        "Accept": "application/vnd.github+json",
        "Authorization": f"Bearer {token}",
        "X-GitHub-Api-Version": "2022-11-28",
        "User-Agent": "px-review/0.1",
    }


class GitHubClient:
    def __init__(self, *, api_url: str = "https://api.github.com") -> None:
        self.api_url = api_url.rstrip("/")

    async def _request(
        self,
        method: str,
        path: str,
        token: str,
        *,
        json: dict[str, Any] | None = None,
    ) -> Any:
        async with httpx.AsyncClient(timeout=45) as client:
            response = await client.request(
                method,
                f"{self.api_url}{path}",
                headers=_headers(token),
                json=json,
            )
        if response.is_error:
            raise GitHubError(
                f"GitHub {method} {path} failed ({response.status_code}): "
                f"{response.text[:1000]}"
            )
        return response.json() if response.content else None

    async def _list_pages(
        self,
        path: str,
        token: str,
        *,
        max_pages: int = 10,
    ) -> list[dict[str, Any]]:
        items: list[dict[str, Any]] = []
        separator = "&" if "?" in path else "?"
        for page in range(1, max_pages + 1):
            page_items = await self._request(
                "GET", f"{path}{separator}per_page=100&page={page}", token
            )
            if not isinstance(page_items, list):
                raise GitHubError(f"GitHub GET {path} did not return a list")
            items.extend(page_items)
            if len(page_items) < 100:
                break
        return items

    async def get_pull(self, token: str, repository: str, number: int) -> PullRequest:
        raw = await self._request(
            "GET", f"/repos/{repository}/pulls/{number}", token
        )
        head_repo = raw["head"].get("repo")
        base_repo = raw["base"]["repo"]
        return PullRequest(
            repository=repository,
            number=number,
            title=raw["title"],
            body=raw.get("body") or "",
            base_sha=raw["base"]["sha"],
            head_sha=raw["head"]["sha"],
            clone_url=base_repo["clone_url"],
            draft=bool(raw.get("draft")),
            from_fork=(
                head_repo is None
                or head_repo["full_name"] != base_repo["full_name"]
            ),
            html_url=raw.get("html_url"),
        )

    async def create_check(
        self,
        token: str,
        pull: PullRequest,
        *,
        name: str,
        external_id: str,
    ) -> int:
        raw = await self._request(
            "POST",
            f"/repos/{pull.repository}/check-runs",
            token,
            json={
                "name": name,
                "head_sha": pull.head_sha,
                "status": "in_progress",
                "external_id": external_id,
                "output": {
                    "title": "PX review is running",
                    "summary": "Reviewing the change across the PX taxonomy.",
                },
            },
        )
        return int(raw["id"])

    async def finish_check(
        self,
        token: str,
        repository: str,
        check_id: int,
        outcome: ReviewOutcome,
    ) -> None:
        await self._request(
            "PATCH",
            f"/repos/{repository}/check-runs/{check_id}",
            token,
            json={
                "status": "completed",
                "conclusion": outcome.conclusion,
                "completed_at": _iso_now(),
                "output": {
                    "title": (
                        "PX review skipped"
                        if outcome.skipped
                        else f"PX review: {len(outcome.findings)} finding(s)"
                    ),
                    "summary": render_check_summary(outcome)[:65_000],
                },
            },
        )

    async def fail_check(
        self,
        token: str,
        repository: str,
        check_id: int,
        message: str,
    ) -> None:
        await self._request(
            "PATCH",
            f"/repos/{repository}/check-runs/{check_id}",
            token,
            json={
                "status": "completed",
                "conclusion": "failure",
                "completed_at": _iso_now(),
                "output": {
                    "title": "PX review could not complete",
                    "summary": message[:65_000],
                },
            },
        )

    async def publish_review(
        self,
        token: str,
        pull: PullRequest,
        outcome: ReviewOutcome,
    ) -> int:
        existing = await self.existing_fingerprints(token, pull)
        comments = [
            {
                "path": finding.path,
                "line": finding.line,
                "side": "RIGHT",
                "body": render_inline_comment(finding),
            }
            for finding in outcome.findings
            if (
                finding.path is not None
                and finding.line is not None
                and finding_fingerprint(finding) not in existing
            )
        ]
        if not comments:
            return 0
        await self._request(
            "POST",
            f"/repos/{pull.repository}/pulls/{pull.number}/reviews",
            token,
            json={
                "commit_id": pull.head_sha,
                "body": render_review_body(outcome, inline_count=len(comments)),
                "event": "COMMENT",
                "comments": comments,
            },
        )
        return len(comments)

    async def existing_fingerprints(
        self, token: str, pull: PullRequest
    ) -> set[str]:
        comments = await self._list_pages(
            f"/repos/{pull.repository}/pulls/{pull.number}/comments", token
        )
        fingerprints: set[str] = set()
        for comment in comments:
            body = str(comment.get("body") or "")
            fingerprints.update(_FINGERPRINT_RE.findall(body))
        return fingerprints

    async def upsert_summary_comment(
        self,
        token: str,
        pull: PullRequest,
        outcome: ReviewOutcome,
    ) -> int:
        body = render_pr_summary(outcome, pull)[:65_000]
        comments = await self._list_pages(
            f"/repos/{pull.repository}/issues/{pull.number}/comments", token
        )
        existing = next(
            (comment for comment in comments if SUMMARY_MARKER in str(comment.get("body"))),
            None,
        )
        if existing is not None:
            raw = await self._request(
                "PATCH",
                f"/repos/{pull.repository}/issues/comments/{existing['id']}",
                token,
                json={"body": body},
            )
        else:
            raw = await self._request(
                "POST",
                f"/repos/{pull.repository}/issues/{pull.number}/comments",
                token,
                json={"body": body},
            )
        return int(raw["id"])


def _iso_now() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


_FINGERPRINT_RE = re.compile(r"<!--\s*px-review:([a-f0-9]{16})\s*-->")
