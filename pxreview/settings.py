from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Settings:
    github_app_id: str
    github_private_key: str
    github_webhook_secret: str
    openai_api_key: str | None
    database_path: Path
    github_api_url: str = "https://api.github.com"
    worker_concurrency: int = 1
    github_app_slug: str | None = None
    public_url: str | None = None
    app_name: str = "PX Review"
    check_name: str = "PX review"

    @classmethod
    def from_env(cls) -> Settings:
        private_key = os.environ.get("GITHUB_APP_PRIVATE_KEY", "").replace(
            "\\n", "\n"
        )
        private_key_file = os.environ.get("GITHUB_APP_PRIVATE_KEY_FILE")
        if not private_key and private_key_file:
            private_key = Path(private_key_file).read_text()

        required = {
            "GITHUB_APP_ID": os.environ.get("GITHUB_APP_ID", ""),
            "GITHUB_WEBHOOK_SECRET": os.environ.get(
                "GITHUB_WEBHOOK_SECRET", ""
            ),
            "GITHUB_APP_PRIVATE_KEY(_FILE)": private_key,
        }
        missing = [name for name, value in required.items() if not value]
        if missing:
            raise RuntimeError(
                "Missing required PX review settings: " + ", ".join(missing)
            )
        return cls(
            github_app_id=required["GITHUB_APP_ID"],
            github_private_key=private_key,
            github_webhook_secret=required["GITHUB_WEBHOOK_SECRET"],
            openai_api_key=os.environ.get("OPENAI_API_KEY"),
            database_path=Path(
                os.environ.get("PX_REVIEW_DATABASE", "work/px-review.db")
            ),
            github_api_url=os.environ.get(
                "GITHUB_API_URL", "https://api.github.com"
            ),
            worker_concurrency=int(
                os.environ.get("PX_REVIEW_WORKERS", "1")
            ),
            github_app_slug=os.environ.get("GITHUB_APP_SLUG") or None,
            public_url=(os.environ.get("PX_REVIEW_PUBLIC_URL") or "").rstrip("/")
            or None,
            app_name=os.environ.get("PX_REVIEW_APP_NAME", "PX Review").strip()
            or "PX Review",
            check_name=os.environ.get("PX_REVIEW_CHECK_NAME", "PX review").strip()
            or "PX review",
        )
