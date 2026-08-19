from pxreview.taxonomy import CATEGORIES, CATEGORY_BY_ID, TAXONOMY_VERSION


def test_taxonomy_matches_px_bench_category_order():
    assert TAXONOMY_VERSION == "1.0"
    assert [category.id for category in CATEGORIES] == [
        "intent_fidelity",
        "product_fit",
        "visual_craft",
        "convention_adherence",
        "pathway_completeness",
        "content_language",
        "resilience",
        "accessibility",
    ]
    assert len(CATEGORY_BY_ID) == 8

