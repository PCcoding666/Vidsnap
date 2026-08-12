"""Pre-registered public-case selection for external benchmark manifests."""

from vidsnap.benchmark.manifest import FORMAL_SELECTION, SMOKE_SELECTION


def test_registered_selection_has_required_counts_and_no_smoke_overlap() -> None:
    """Changing the 36/18 split or reusing smoke cases must fail this test."""
    assert len(FORMAL_SELECTION["Video-MME"]) == 36
    assert len(FORMAL_SELECTION["MVBench"]) == 18
    assert len(SMOKE_SELECTION["Video-MME"]) == 4
    assert len(SMOKE_SELECTION["MVBench"]) == 2

    formal_ids = {
        (dataset, item.case_id) for dataset, items in FORMAL_SELECTION.items() for item in items
    }
    smoke_ids = {
        (dataset, item.case_id) for dataset, items in SMOKE_SELECTION.items() for item in items
    }
    assert formal_ids.isdisjoint(smoke_ids)


def test_registered_selection_covers_all_evidence_requirements() -> None:
    """A benchmark without visual, speech, and temporal cases is not stratified."""
    requirements = {
        requirement
        for selection in (SMOKE_SELECTION, FORMAL_SELECTION)
        for items in selection.values()
        for item in items
        for requirement in item.requirements
    }
    assert requirements == {"visual", "speech", "temporal"}
