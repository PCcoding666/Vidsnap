"""Task evaluation: eval sets, systems, graders, attribution, reports, human review.

The evaluator runs every item through ``HarnessKernel`` so each run is an
ordinary RunBundle with the v0.1.1 trace; it reads those traces and never keeps
a parallel log. See ``docs/eval.md`` for the method.
"""

from vidsnap.eval.suite import (
    SUITE_SCHEMA,
    EvalItem,
    EvalSuite,
    LoadedSuite,
    load_suite,
    validate_suite,
)

__all__ = [
    "SUITE_SCHEMA",
    "EvalItem",
    "EvalSuite",
    "LoadedSuite",
    "load_suite",
    "validate_suite",
]
