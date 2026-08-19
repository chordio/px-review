# Customize the reviewer

PX Review is meant to become your team's reviewer, not remain a generic bot. Most
teams should begin with repository policy and only fork the Python modules when the
review contract itself needs to change.

## Level 1: teach it the product

Add `.pxreview.yml` to each reviewed repository. Start from
`example.pxreview.yml` and set:

- `brief`: product briefs and acceptance criteria;
- `context`: design-system, component, token, content, and interaction guidance;
- `include` and `exclude`: files that carry PX signal;
- `categories`: taxonomy categories relevant to the product;
- `min_confidence` and `max_inline_comments`: noise controls;
- `block_on`: severities that fail the check;
- `model` and `reasoning_effort`: the cost/quality policy.

Policy is loaded from the target commit, not the proposed commit. A policy update is
reviewed under the current rules and becomes active after it merges. This prevents a
pull request from weakening its own review.

## Level 2: change the implementation

The main adaptation points are deliberately small:

| File | Responsibility |
|---|---|
| `pxreview/taxonomy.py` | category definitions and filing rules |
| `pxreview/prompts.py` | model review contract |
| `pxreview/models.py` | structured finding schema |
| `pxreview/provider.py` | model-provider adapter |
| `pxreview/engine.py` | validation, filtering, and fingerprints |
| `pxreview/render.py` | GitHub-facing report language |
| `pxreview/github.py` | GitHub checks, comments, and review threads |

Keep deterministic validation outside the prompt. A model may propose a finding;
code should still verify its category, confidence, location, changed-line status,
and publication limits.

## Replace the model provider

The included real provider uses OpenAI Structured Outputs. To keep code within a
different provider boundary, implement the same `review(...) -> ReviewDraft`
contract in `pxreview/provider.py`, wire it in `ReviewService`, and add a fixture test
for malformed output and network failure.

## Calibrate as a DesignOps practice

Use a small set of past PRs with known product-experience issues. For each finding,
track whether it was useful, correctly categorized, placed on the right line, and
worth interrupting the author. Tune evidence sources before expanding the prompt.
The goal is a reliable review habit, not the largest possible issue count.
