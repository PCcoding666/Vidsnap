"""Direct-vs-Harness fairness contracts."""

from pathlib import Path

from vidsnap.benchmark.runners import DirectRunner, HarnessRunner, Transcript


class FakeBenchmarkModel:
    def __init__(self) -> None:
        self.video_requests = []
        self.evidence_requests = []

    def prepare_video(self, request) -> None:
        self.video_requests.append(request)

    def prepare_evidence(self, request) -> None:
        self.evidence_requests.append(request)


def test_direct_runner_sets_explicit_two_fps_baseline() -> None:
    model = FakeBenchmarkModel()
    runner = DirectRunner(model=model)

    runner.prepare(Path("video.mp4"), transcript=None)

    assert model.video_requests[0].fps == 2


def test_direct_asr_and_harness_full_share_the_same_transcript_object() -> None:
    model = FakeBenchmarkModel()
    transcript = Transcript(text="shared ASR transcript", source_sha256="a" * 64)

    DirectRunner(model=model).prepare(Path("video.mp4"), transcript=transcript)
    HarnessRunner(model=model).prepare(Path("video.mp4"), transcript=transcript)

    assert model.video_requests[0].transcript is transcript
    assert model.evidence_requests[0].transcript is transcript
