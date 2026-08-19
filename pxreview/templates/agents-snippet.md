## PX Review

This frontend repo uses [PX Review](https://github.com/chordio/px-review) for
product-experience review of UI pull requests.

- Policy: `.pxreview.yml`
- Continuous: `.github/workflows/px-review.yml` on each PR
- Run now: `uvx --from git+https://github.com/chordio/px-review px-review local --repo .`

Do not deploy the GitHub App unless the user asks. CLI plus CI is the default.
