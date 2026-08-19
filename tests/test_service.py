from pxreview.models import PullRequest, ReviewFinding, ReviewOutcome, Severity
from pxreview.service import ReviewService
from pxreview.store import ReviewJob


class FakeAuth:
    async def installation_token(self, installation_id):
        assert installation_id == 12
        return "installation-token"


class FakeGitHub:
    def __init__(self, pull):
        self.pull = pull
        self.events = []

    async def get_pull(self, token, repository, number):
        self.events.append(("get_pull", token, repository, number))
        return self.pull

    async def create_check(self, token, pull, *, name, external_id):
        self.events.append(("create_check", name, external_id))
        return 71

    async def publish_review(self, token, pull, outcome):
        self.events.append(("publish_review", len(outcome.findings)))
        return len(outcome.findings)

    async def upsert_summary_comment(self, token, pull, outcome):
        self.events.append(("upsert_summary", len(outcome.findings)))
        return 81

    async def finish_check(self, token, repository, check_id, outcome):
        self.events.append(("finish_check", check_id, outcome.conclusion))

    async def fail_check(self, token, repository, check_id, message):
        raise AssertionError(message)


def _pull():
    return PullRequest(
        repository="acme/app",
        number=8,
        title="Add filters",
        body="",
        base_sha="base",
        head_sha="head",
        clone_url="https://github.test/acme/app.git",
    )


def _job():
    return ReviewJob(
        delivery_id="delivery",
        dedupe_key="auto:acme/app:8:head",
        installation_id=12,
        repository="acme/app",
        pull_number=8,
        expected_head_sha="head",
        trigger="pull_request.opened",
    )


async def test_process_publishes_native_review_summary_and_check():
    finding = ReviewFinding(
        category="accessibility",
        severity=Severity.HIGH,
        title="Filter has no label",
        body="The new filter input has no accessible name.",
        recommendation="Associate a visible label with the input.",
        path="app/Filters.tsx",
        line=18,
        confidence=0.98,
    )
    outcome = ReviewOutcome(
        summary="One actionable finding.",
        findings=(finding,),
        categories=(),
        conclusion="neutral",
    )
    github = FakeGitHub(_pull())
    service = ReviewService(FakeAuth(), github, openai_api_key=None)
    service._review_checkout = lambda job, token, pull: outcome

    await service.process(_job())

    event_names = [event[0] for event in github.events]
    assert event_names == [
        "get_pull",
        "create_check",
        "get_pull",
        "publish_review",
        "upsert_summary",
        "finish_check",
    ]


async def test_process_updates_summary_when_there_are_no_findings():
    outcome = ReviewOutcome(
        summary="No actionable findings.",
        findings=(),
        categories=(),
        conclusion="success",
    )
    github = FakeGitHub(_pull())
    service = ReviewService(FakeAuth(), github, openai_api_key=None)
    service._review_checkout = lambda job, token, pull: outcome

    await service.process(_job())

    event_names = [event[0] for event in github.events]
    assert "publish_review" not in event_names
    assert "upsert_summary" in event_names
    assert event_names[-1] == "finish_check"
