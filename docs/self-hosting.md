# Self-host PX Review

This guide sets up an organization-owned PX reviewer. The result behaves like a
normal GitHub reviewer: opening or updating a pull request starts a check and puts
findings directly on the changed lines.

Chordio is not in the runtime path. Your organization owns the GitHub App,
credentials, deployment, logs, database, policy, and model-provider account.

## What you need

- GitHub organization-owner or GitHub App manager access
- one public HTTPS endpoint for GitHub webhooks
- Python 3.11+ with `uv`, or Docker
- an OpenAI API key, unless you are using the fixture adapter or writing another
  provider adapter

## 1. Take your own copy

Publish `services/px-review` as its own repository, fork the standalone project, or
copy the directory into an internal repository. The MIT License applies to
this directory, so the team may inspect, modify, and redistribute it.

```bash
cp .env.example .env
cp example.pxreview.yml /path/to/product/.pxreview.yml
```

Never commit `.env` or a GitHub App private key. Both are ignored by the included
`.gitignore`.

## 2. Deploy a single instance

Build the included image and run it with persistent storage:

```bash
docker build -t px-review .
docker run -d --name px-review -p 8000:8000 \
  --env-file .env \
  -v px-review-data:/data \
  -v /absolute/path/to/github-app.pem:/run/secrets/github-app.pem:ro \
  px-review
```

Put TLS and request-size limits in front of port 8000. The public origin in the
examples below is `https://review.example.com`; replace it with the real origin.

This version uses SQLite and should run as one replica. Move `JobStore` to a shared
database or queue before horizontal scaling.

## 3. Register your GitHub App

In GitHub, open **Settings → Developer settings → GitHub Apps → New GitHub App** and
use:

- **GitHub App name:** a unique name, such as `Acme PX Review`
- **Homepage URL:** `https://review.example.com`
- **Setup URL:** `https://review.example.com/setup`
- **Webhook URL:** `https://review.example.com/webhooks/github`
- **Webhook active:** on
- **Webhook secret:** a new random value, also stored as `GITHUB_WEBHOOK_SECRET`
- **Request user authorization during installation:** off

Repository permissions:

| Permission | Access | Why |
|---|---|---|
| Checks | Read & write | Start and complete the PX check |
| Contents | Read | Fetch the target and proposed commits |
| Metadata | Read | Required repository metadata |
| Pull requests | Read & write | Read PR state and publish summaries and threads |

Subscribe to **Pull request** and **Issue comment** events. Create the app, note its
numeric App ID and URL slug, and generate a private key.

If the deployment is not ready yet, GitHub lets you create the app with the webhook
temporarily inactive. Add the real HTTPS URL and activate it after deployment. Do not
paste example brackets or a localhost URL into the webhook field.

## 4. Configure the process

Fill `.env`:

```dotenv
GITHUB_APP_ID=123456
GITHUB_APP_SLUG=acme-px-review
GITHUB_WEBHOOK_SECRET=use-a-long-random-secret
GITHUB_APP_PRIVATE_KEY_FILE=/run/secrets/github-app.pem
OPENAI_API_KEY=your-provider-key
PX_REVIEW_PUBLIC_URL=https://review.example.com
PX_REVIEW_APP_NAME=Acme PX Review
PX_REVIEW_CHECK_NAME=PX review
PX_REVIEW_DATABASE=/data/px-review.db
```

Restart the deployment and verify `GET /healthz` returns `{"ok": true, ...}`.

## 5. Install and test

Open `https://review.example.com/install`, select the GitHub organization, and grant
access only to the repositories that should be reviewed. Open or update a non-draft
pull request that changes frontend files. The **PX review** check should start without
a command.

For an already-open pull request, a repository owner, member, or collaborator can
comment `/px review` to request an immediate run.

## 6. Calibrate before enforcing

Start with `block_on: []` or only `blocking`, a high `min_confidence`, and a small
`max_inline_comments`. Run the reviewer against 10–20 representative pull requests,
record false positives and misses, then tune context and policy before making the
check required in branch protection.

See [customization.md](./customization.md) for the two supported levels of change:
repository policy and source-code adaptation.
