import jwt
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa

from pxreview.engine import finding_fingerprint
from pxreview.github import GitHubAppAuth, GitHubClient
from pxreview.models import PullRequest, ReviewFinding, ReviewOutcome, Severity


def test_app_jwt_is_signed_with_configured_app_id():
    private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    pem = private_key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    ).decode()
    auth = GitHubAppAuth("1234", pem, api_url="https://api.github.test")

    token = auth.app_jwt()

    public_pem = private_key.public_key().public_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PublicFormat.SubjectPublicKeyInfo,
    )
    payload = jwt.decode(token, public_pem, algorithms=["RS256"])
    assert payload["iss"] == "1234"


class CaptureGitHub(GitHubClient):
    def __init__(self, responses=None):
        super().__init__(api_url="https://api.github.test")
        self.requests = []
        self.responses = list(responses or [])

    async def _request(self, method, path, token, *, json=None):
        self.requests.append((method, path, token, json))
        if self.responses:
            return self.responses.pop(0)
        return {"id": 1}


async def test_publish_review_batches_only_commentable_findings():
    client = CaptureGitHub(responses=[[], {"id": 123}])
    pull = PullRequest(
        repository="acme/app",
        number=9,
        title="Add saved views",
        body="",
        base_sha="base",
        head_sha="head",
        clone_url="https://github.test/acme/app.git",
    )
    inline = ReviewFinding(
        category="accessibility",
        severity=Severity.HIGH,
        title="Field is unlabeled",
        body="The new field has no programmatic label.",
        recommendation="Associate its label and input.",
        path="app/Form.tsx",
        line=22,
        confidence=0.99,
    )
    summary_only = inline.model_copy(
        update={
            "title": "Flow is fragmented",
            "category": "product_fit",
            "path": None,
            "line": None,
        }
    )
    outcome = ReviewOutcome(
        summary="Two findings.",
        findings=(inline, summary_only),
        categories=(),
        conclusion="neutral",
    )

    published = await client.publish_review("token", pull, outcome)

    assert published == 1
    assert client.requests[0][0:3] == (
        "GET",
        "/repos/acme/app/pulls/9/comments?per_page=100&page=1",
        "token",
    )
    method, path, token, payload = client.requests[1]
    assert (method, path, token) == (
        "POST",
        "/repos/acme/app/pulls/9/reviews",
        "token",
    )
    assert payload["commit_id"] == "head"
    assert len(payload["comments"]) == 1
    assert payload["comments"][0]["line"] == 22
    assert payload["comments"][0]["side"] == "RIGHT"


async def test_publish_review_suppresses_existing_fingerprints():
    finding = ReviewFinding(
        category="accessibility",
        severity=Severity.HIGH,
        title="Field is unlabeled",
        body="The new field has no programmatic label.",
        recommendation="Associate its label and input.",
        path="app/Form.tsx",
        line=22,
        confidence=0.99,
    )
    fingerprint = finding_fingerprint(finding)
    client = CaptureGitHub(
        responses=[[{"body": f"finding\n<!-- px-review:{fingerprint} -->"}]]
    )
    pull = PullRequest(
        repository="acme/app",
        number=9,
        title="Add saved views",
        body="",
        base_sha="base",
        head_sha="head",
        clone_url="https://github.test/acme/app.git",
    )
    outcome = ReviewOutcome(
        summary="One finding.",
        findings=(finding,),
        categories=(),
        conclusion="neutral",
    )

    assert await client.publish_review("token", pull, outcome) == 0
    assert len(client.requests) == 1


async def test_summary_comment_is_created_then_updated():
    pull = PullRequest(
        repository="acme/app",
        number=9,
        title="Add saved views",
        body="",
        base_sha="base1234567890",
        head_sha="head1234567890",
        clone_url="https://github.test/acme/app.git",
    )
    outcome = ReviewOutcome(
        summary="No actionable findings.",
        findings=(),
        categories=(),
        conclusion="success",
    )
    create_client = CaptureGitHub(responses=[[], {"id": 41}])

    assert await create_client.upsert_summary_comment("token", pull, outcome) == 41
    create_request = create_client.requests[1]
    assert create_request[0:3] == (
        "POST",
        "/repos/acme/app/issues/9/comments",
        "token",
    )
    assert "<!-- px-review:summary -->" in create_request[3]["body"]

    update_client = CaptureGitHub(
        responses=[[{"id": 41, "body": "<!-- px-review:summary -->"}], {"id": 41}]
    )
    assert await update_client.upsert_summary_comment("token", pull, outcome) == 41
    assert update_client.requests[1][0:3] == (
        "PATCH",
        "/repos/acme/app/issues/comments/41",
        "token",
    )
