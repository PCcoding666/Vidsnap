"""LoopSpec conformance contracts.

These tests catch an accidental expansion of the executable surface or a
change to the published budget envelope without a versioned contract change.
"""

from vidsnap.contracts import TerminalState, default_loop_spec


def test_default_loop_spec_is_versioned_bounded_and_stable() -> None:
    spec = default_loop_spec()

    assert spec.api_version == "vidsnap.loop/v1"
    assert spec.id == "grounded-video-understanding"
    assert spec.allowed_skills == (
        "probe_media",
        "transcribe_audio",
        "sample_evidence",
        "inspect_evidence",
        "synthesize_result",
        "verify_claims",
    )
    assert spec.budgets.max_iterations == 3
    assert spec.budgets.max_model_calls == 12
    assert spec.budgets.max_evidence_frames == 96
    assert spec.budgets.max_wall_seconds == 900
    assert TerminalState.SUCCEEDED in spec.terminal_states
    assert len(spec.digest()) == 64
    assert spec.digest() == default_loop_spec().digest()
