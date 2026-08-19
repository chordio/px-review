from __future__ import annotations

import asyncio
import logging
from contextlib import suppress

from .service import ReviewService
from .store import JobStore

logger = logging.getLogger(__name__)


class ReviewWorker:
    def __init__(
        self,
        store: JobStore,
        service: ReviewService,
        *,
        concurrency: int = 1,
        poll_interval: float = 0.75,
    ) -> None:
        self.store = store
        self.service = service
        self.concurrency = max(1, concurrency)
        self.poll_interval = poll_interval
        self._tasks: list[asyncio.Task] = []
        self._stop = asyncio.Event()

    def start(self) -> None:
        if self._tasks:
            return
        self._stop.clear()
        self._tasks = [
            asyncio.create_task(self._run(index), name=f"px-review-worker-{index}")
            for index in range(self.concurrency)
        ]

    async def stop(self) -> None:
        self._stop.set()
        if self._tasks:
            await asyncio.gather(*self._tasks, return_exceptions=True)
        self._tasks = []

    async def run_once(self) -> bool:
        job = await asyncio.to_thread(self.store.claim_next)
        if job is None:
            return False
        try:
            await self.service.process(job)
        except Exception as error:
            logger.exception("PX review job %s failed", job.delivery_id)
            await asyncio.to_thread(self.store.fail, job, str(error))
        else:
            await asyncio.to_thread(self.store.complete, job.delivery_id)
        return True

    async def _run(self, index: int) -> None:
        del index
        while not self._stop.is_set():
            worked = await self.run_once()
            if not worked:
                with suppress(TimeoutError):
                    await asyncio.wait_for(
                        self._stop.wait(), timeout=self.poll_interval
                    )
