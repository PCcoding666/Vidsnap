"""Stateless local FastAPI adapter behavior."""

import httpx
import pytest

from vidsnap.api import DEFAULT_HOST, create_app
from vidsnap.contracts import TerminalState
from vidsnap.harness import HarnessRunResult


@pytest.mark.asyncio
async def test_api_is_local_stateless_health_surface() -> None:
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=create_app()),
        base_url="http://testserver",
    ) as client:
        response = await client.get("/health")

    assert response.status_code == 200
    assert response.json()["stateful_jobs"] is False
    assert response.json()["default_host"] == DEFAULT_HOST


@pytest.mark.asyncio
async def test_api_rejects_request_keys_and_cleans_the_temporary_run_bundle() -> None:
    seen_run_paths = []

    class FakeHarness:
        async def run(self, source, goal, policy):
            del source, goal
            assert policy.output_dir is not None
            seen_run_paths.append(policy.output_dir)
            return HarnessRunResult(
                terminal_state=TerminalState.NO_OP,
                run_path=policy.output_dir,
            )

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=create_app(lambda: FakeHarness())),
        base_url="http://testserver",
    ) as client:
        rejected = await client.post(
            "/v1/analyze",
            json={
                "source": {"path": "/tmp/input.mp4"},
                "goal": {"objective": "Summarize"},
                "api_key": "must-not-be-accepted",
            },
        )
        response = await client.post(
            "/v1/analyze",
            json={
                "source": {"path": "/tmp/input.mp4"},
                "goal": {"objective": "Summarize"},
            },
        )

    assert rejected.status_code == 422
    assert response.json()["terminal_state"] == "NO_OP"
    assert len(seen_run_paths) == 1
    assert not seen_run_paths[0].exists()
