"""Typed local-provider ports; credentials never cross the API boundary."""

from vidsnap.providers.base import (
    AgentDecisionFormatError,
    AgentDecisionResponse,
    AgentModelPort,
    AgentStepRequest,
    ModelResponse,
    ProviderError,
    ProviderIdentity,
    ProviderPlugin,
    ProviderProtocol,
    ProviderUnavailable,
    ToolPlanningPort,
    ToolPlanResponse,
)
from vidsnap.providers.discovery import (
    PROVIDER_ENTRY_POINT_GROUP,
    discover_allowed_providers,
)
from vidsnap.providers.mock import MockProvider
from vidsnap.providers.qwen import QwenCompatibleClient, QwenProfile, QwenProvider
from vidsnap.providers.testing import assert_provider_contract

__all__ = [
    "AgentDecisionFormatError",
    "AgentDecisionResponse",
    "AgentModelPort",
    "AgentStepRequest",
    "MockProvider",
    "ModelResponse",
    "PROVIDER_ENTRY_POINT_GROUP",
    "ProviderError",
    "ProviderIdentity",
    "ProviderPlugin",
    "ProviderProtocol",
    "ProviderUnavailable",
    "QwenCompatibleClient",
    "QwenProfile",
    "QwenProvider",
    "ToolPlanningPort",
    "ToolPlanResponse",
    "assert_provider_contract",
    "discover_allowed_providers",
]
