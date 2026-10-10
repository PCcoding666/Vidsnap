"""Publishing task adapter: adapter-private transcript and a strict draft schema."""

from __future__ import annotations

import re
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Protocol

from pydantic import Field, JsonValue, model_validator
from typing_extensions import Self

from vidsnap.contracts import Evidence, VideoGoal
from vidsnap.contracts.agent import ProviderUsage
from vidsnap.contracts.models import StrictModel
from vidsnap.tasks.base import TaskVerification
from vidsnap.video.probe import MediaProbe

_MAX_IMAGE_EVIDENCE_IDS = 12
IMAGE_PLACEHOLDER_PATTERN = re.compile(r"\[\[image:([^\[\]]+)\]\]")


class PublishingDraft(StrictModel):
    """Strict in-memory publishing draft: non-empty texts and bounded unique frame ids."""

    article: str = Field(min_length=1)
    summary: str = Field(min_length=1)
    image_evidence_ids: tuple[str, ...] = Field(min_length=1, max_length=_MAX_IMAGE_EVIDENCE_IDS)

    @model_validator(mode="after")
    def validate_image_evidence_ids(self) -> Self:
        if len(set(self.image_evidence_ids)) != len(self.image_evidence_ids):
            raise ValueError("image_evidence_ids must not contain duplicates")
        return self

    @model_validator(mode="after")
    def validate_article_placeholders(self) -> Self:
        placeholders = tuple(IMAGE_PLACEHOLDER_PATTERN.findall(self.article))
        if placeholders != self.image_evidence_ids:
            raise ValueError(
                "article image placeholders must match image_evidence_ids "
                "exactly in order, count, and uniqueness"
            )
        return self


@dataclass(frozen=True, slots=True)
class PublishingModelResponse:
    """One schema-valid publishing draft plus provider-reported usage counters."""

    draft: PublishingDraft
    input_tokens: int = 0
    output_tokens: int = 0
    input_bytes: int = 0
    usage_reported: bool = False


class PublishingModelPort(Protocol):
    """The only model operation the publishing task may invoke."""

    async def draft_deliverables(
        self,
        evidence: Sequence[Evidence],
        transcript: str | None,
        probe: MediaProbe,
    ) -> PublishingModelResponse:
        """Produce a schema-valid draft for captured evidence and a private transcript."""


class PublishingTaskAdapter:
    """Kernel seam for the publishing task; the transcript never enters evidence."""

    output_model: type[PublishingDraft] = PublishingDraft

    def __init__(self, *, goal: VideoGoal, transcript: str | None = None) -> None:
        self.goal = goal
        self._transcript = transcript

    async def request_final(
        self,
        model: PublishingModelPort,
        evidence: Sequence[Evidence],
        probe: MediaProbe,
    ) -> tuple[PublishingDraft, ProviderUsage]:
        """Run the one publishing model call and map only reported token counters."""
        response = await model.draft_deliverables(evidence, self._transcript, probe)
        usage = ProviderUsage(
            model_calls=1,
            input_bytes=response.input_bytes,
            input_tokens=response.input_tokens,
            output_tokens=response.output_tokens,
            reported=response.usage_reported,
        )
        return response.draft, usage

    def parse_final(self, payload: dict[str, JsonValue]) -> PublishingDraft:
        """Accept only the strict PublishingDraft schema."""
        return PublishingDraft.model_validate(payload)

    def verify(
        self,
        output: PublishingDraft,
        evidence: Sequence[Evidence],
        probe: MediaProbe,
    ) -> TaskVerification:
        """Accept only image ids that exist in captured evidence and are frames."""
        del probe
        known_frame_ids = {item.id for item in evidence if item.modality == "frame"}
        images_known = all(
            evidence_id in known_frame_ids for evidence_id in output.image_evidence_ids
        )
        gates = {
            "draft_schema": True,
            "image_evidence_known": images_known,
        }
        return TaskVerification(passed=images_known, gates=gates)
