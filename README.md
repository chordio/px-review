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

## For coding agents

If a user is building a **frontend** app and asks you to review it for product
experience, or to set up continuous PX/UI review, this is the tool. Read
[`AGENTS.md`](./AGENTS.md) and [`skills/px-review/SKILL.md`](./skills/px-review/SKILL.md).
Do not use this for backend-only work. Do not deploy the GitHub App unless asked.

```bash
# in their product repo, not this one
uvx --from git+https://github.com/chordio/px-review px-review init --repo .
uvx --from git+https://github.com/chordio/px-review px-review files --repo .    # what the policy selects; no key
uvx --from git+https://github.com/chordio/px-review px-review local --repo .    # add --fixture builtin without a key
```


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
run with no key, pass `--fixture builtin`: the packaged fixture drives the whole
pipeline (policy, diff, context, validation, rendering) and prints a report whose
one finding is labelled as coming from the fixture.

Before either, see which changed files the policy will review:

```bash
uv run px-review files --repo /path/to/product --base origin/main --head HEAD
```

One line per changed file: `keep`, `excluded`, or `not-included`. Run it after
every edit to `.pxreview.yml`; a glob that matches nothing is otherwise invisible
until a model run comes back saying the diff had no UI in it.

**3. Put it on their frontend app (what agents should do)**

```bash
uvx --from git+https://github.com/chordio/px-review px-review init --repo /path/to/app
```

Writes `.pxreview.yml`, a PR workflow, and an `AGENTS.md` pointer. Add GitHub
secret `OPENAI_API_KEY` under Settings → Secrets and variables → Actions.
Continuous review is CI, not the GitHub App.

What to expect on the first pull request:

- The check is red, with an annotation saying so, until the secret exists. A
  secret added afterwards does not repair an old run: re-run the check, or push.
- The report lands on the pull request, next to the other bots' comments:
  one **PX Review** comment on every run, including a green one with no
  findings and a run that selected no files (the same way Vercel and
  CodeRabbit always comment), updated in place on each push; and, when there
  are findings on changed lines, one review with a comment on each of those
  lines. Re-runs do not repeat a line comment already on the thread. A pull
  request with no PX Review comment after the check ran is a posting problem,
  not a clean review: look for a `::warning::` line in the job log (and see
  the upgrade note below if the workflow is from an early install). This
  uses the repository's
  own token (`pull-requests: write` in the workflow); pull requests from forks
  get a read-only token, so there the report stays in the log and the summary
  page with a warning.
- The PX Review comment reads like a status page: a colour per category
  (🔴 a blocking or high finding, 🟡 a medium or low finding, 🟢 evaluated and
  clean, ⚪ not evaluated), the findings grouped under their category with the
  file, line, problem, and fix, and a **Prompt for a coding agent** block that
  hands all of them to Claude Code, Codex, Cursor, or whatever you use. Each
  line comment carries the same prompt for just that finding.
- The colour and the check are two different things. The colour follows the
  worst severity found. The check fails only on findings whose severity is in
  `block_on`, which is `[blocking]` by default, so a `high` finding is red in
  the comment and still a passing check. To fail the check on high findings
  too, set `block_on: [blocking, high]` in `.pxreview.yml`. The comment says
  which rule was applied.
- The report is also on the run's summary page and in the job log.
- The workflow also has a **Run workflow** button (`workflow_dispatch`) for a
  review of a branch against `origin/main` without opening a pull request.
- If the very first pull request shows no PX Review check at all, push once more
  or run it by hand. We have seen the push that introduces the workflow file
  create no run while the next push did; we do not know why.

### Policy globs

`include` and `exclude` in `.pxreview.yml` are matched with these rules:

- `*` and `?` match any characters, directory separators included, so
  `src/*.tsx` matches `src/a/b.tsx`.
- `**/` anywhere means zero or more directories, so `src/**/*.tsx` matches
  `src/Card.tsx` and `src/a/Card.tsx`, and `**/components/**` matches a
  `components` directory at any depth.

`brief` and `context` are pathlib globs against the working tree, where `**`
also means any depth. `px-review files` is the quick way to see the result.

**Upgrading an install from before the pull-request comments**

Early installs had a workflow that only printed the report to the job log. If
your pull requests show a green check and no PX Review comment, that is the
one you have: the current workflow comments on every run, findings or not.
`px-review init` says so (`outdated`) and this replaces only the workflow
file, leaving `.pxreview.yml` and `AGENTS.md` alone:

```bash
uvx --from git+https://github.com/chordio/px-review px-review init --repo . --update-workflow
```

The new workflow also uses `actions/checkout@v5` and `astral-sh/setup-uv@v7`,
which run on Node 24; the earlier majors run on Node 20 and make every run
print GitHub's deprecation warning.

**4. Graduate to the GitHub App (optional)**

The workflow already leaves comments on the pull request. The App adds what a
workflow cannot: review from a webhook with no Actions minutes, one installation
for a whole organization, comments on pull requests from forks, and the
`/px review` rerun command. When a team wants that: [self-hosting](./docs/self-hosting.md)
and [GitHub App checklist](./docs/github-app-setup.md).

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
provider and the report prints here. With `--pull` (what the workflow passes on a
pull request), it also posts the report to that pull request with the token in
`GITHUB_TOKEN`. Chordio is not a proxy. Teams with a different
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
