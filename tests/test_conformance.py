"""Offline release-conformance behavior."""

from vidsnap.conformance import run_conformance


def test_conformance_passes_for_default_package() -> None:
    report = run_conformance()

    assert report.passed is True
    assert report.checks["loop_spec"] == "passed"
