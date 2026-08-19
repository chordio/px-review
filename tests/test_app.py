import hashlib
import hmac
import json
from pathlib import Path

import httpx

from pxreview.app import create_app
from pxreview.settings import Settings
from pxreview.store import JobStore


class UnusedService:
    async def process(self, job):
        raise AssertionError(f"worker should be disabled in this test: {job}")


def _settings(tmp_path: Path) -> Settings:
    return Settings(
        github_app_id="1",
        github_private_key="not-used",
        github_webhook_secret="secret",
        openai_api_key=None,
        database_path=tmp_path / "queue.db",
        github_app_slug="px-review-test",
    )


async def test_webhook_is_authenticated_and_idempotent(tmp_path: Path):
    settings = _settings(tmp_path)
    store = JobStore(settings.database_path)
    app = create_app(
        settings=settings,
        store=store,
        service=UnusedService(),
        start_workers=False,
    )
    payload = json.dumps(
        {
            "action": "opened",
            "number": 4,
            "installation": {"id": 3},
            "repository": {"full_name": "acme/app"},
            "pull_request": {"head": {"sha": "head"}},
        }
    ).encode()
    signature = "sha256=" + hmac.new(
        b"secret", payload, hashlib.sha256
    ).hexdigest()
    headers = {
        "X-GitHub-Event": "pull_request",
        "X-GitHub-Delivery": "delivery",
        "X-Hub-Signature-256": signature,
        "Content-Type": "application/json",
    }

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(
        transport=transport, base_url="http://test"
    ) as client:
        first = await client.post(
            "/webhooks/github", content=payload, headers=headers
        )
        second = await client.post(
            "/webhooks/github", content=payload, headers=headers
        )
        unauthorized = await client.post(
            "/webhooks/github",
            content=payload,
            headers={**headers, "X-Hub-Signature-256": "sha256=bad"},
        )

    assert first.status_code == 202
    assert first.json()["queued"] is True
    assert second.json()["duplicate"] is True
    assert unauthorized.status_code == 401


async def test_install_landing_redirects_to_github(tmp_path: Path):
    app = create_app(
        settings=_settings(tmp_path),
        service=UnusedService(),
        start_workers=False,
    )
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(
        transport=transport, base_url="http://test", follow_redirects=False
    ) as client:
        home = await client.get("/")
        install = await client.get("/install")
        setup = await client.get("/setup")

    assert home.status_code == 200
    assert "Install PX Review on GitHub" in home.text
    assert install.status_code == 302
    assert install.headers["location"] == (
        "https://github.com/apps/px-review-test/installations/new"
    )
    assert "nothing else to configure" in setup.text
