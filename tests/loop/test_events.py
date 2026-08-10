"""Run-event ledger behavior."""

import json

from vidsnap.loop.events import RunEvent


def test_event_serialization_is_timestamped_and_json_compatible() -> None:
    event = RunEvent(sequence=1, phase="probe", payload={"duration_seconds": 3.0})

    serialized = event.model_dump(mode="json")
    assert serialized["sequence"] == 1
    assert serialized["phase"] == "probe"
    assert serialized["payload"] == {"duration_seconds": 3.0}
    assert json.loads(event.to_json()) == serialized
