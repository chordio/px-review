# PX Review

PX Review is a free, open-source kit for running product-experience review against
frontend changes. It uses the same eight-category taxonomy as PX-bench:

1. Intent fidelity
2. Product fit
3. Visual craft
4. Convention adherence
5. Pathway completeness
6. Content & language
7. Resilience
8. Accessibility

Start on your machine. The GitHub App is what a team graduates to once the findings
have proven useful. Chordio does not need access to your repositories.

## Start here

Requires Python 3.11+ and [`uv`](https://docs.astral.sh/uv/).

**1. See a finding (no credentials)**

```bash
git clone https://github.com/chordio/px-review.git
cd px-review
uv sync --group test
uv run px-review demo
```

Opens `http://127.0.0.1:4173` with a saved-views change and three evidence-backed
findings. Use `--no-open` in a remote environment.

**2. Review a local diff (under five minutes)**

```bash
export OPENAI_API_KEY=...
uv run px-review local \
  --repo /path/to/product \
  --base origin/main \
  --head HEAD
```

The same engine as the GitHub App, against your working tree. Exits 1 only when a
finding matches the repository's `block_on` policy. For a deterministic no-network
run, pass `--fixture review-fixture.json`.

**3. Put it on pull requests**

When the CLI findings are useful, deploy the GitHub App so review starts on every
frontend PR: [self-hosting guide](./docs/self-hosting.md) and
[GitHub App checklist](./docs/github-app-setup.md).

Also:

- [Customization](./docs/customization.md): teach the reviewer your product
- [Security and data boundary](./SECURITY.md)
- [Course outline](./docs/course-outline.md): optional guided implementation

## Trust boundary

During a GitHub-App review, repository data moves between systems your team selects:

```text
your GitHub organization
  -> your PX Review deployment
  -> your configured LLM provider
  -> your GitHub pull request
```

The local CLI skips GitHub entirely: your working tree goes to your configured LLM
provider and the report prints here. Chordio is not a proxy. Teams with a different
provider or data boundary can replace `pxreview/provider.py`.

The service verifies GitHub webhook HMACs, uses short-lived installation tokens,
loads policy from the trusted target commit, validates structured model output, and
neutralizes model-authored GitHub mentions before publication. See [SECURITY.md](./SECURITY.md)
for operator responsibilities and remaining risks.

## Product contract

PX Review reuses the taxonomy and its MECE filing rules, not the benchmark's
scenario-specific score. An arbitrary pull request rarely contains enough evidence
to grade all eight categories fairly. It therefore emits:

- one category home per finding;
- `finding`, `no finding`, or `not evaluated` coverage per category;
- severity and confidence as separate concepts;
- inline comments only on changed lines;
- no numeric composite.

The scenario-specific PX-bench evaluator remains the right tool for a calibrated,
numeric replay against a pinned benchmark. PX Review is the general team workflow.

## GitHub App workflow

Once deployed, the normal developer workflow has no command and no dashboard:

1. A GitHub administrator deploys the service and installs the team's GitHub App.
2. A developer opens or updates a pull request. Review starts automatically.
3. GitHub shows a check, one persistent taxonomy report, and review threads on exact
   changed lines.

`/px review` and `@px-review review` are optional rerun commands for trusted
collaborators.

```bash
uv sync --group test
uv run pytest -q
cp .env.example .env
set -a; source .env; set +a
uv run px-review serve
```

The service reads:

| Variable | Required | Purpose |
|---|---:|---|
| `GITHUB_APP_ID` | yes | Organization-owned GitHub App identity |
| `GITHUB_APP_SLUG` | for `/install` | App URL slug, such as `acme-px-review` |
| `GITHUB_WEBHOOK_SECRET` | yes | Webhook HMAC verification |
| `GITHUB_APP_PRIVATE_KEY` or `_FILE` | yes | Installation-token signing |
| `OPENAI_API_KEY` | yes for real reviews | Included model-provider adapter |
| `PX_REVIEW_PUBLIC_URL` | no | Public HTTPS deployment origin |
| `PX_REVIEW_APP_NAME` | no | Operator page name |
| `PX_REVIEW_CHECK_NAME` | no | GitHub check name |
| `PX_REVIEW_DATABASE` | no | Queue path, default `work/px-review.db` |
| `PX_REVIEW_WORKERS` | no | In-process worker count, default `1` |

## Architecture

```text
GitHub webhook
  -> HMAC verification
  -> SQLite durable/idempotent queue
  -> GitHub App installation token
  -> detached target/proposed checkout
  -> PX-file filtering + bounded product/design-system context
  -> structured model review
  -> deterministic category/location/confidence validation
  -> check run + persistent PR summary + new inline review threads
```

Repository content is untrusted evidence, not model instructions. Installation
tokens are passed through an ephemeral HTTP header and never embedded in clone URLs.
A head-SHA check suppresses stale findings when new commits supersede an in-flight
review. Exact finding fingerprints prevent duplicate inline threads.

SQLite is appropriate for one service replica. Move `JobStore` to Postgres or a
managed queue before horizontal scaling.

## Repository policy

Copy [`example.pxreview.yml`](./example.pxreview.yml) to `.pxreview.yml` in a product
repository. Conservative frontend defaults apply when it is absent. Backend-only
changes are skipped instead of spending a model call; draft and fork PRs are skipped
by default.

Policy is loaded from the pull request's target commit. A proposed policy change is
reviewed under the current approved rules and becomes active after merge. This is a
normal control for privileged repository automation, not an assumption that feature
branches commonly change policy.

## License and course

MIT. The software is free to use, fork, and adapt without taking a course. Chordio's
optional course teaches DesignOps teams how to shape the review contract, connect
product evidence, deploy an organization-owned GitHub App, calibrate on real pull
requests, and govern the reviewer over time.

## Current limits

- Static diff and repository-context review only; the worker does not yet launch the
  app, capture screenshots, or run browser/axe pathways.
- The model boundary is pluggable, but only OpenAI and fixture adapters ship.
- Each head is evaluated against the complete PR diff. The service does not yet
  auto-resolve an existing thread after a later commit fixes it.
- Binary assets are visible only as changed paths, not model inputs.
- This does not replace calibrated multi-provider consensus for publishable PX-bench
  results.
