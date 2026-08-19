import hashlib
import hmac
import json

from pxreview.webhook import parse_webhook, verify_signature


def _pull_payload(action: str = "synchronize") -> bytes:
    return json.dumps(
        {
            "action": action,
            "number": 7,
            "installation": {"id": 99},
            "repository": {"full_name": "acme/app"},
            "pull_request": {"head": {"sha": "abc123"}},
        }
    ).encode()


def test_signature_verification():
    body = b'{"ok":true}'
    digest = hmac.new(b"secret", body, hashlib.sha256).hexdigest()
    assert verify_signature("secret", body, f"sha256={digest}")
    assert not verify_signature("secret", body + b"x", f"sha256={digest}")


def test_pull_request_event_becomes_deduplicated_job():
    parsed = parse_webhook("pull_request", "delivery", _pull_payload())
    assert parsed.job is not None
    assert parsed.job.dedupe_key == "auto:acme/app:7:abc123"
    assert parsed.job.expected_head_sha == "abc123"


def test_uninteresting_actions_are_ignored():
    parsed = parse_webhook("pull_request", "delivery", _pull_payload("closed"))
    assert parsed.job is None


def test_manual_comment_forces_a_new_review():
    body = json.dumps(
        {
            "action": "created",
            "installation": {"id": 99},
            "repository": {"full_name": "acme/app"},
            "issue": {"number": 7, "pull_request": {"url": "https://example.test"}},
            "comment": {
                "body": "/px review",
                "author_association": "MEMBER",
            },
        }
    ).encode()
    parsed = parse_webhook("issue_comment", "manual-delivery", body)
    assert parsed.job is not None
    assert parsed.job.dedupe_key == "manual:manual-delivery"
    assert parsed.job.expected_head_sha is None


def test_github_mention_can_force_a_full_review():
    body = json.dumps(
        {
            "action": "created",
            "installation": {"id": 99},
            "repository": {"full_name": "acme/app"},
            "issue": {"number": 7, "pull_request": {"url": "https://example.test"}},
            "comment": {
                "body": "  @acme-px-review[bot]   full review  ",
                "author_association": "OWNER",
            },
        }
    ).encode()
    parsed = parse_webhook("issue_comment", "mention-delivery", body)
    assert parsed.job is not None
    assert parsed.job.trigger == "issue_comment.manual"


def test_manual_comment_from_untrusted_author_is_ignored():
    body = json.dumps(
        {
            "action": "created",
            "installation": {"id": 99},
            "repository": {"full_name": "acme/app"},
            "issue": {"number": 7, "pull_request": {"url": "https://example.test"}},
            "comment": {
                "body": "/px review",
                "author_association": "NONE",
            },
        }
    ).encode()
    assert parse_webhook("issue_comment", "delivery", body).job is None
