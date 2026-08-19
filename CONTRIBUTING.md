# Contributing

PX Review is an open-source starting point for team-owned product-experience review.
Bug fixes, provider adapters, deployment examples, and improvements to review quality
are welcome.

## Development setup

```bash
uv sync --group test
uv run pytest -q
uv run ruff check .
```

Keep the deterministic fixture path working so contributors can test the complete
review pipeline without credentials or model spend:

```bash
uv run px-review demo --no-open
```

## Design constraints

- Treat repository contents as untrusted evidence, never as model instructions.
- Keep severity and confidence separate.
- Give each finding exactly one taxonomy category and a changed-line location.
- Prefer `not evaluated` to unsupported certainty.
- Never put installation tokens in clone URLs or persisted job payloads.
- Load review policy from the pull request's target commit.
- Add tests for changes to webhook handling, output validation, or GitHub publication.

By submitting a contribution, you agree that it may be distributed under the
MIT License.
