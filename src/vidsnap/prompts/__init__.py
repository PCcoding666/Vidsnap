"""Versioned prompt assets and safe rendering for untrusted video evidence."""

from __future__ import annotations

import json
from dataclasses import dataclass
from importlib.resources import files
from typing import Any


@dataclass(frozen=True, slots=True)
class PromptAsset:
    """A versioned template bound to a LoopSpec and fixed model configuration."""

    prompt_id: str
    version: str
    input_schema: str
    output_schema: str
    loop_spec_sha256: str
    model_config: dict[str, Any]
    template: str

    @classmethod
    def from_dict(cls, value: object) -> PromptAsset:
        """Validate the narrow metadata fields required for a prompt asset."""
        if not isinstance(value, dict):
            raise ValueError("prompt asset must be an object")
        required = {
            "prompt_id",
            "version",
            "input_schema",
            "output_schema",
            "loop_spec_sha256",
            "model_config",
            "template",
        }
        if set(value) != required:
            raise ValueError("prompt asset has unexpected or missing metadata")
        model_config = value["model_config"]
        if not isinstance(model_config, dict):
            raise ValueError("model_config must be an object")
        string_fields = required - {"model_config"}
        if any(not isinstance(value[field], str) or not value[field] for field in string_fields):
            raise ValueError("prompt metadata fields must be non-empty strings")
        return cls(
            prompt_id=value["prompt_id"],
            version=value["version"],
            input_schema=value["input_schema"],
            output_schema=value["output_schema"],
            loop_spec_sha256=value["loop_spec_sha256"],
            model_config=model_config,
            template=value["template"],
        )

    def render(self, input_data: dict[str, Any]) -> str:
        """Render JSON inputs as quarantined data rather than executable instructions."""
        return (
            f"{self.template}\n\n"
            "<untrusted-input-json>\n"
            f"{json.dumps(input_data, ensure_ascii=True, separators=(',', ':'), sort_keys=True)}\n"
            "</untrusted-input-json>"
        )


def load_prompt_assets() -> dict[str, PromptAsset]:
    """Load the five shipped prompt layers from package resources."""
    resources = files("vidsnap.prompts")
    return {
        resource.name.removesuffix(".json"): PromptAsset.from_dict(json.loads(resource.read_text()))
        for resource in sorted(resources.iterdir(), key=lambda item: item.name)
        if resource.name.endswith(".json")
    }
