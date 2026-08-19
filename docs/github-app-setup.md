# GitHub App setup checklist

Each organization should register and own its own GitHub App. There is no shared
Chordio installation and no Chordio user account in this architecture.

## URLs

Deploy PX Review to a public HTTPS origin first, then configure:

- **Homepage URL:** your deployment origin, for example `https://review.example.com`
- **Setup URL:** `https://review.example.com/setup`
- **Webhook URL:** `https://review.example.com/webhooks/github`
- **Webhook active:** yes
- **Request user authorization during installation:** no

The GitHub App installation is the authorization step. PX Review needs repository
installation access, not an end-user OAuth token.

## Repository permissions

| Permission | Access | Used for |
|---|---|---|
| Checks | Read & write | Start and complete the PX check |
| Contents | Read | Fetch the trusted target and proposed commits |
| Metadata | Read | Required repository metadata |
| Pull requests | Read & write | Read the diff and publish summaries and threads |

Subscribe to **Pull request** and **Issue comment** events.

## Credentials

1. Generate a long random webhook secret and store the same value in
   `GITHUB_WEBHOOK_SECRET`.
2. Create the app, record its numeric App ID and URL slug, then generate a private
   key.
3. Store the private key outside the repository and set
   `GITHUB_APP_PRIVATE_KEY_FILE` to its mounted path.
4. Install the app only on repositories the reviewer should access.

## Verify the workflow

Open or update a frontend pull request. The **PX review** check starts automatically.
The reviewer publishes one persistent summary and new evidence-backed inline threads
without duplicating prior findings.

If a webhook is missed during setup, a repository owner, member, or collaborator can
comment `/px review`.

The service authenticates every webhook delivery, deduplicates deliveries and head
SHAs, and obtains short-lived installation tokens only when a job runs.
