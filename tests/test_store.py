from pathlib import Path

from pxreview.store import JobStore, ReviewJob


def _job(delivery: str = "delivery-1") -> ReviewJob:
    return ReviewJob(
        delivery_id=delivery,
        dedupe_key="auto:acme/app:1:abc",
        installation_id=10,
        repository="acme/app",
        pull_number=1,
        expected_head_sha="abc",
        trigger="pull_request.synchronize",
    )


def test_store_deduplicates_and_completes(tmp_path: Path):
    store = JobStore(tmp_path / "queue.db")
    assert store.enqueue(_job()) is True
    assert store.enqueue(_job("github-retry")) is False

    claimed = store.claim_next()
    assert claimed is not None
    assert claimed.attempts == 1
    store.complete(claimed.delivery_id)

    assert store.stats() == {"complete": 1}
    assert store.claim_next() is None


def test_store_retries_then_fails_terminally(tmp_path: Path):
    store = JobStore(tmp_path / "queue.db")
    store.enqueue(_job())
    claimed = store.claim_next()
    assert claimed is not None
    store.fail(claimed, "temporary", max_attempts=1)
    assert store.stats() == {"failed": 1}

