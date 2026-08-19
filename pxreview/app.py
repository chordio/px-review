from __future__ import annotations

from contextlib import asynccontextmanager
from urllib.parse import quote

from fastapi import FastAPI, HTTPException, Request, status
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse

from .github import GitHubAppAuth, GitHubClient
from .service import ReviewService
from .settings import Settings
from .store import JobStore
from .webhook import parse_webhook, verify_signature
from .worker import ReviewWorker


def create_app(
    *,
    settings: Settings | None = None,
    store: JobStore | None = None,
    service: ReviewService | None = None,
    start_workers: bool = True,
) -> FastAPI:
    settings = settings or Settings.from_env()
    store = store or JobStore(settings.database_path)
    if service is None:
        auth = GitHubAppAuth(
            settings.github_app_id,
            settings.github_private_key,
            api_url=settings.github_api_url,
        )
        github = GitHubClient(api_url=settings.github_api_url)
        service = ReviewService(
            auth,
            github,
            openai_api_key=settings.openai_api_key,
            check_name=settings.check_name,
        )
    worker = ReviewWorker(
        store,
        service,
        concurrency=settings.worker_concurrency,
    )

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        del app
        if start_workers:
            worker.start()
        yield
        if start_workers:
            await worker.stop()

    app = FastAPI(
        title=settings.app_name,
        version="0.1.0",
        lifespan=lifespan,
    )
    app.state.store = store
    app.state.worker = worker

    @app.get("/", response_class=HTMLResponse)
    async def home() -> str:
        install = (
            f'<a class="button" href="/install">Install {settings.app_name} on GitHub</a>'
            if settings.github_app_slug
            else '<p class="muted">Set <code>GITHUB_APP_SLUG</code> to enable the install link.</p>'
        )
        return _page(
            settings.app_name,
            "Product experience review, in every pull request.",
            f"Install once. Open or update a pull request. {settings.app_name} adds a native "
            "check, a persistent taxonomy report, and actionable inline comments.",
            install,
        )

    @app.get("/install")
    async def install() -> RedirectResponse:
        if not settings.github_app_slug:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="GITHUB_APP_SLUG is not configured.",
            )
        slug = quote(settings.github_app_slug, safe="-")
        return RedirectResponse(
            f"https://github.com/apps/{slug}/installations/new",
            status_code=status.HTTP_302_FOUND,
        )

    @app.get("/setup", response_class=HTMLResponse)
    async def setup() -> str:
        return _page(
            f"{settings.app_name} is installed",
            "There is nothing else to configure.",
            "Open a pull request in an installed repository. Review starts "
            "automatically and updates on every push.",
            '<a class="button" href="https://github.com/pulls">Open GitHub pull requests</a>',
        )

    @app.get("/healthz")
    async def healthz() -> dict:
        return {"ok": True, "queue": store.stats()}

    @app.post("/webhooks/github")
    async def github_webhook(request: Request) -> JSONResponse:
        body = await request.body()
        if not verify_signature(
            settings.github_webhook_secret,
            body,
            request.headers.get("X-Hub-Signature-256"),
        ):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid GitHub webhook signature.",
            )
        delivery_id = request.headers.get("X-GitHub-Delivery")
        if not delivery_id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Missing X-GitHub-Delivery.",
            )
        parsed = parse_webhook(
            request.headers.get("X-GitHub-Event"),
            delivery_id,
            body,
        )
        if parsed.job is None:
            return JSONResponse(
                {"accepted": False, "reason": parsed.reason},
                status_code=status.HTTP_202_ACCEPTED,
            )
        created = store.enqueue(parsed.job)
        return JSONResponse(
            {
                "accepted": True,
                "queued": created,
                "duplicate": not created,
                "delivery_id": delivery_id,
            },
            status_code=status.HTTP_202_ACCEPTED,
        )

    return app


def _page(title: str, heading: str, description: str, action: str) -> str:
    return f"""<!doctype html>
<html lang="en">
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{title}</title>
<style>
body {{ margin: 0; background: #0b1020; color: #f5f7ff; font: 17px/1.6 system-ui, sans-serif; }}
main {{ max-width: 720px; margin: 12vh auto; padding: 48px; }}
.eyebrow {{ color: #90a7ff; font-weight: 700; letter-spacing: .08em; text-transform: uppercase; }}
h1 {{ max-width: 640px; margin: 12px 0; font-size: clamp(40px, 7vw, 72px); line-height: 1.02; }}
p {{ max-width: 620px; color: #c6ccdf; }}
.button {{ display: inline-block; margin-top: 24px; padding: 12px 18px;
  border-radius: 9px; background: #8ba2ff; color: #07102b;
  font-weight: 750; text-decoration: none; }}
.muted {{ margin-top: 24px; color: #8d96ad; }}
code {{ color: #d5dcff; }}
</style>
<main><div class="eyebrow">{title}</div><h1>{heading}</h1><p>{description}</p>{action}</main>
</html>"""
