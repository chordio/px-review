# Security and data boundary

PX Review is designed to be self-hosted. Chordio does not need an account, a
GitHub installation, or access to a deployment operated from this source code.

## Where repository data goes

During a review, the worker:

1. receives a signed webhook from GitHub;
2. uses the team's GitHub App installation token to fetch the pull request;
3. checks out the trusted base and proposed head in temporary local storage;
4. sends the bounded diff, pull-request intent, and configured context files to
   the configured model provider; and
5. publishes the validated result back to GitHub.

The included production adapter calls the OpenAI API. The fixture adapter makes no
network model call. A team that needs a different data boundary can replace the
provider adapter in `pxreview/provider.py`.

## Operator responsibilities

- Run the service behind HTTPS and keep only `/webhooks/github` publicly reachable.
- Store the GitHub private key, webhook secret, and model API key in a secret manager.
- Select only the repositories the reviewer should access.
- Keep `review_forks: false` unless the security implications are understood.
- Review `.pxreview.yml` changes before merging; policy is intentionally read from
  the target branch so a proposed change cannot alter the rules applied to itself.
- Apply request-size limits at ingress and restrict access to logs and the database.
- Pin versions and review dependency updates like any other privileged automation.

PX Review verifies GitHub webhook signatures, uses short-lived installation tokens,
deduplicates deliveries, avoids credentials in clone URLs, neutralizes model-authored
mentions, and validates model output before publishing it.

## Reporting a vulnerability

Please report suspected vulnerabilities privately to `hello@chordio.com`. Do not
include repository code, secrets, or production logs in the initial report.
