# Article recipe v2: approved first batch

The user approved implementation of visual caption checking, targeted frame repair,
and one editorial revision round. This specification records that decision.

Expose `--recipe-version v2`, keeping v1 as the default. Keep ArticleOutput and
RunBundle v1 compatible; add versioned, validated review artifacts. Pin the same
SynthesisPort for drafting, visual review, patching and final review. Core owns
all model/tool/iteration budgets. No new network clients, provider switching,
media access outside ports, publishing, UI, or data migration.

Initial sampling consumes at most 32 of 96 frames. Review each cited image with
its caption and surrounding article; missing images or review entries never pass.
Report supported / contradicted / insufficient evidence, and section-level editing
issues. Resample up to three affected windows directly (at most 24 new frames),
then patch only flagged sections once. Re-review the resulting article. Remaining
issues mean PARTIAL; failures retain the last valid draft. All calls and artifacts
are auditable. A review is a model judgment, not a guarantee of factual correctness.

Tests use synthetic frames and scripted ports only. Exact public gates must pass.
Real-video quality comparison remains a separate live validation.
