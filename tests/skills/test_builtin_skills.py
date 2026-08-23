"""LoopSpec skill allow-list behavior."""

import pytest

from vidsnap.contracts import default_loop_spec
from vidsnap.skills import SkillRegistry


async def _no_op(context: object) -> None:
    del context


def test_registry_only_exposes_loopspec_approved_skills() -> None:
    registry = SkillRegistry(default_loop_spec())
    for name in default_loop_spec().allowed_skills:
        registry.register(name, _no_op)

    assert registry.names() == default_loop_spec().allowed_skills
    with pytest.raises(ValueError):
        registry.register("arbitrary_tool", _no_op)
