from __future__ import annotations

import hashlib
import hmac
import json
from dataclasses import dataclass

from .store import ReviewJob

AUTO_ACTIONS = {"opened", "reopened", "ready_for_review", "synchronize"}
MANUAL_COMMANDS = {
    "/px review",
    "/px full review",
    "/px-review",
}
TRUSTED_ASSOCIATIONS = {"OWNER", "MEMBER", "COLLABORATOR"}


@dataclass(frozen=True)
class ParsedWebhook:
    job: ReviewJob | None
    reason: str


def verify_signature(secret: str, body: bytes, signature: str | None) -> bool:
    if not secret or not signature or not signature.startswith("sha256="):
        return False
    expected = "sha256=" + hmac.new(
        secret.encode(), body, hashlib.sha256
    ).hexdigest()
    return hmac.compare_digest(expected, signature)


def _is_manual_review_command(body_text: str) -> bool:
    if body_text in MANUAL_COMMANDS:
        return True
    words = body_text.split()
    if len(words) not in {2, 3} or not words[0].startswith("@"):
        return False
    bot_name = words[0].removeprefix("@").removesuffix("[bot]")
    return "px-review" in bot_name and " ".join(words[1:]) in {
        "review",
        "full review",
    }


def parse_webhook(
    event: str | None,
    delivery_id: str,
    body: bytes,
) -> ParsedWebhook:
    try:
        payload = json.loads(body)
    except json.JSONDecodeError:
        return ParsedWebhook(None, "invalid_json")

    if event == "pull_request":
        action = payload.get("action")
        if action not in AUTO_ACTIONS:
            return ParsedWebhook(None, f"ignored_pull_request_action:{action}")
        repository = payload["repository"]["full_name"]
        number = int(payload["number"])
        head_sha = payload["pull_request"]["head"]["sha"]
        return ParsedWebhook(
            ReviewJob(
                delivery_id=delivery_id,
                dedupe_key=f"auto:{repository}:{number}:{head_sha}",
                installation_id=int(payload["installation"]["id"]),
                repository=repository,
                pull_number=number,
                expected_head_sha=head_sha,
                trigger=f"pull_request.{action}",
            ),
            "queued",
        )

    if event == "issue_comment":
        body_text = " ".join(
            (payload.get("comment", {}).get("body") or "")
            .strip()
            .lower()
            .replace("[bot]", "")
            .split()
        )
        if (
            payload.get("action") != "created"
            or not _is_manual_review_command(body_text)
            or "pull_request" not in payload.get("issue", {})
            or payload.get("comment", {}).get("author_association")
            not in TRUSTED_ASSOCIATIONS
        ):
            return ParsedWebhook(None, "ignored_issue_comment")
        repository = payload["repository"]["full_name"]
        number = int(payload["issue"]["number"])
        return ParsedWebhook(
            ReviewJob(
                delivery_id=delivery_id,
                dedupe_key=f"manual:{delivery_id}",
                installation_id=int(payload["installation"]["id"]),
                repository=repository,
                pull_number=number,
                expected_head_sha=None,
                trigger="issue_comment.manual",
            ),
            "queued",
        )

    return ParsedWebhook(None, f"ignored_event:{event}")
