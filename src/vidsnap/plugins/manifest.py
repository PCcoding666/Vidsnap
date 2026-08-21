"""Strict manifest contract for approved VidSnap plugins."""

from __future__ import annotations

from typing import Literal

from pydantic import Field, model_validator
from typing_extensions import Self

from vidsnap.contracts.models import StrictModel


class PluginManifest(StrictModel):
    """The versioned identity every loadable plugin must declare."""

    api_version: Literal["vidsnap.plugin/v1"] = "vidsnap.plugin/v1"
    id: str = Field(pattern=r"^[a-z][a-z0-9_.-]*$")
    version: str = Field(pattern=r"^\d+\.\d+\.\d+$")
    kind: Literal["tool", "policy", "task", "observer"]
    provides: tuple[str, ...] = ()
    requires: tuple[str, ...] = ()
    model_visible: bool = False

    @model_validator(mode="after")
    def _only_tools_may_be_model_visible(self) -> Self:
        if self.model_visible and self.kind != "tool":
            raise ValueError(
                f"model_visible must be false for kind '{self.kind}': "
                "only tool plugins may be exposed to the model"
            )
        return self
