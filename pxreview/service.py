from __future__ import annotations

import asyncio
from collections.abc import Callable

from .checkout import checkout_pull
from .config import ReviewConfig, load_config
from .context import collect_documents
from .diffing import build_diff
from .engine import run_review
from .github import GitHubAppAuth, GitHubClient
from .models import ReviewContext, ReviewOutcome
from .provider import OpenAIReviewProvider, ReviewProvider
from .store import ReviewJob

ProviderFactory = Callable[[ReviewConfig], ReviewProvider]


class ReviewService:
    def __init__(
        self,
        auth: GitHubAppAuth,
        github: GitHubClient,
        *,
        openai_api_key: str | None,
        provider_factory: ProviderFactory | None = None,
        check_name: str = "PX review",
    ) -> None:
        self.auth = auth
        self.github = github
        self.openai_api_key = openai_api_key
        self.provider_factory = provider_factory or self._openai_provider
        self.check_name = check_name

    def _openai_provider(self, config: ReviewConfig) -> ReviewProvider:
        return OpenAIReviewProvider(
            model=config.model,
            api_key=self.openai_api_key,
            reasoning_effort=config.reasoning_effort,
        )

    def _review_checkout(
        self,
        job: ReviewJob,
        token: str,
        pull,
    ) -> ReviewOutcome:
        with checkout_pull(
            pull.repository,
            token,
            pull.base_sha,
            pull.head_sha,
            pull.number,
        ) as repo_root:
            config = load_config(repo_root, ref=pull.base_sha)
            if pull.draft and not config.review_drafts:
                return ReviewOutcome(
                    summary="Draft pull request; PX review is deferred until it is ready.",
                    findings=(),
                    categories=(),
                    conclusion="success",
                    skipped=True,
                    skip_reason="`.pxreview.yml` has `review_drafts: false`.",
                )
            if pull.from_fork and not config.review_forks:
                return ReviewOutcome(
                    summary="Fork pull request; automatic PX review is disabled.",
                    findings=(),
                    categories=(),
                    conclusion="success",
                    skipped=True,
                    skip_reason="`.pxreview.yml` has `review_forks: false`.",
                )
            diff = build_diff(repo_root, pull.base_sha, pull.head_sha, config)
            context = ReviewContext(
                repo_root=repo_root,
                repository=pull.repository,
                pull_number=pull.number,
                title=pull.title,
                body=pull.body,
                diff=diff,
                documents=collect_documents(repo_root, diff, config),
            )
            return run_review(context, config, self.provider_factory(config))

    async def process(self, job: ReviewJob) -> None:
        token = await self.auth.installation_token(job.installation_id)
        pull = await self.github.get_pull(
            token, job.repository, job.pull_number
        )
        # A queued synchronize job becomes stale when a newer head arrives. Do
        # not post old findings onto the new diff.
        if job.expected_head_sha and pull.head_sha != job.expected_head_sha:
            return

        check_id = await self.github.create_check(
            token,
            pull,
            name=self.check_name,
            external_id=job.delivery_id,
        )
        try:
            outcome = await asyncio.to_thread(
                self._review_checkout, job, token, pull
            )
            latest = await self.github.get_pull(
                token, job.repository, job.pull_number
            )
            if latest.head_sha != pull.head_sha:
                outcome = ReviewOutcome(
                    summary="A newer commit arrived before this review finished.",
                    findings=(),
                    categories=(),
                    conclusion="neutral",
                    skipped=True,
                    skip_reason="This review was superseded; the newer head is queued separately.",
                    model=outcome.model,
                )
            else:
                if outcome.findings:
                    await self.github.publish_review(token, pull, outcome)
                await self.github.upsert_summary_comment(token, pull, outcome)
            await self.github.finish_check(
                token, pull.repository, check_id, outcome
            )
        except Exception as error:
            try:
                await self.github.fail_check(
                    token,
                    pull.repository,
                    check_id,
                    "The review worker failed. It will retry automatically.\n\n"
                    f"`{type(error).__name__}: {str(error)[:1000]}`",
                )
            finally:
                raise
