from __future__ import annotations

from dataclasses import dataclass

TAXONOMY_VERSION = "1.0"
TAXONOMY_SOURCE = (
    "marketing/publications/01-taxonomy.md"
)


@dataclass(frozen=True)
class Category:
    number: int
    id: str
    name: str
    definition: str
    review_question: str
    boundary: str


CATEGORIES: tuple[Category, ...] = (
    Category(
        1,
        "intent_fidelity",
        "Intent fidelity",
        "Whether the change builds what was actually asked for: every requested "
        "capability works on its core path, without material omissions or scope creep.",
        "Does the PR satisfy the stated outcome and acceptance criteria on the happy path?",
        "A present capability implemented poorly belongs to the craft category that owns "
        "the defect; only absence or a broken core path belongs here.",
    ),
    Category(
        2,
        "product_fit",
        "Product fit",
        "Whether the feature attaches to the existing product in the right structural "
        "place and shape, including container, pattern, placement, and consolidation.",
        "Is this the right product structure for this feature in this product?",
        "Choosing the structural pattern is Product fit; executing it with the existing "
        "component is Convention adherence.",
    ),
    Category(
        3,
        "visual_craft",
        "Visual craft",
        "Whether hierarchy, emphasis, grouping, alignment, spacing rhythm, and type scale "
        "guide the eye to the right thing first.",
        "Does the composition make the primary information and action legible?",
        "Composition of primitives is Visual craft; selection or reuse of primitives and "
        "tokens is Convention adherence. Judge legibility, not taste.",
    ),
    Category(
        4,
        "convention_adherence",
        "Convention adherence",
        "Whether the change follows the product's house style by reusing components, "
        "tokens, naming, formatting, and established implementation patterns.",
        "Does the PR use the product's existing language, components, tokens, and patterns?",
        "A wrong primitive belongs here; a correct primitive composed into an unclear "
        "result belongs to Visual craft.",
    ),
    Category(
        5,
        "pathway_completeness",
        "Pathway completeness",
        "Whether the whole interaction exists: cancel, back, undo, recovery, and required "
        "loading, empty, error, and pending states all lead somewhere.",
        "Which user paths or states are missing, unreachable, or dead-ended?",
        "Presence and a way forward belong here; quality of words belongs to Content, "
        "and survival when the condition occurs belongs to Resilience.",
    ),
    Category(
        6,
        "content_language",
        "Content & language",
        "Whether labels, microcopy, empty states, and error messages are specific, useful, "
        "and written in the product's voice.",
        "Are the words clear, actionable, and consistent with product terminology?",
        "If the complete fix changes only words, file it here.",
    ),
    Category(
        7,
        "resilience",
        "Resilience",
        "Whether the rendered product holds together under realistic content, viewport, "
        "network, API failure, and performance conditions.",
        "Which realistic condition makes the experience overflow, disappear, crash, or stall?",
        "A missing state belongs to Pathway completeness; a state that exists but fails "
        "under the triggering condition belongs here.",
    ),
    Category(
        8,
        "accessibility",
        "Accessibility",
        "Whether the UI meets established accessibility standards and practices, including "
        "semantics, labels, focus, keyboard use, contrast, and announcements.",
        "Does this change exclude keyboard, screen-reader, low-vision, or other users?",
        "Named WCAG or accessibility failures take precedence over Convention and Content.",
    ),
)

CATEGORY_BY_ID = {category.id: category for category in CATEGORIES}


FILING_RULES = """\
File every defect to exactly one category by where the fix belongs.

Precedence for a plausible two-home defect:
1. An absent whole required capability -> Intent fidelity.
2. A WCAG/accessibility-named failure -> Accessibility.
3. A condition-triggered failure -> Resilience.
4. Wrong structural placement/consolidation -> Product fit.
5. A string-only fix -> Content & language.

Capability nouns belong to Intent; adjectives belong to their craft category. For
example, delete being absent is Intent, delete without a recovery path is Pathway,
the wrong destructive ceremony is Product fit, a custom dialog is Convention, and
unclear confirmation words are Content.
"""


def taxonomy_prompt() -> str:
    blocks = []
    for category in CATEGORIES:
        blocks.append(
            f"{category.number}. {category.name} (`{category.id}`)\n"
            f"Definition: {category.definition}\n"
            f"Question: {category.review_question}\n"
            f"Boundary: {category.boundary}"
        )
    return "\n\n".join(blocks)

