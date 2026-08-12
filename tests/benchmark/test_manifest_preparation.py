"""Pre-registered public-case selection for external benchmark manifests."""

from collections import Counter

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


def test_mvbench_formal_selection_covers_three_temporal_task_families() -> None:
    """The MVBench slice must not stand in for one action-antonym task."""
    family_counts = Counter(item.task_family for item in FORMAL_SELECTION["MVBench"])

    assert len(family_counts) >= 3
    assert min(family_counts.values()) >= 4
    assert all("temporal" in item.requirements for item in FORMAL_SELECTION["MVBench"])


def test_every_registered_case_has_independent_tool_label_and_reason() -> None:
    """Tool labels must be explicit fields, not derived from evidence requirements."""
    reason_to_tools = {
        "speech-required": ("transcribe_audio",),
        "visual-required": ("sample_evidence",),
        "both-required": ("transcribe_audio", "sample_evidence"),
        "no-acquisition-required": (),
    }
    items = [
        item
        for selection in (SMOKE_SELECTION, FORMAL_SELECTION)
        for registered in selection.values()
        for item in registered
    ]

    assert all(
        item.expected_tools == reason_to_tools[item.tool_annotation_reason] for item in items
    )
