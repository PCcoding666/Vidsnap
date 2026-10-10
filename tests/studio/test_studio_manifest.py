import json

import pytest

from vidsnap.studio.manifest import StudioManifest, load_studio_manifest

API_VERSION = "vidsnap.studio/v1"


def make_trial(trial_id="t1", run="runs/v0/case-01/t1"):
    return {"trial_id": trial_id, "run": run}


def make_case(case_id="case-01", held_out=False, trials=None):
    return {
        "case_id": case_id,
        "held_out": held_out,
        "trials": trials if trials is not None else [make_trial()],
    }


def make_version(version="v0", cases=None):
    return {
        "version": version,
        "summary": f"{version} summary",
        "cases": cases if cases is not None else [make_case()],
    }


def minimal_payload():
    return {
        "api_version": API_VERSION,
        "iteration": {
            "agent_id": "video-summarizer",
            "versions": [make_version()],
        },
    }


def write_manifest(root, payload):
    root.mkdir(parents=True, exist_ok=True)
    path = root / "studio.json"
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def create_run(root, relative_run):
    run_dir = root / relative_run
    run_dir.mkdir(parents=True)
    (run_dir / "manifest.json").write_text("{}", encoding="utf-8")
    return run_dir


def test_strict_extra_field_rejection():
    payload = minimal_payload()
    payload["unexpected"] = True
    with pytest.raises(ValueError):
        StudioManifest.model_validate(payload)


def test_api_version_must_be_exact():
    payload = minimal_payload()
    payload["api_version"] = "vidsnap.studio/v2"
    with pytest.raises(ValueError):
        StudioManifest.model_validate(payload)


def test_at_least_one_workspace_is_required():
    with pytest.raises(ValueError):
        StudioManifest.model_validate({"api_version": API_VERSION})


@pytest.mark.parametrize("versions", [["v1"], ["v0", "v2"], ["v0", "v1", "v3"]])
def test_versions_must_be_contiguous_v0_through_vn(versions):
    payload = minimal_payload()
    payload["iteration"]["versions"] = [
        make_version(
            version,
            cases=[
                make_case(
                    case_id=f"case-{version}",
                    trials=[make_trial(run=f"runs/{version}/case-{version}/t1")],
                )
            ],
        )
        for version in versions
    ]
    with pytest.raises(ValueError):
        StudioManifest.model_validate(payload)


def test_duplicate_case_in_one_version_is_rejected():
    payload = minimal_payload()
    payload["iteration"]["versions"][0]["cases"] = [
        make_case(case_id="case-01", trials=[make_trial("t1", "runs/v0/case-01/t1")]),
        make_case(case_id="case-01", trials=[make_trial("t2", "runs/v0/case-01/t2")]),
    ]
    with pytest.raises(ValueError):
        StudioManifest.model_validate(payload)


def test_same_case_across_v0_and_v1_is_accepted():
    payload = minimal_payload()
    payload["iteration"]["versions"] = [
        make_version(
            "v0",
            cases=[make_case(case_id="case-01", trials=[make_trial(run="runs/v0/case-01/t1")])],
        ),
        make_version(
            "v1",
            cases=[make_case(case_id="case-01", trials=[make_trial(run="runs/v1/case-01/t1")])],
        ),
    ]

    manifest = StudioManifest.model_validate(payload)

    assert [version.version for version in manifest.iteration.versions] == ["v0", "v1"]
    assert [version.cases[0].case_id for version in manifest.iteration.versions] == [
        "case-01",
        "case-01",
    ]


def test_duplicate_trial_in_one_version_case_is_rejected():
    payload = minimal_payload()
    payload["iteration"]["versions"][0]["cases"][0]["trials"] = [
        make_trial("t1", "runs/v0/case-01/t1"),
        make_trial("t1", "runs/v0/case-01/t1-copy"),
    ]
    with pytest.raises(ValueError):
        StudioManifest.model_validate(payload)


def test_safe_relative_posix_run_reference_loads(tmp_path):
    root = tmp_path / "manifest_root"
    create_run(root, "runs/v0/case-01/t1")
    path = write_manifest(root, minimal_payload())

    manifest = load_studio_manifest(path)

    assert isinstance(manifest, StudioManifest)
    assert manifest.iteration.versions[0].cases[0].trials[0].run == "runs/v0/case-01/t1"


@pytest.mark.parametrize(
    "reference",
    [
        "../escape",
        "/tmp/escape",
        "https://example.test/run",
        "file:///tmp/run",
        "data:application/json,{}",
        "runs\\v0\\case-01\\t1",
    ],
)
def test_run_references_reject_escape_absolute_urls_and_backslashes(tmp_path, reference):
    root = tmp_path / "manifest_root"
    payload = minimal_payload()
    payload["iteration"]["versions"][0]["cases"][0]["trials"][0]["run"] = reference
    path = write_manifest(root, payload)

    with pytest.raises(ValueError):
        load_studio_manifest(path)


def test_symlink_run_reference_escape_is_rejected(tmp_path):
    root = tmp_path / "nested" / "manifest_root"
    outside = tmp_path / "nested" / "outside"
    create_run(outside, "t1")
    root.mkdir(parents=True)
    (root / "runs").symlink_to(outside, target_is_directory=True)

    payload = minimal_payload()
    payload["iteration"]["versions"][0]["cases"][0]["trials"][0]["run"] = "runs/t1"
    path = write_manifest(root, payload)

    with pytest.raises(ValueError):
        load_studio_manifest(path)


def test_missing_referenced_run_manifest_is_rejected(tmp_path):
    root = tmp_path / "manifest_root"
    (root / "runs/v0/case-01/t1").mkdir(parents=True)
    path = write_manifest(root, minimal_payload())

    with pytest.raises(ValueError):
        load_studio_manifest(path)


def test_run_manifest_symlink_escape_is_rejected(tmp_path):
    root = tmp_path / "manifest_root"
    outside = tmp_path / "outside"
    outside.mkdir()
    outside_manifest = outside / "manifest.json"
    outside_manifest.write_text("{}", encoding="utf-8")
    run_dir = root / "runs/v0/case-01/t1"
    run_dir.mkdir(parents=True)
    (run_dir / "manifest.json").symlink_to(outside_manifest)
    path = write_manifest(root, minimal_payload())

    with pytest.raises(ValueError):
        load_studio_manifest(path)


def make_exploration():
    return {
        "problem": {"statement": "task", "constraints": ["constraint-1"]},
        "approaches": [
            {
                "id": "simple-prompt",
                "label": "Simple prompt",
                "synthetic": True,
                "harness": {
                    "max_model_calls": 12,
                    "max_tool_calls": 6,
                    "tools": ["transcribe_audio"],
                },
                "trials": [make_trial("t1", "runs/simple-prompt/t1")],
            }
        ],
    }


@pytest.mark.parametrize("field_name", ["max_model_calls", "max_tool_calls"])
@pytest.mark.parametrize("value", [True, False])
def test_harness_budget_rejects_booleans(field_name, value):
    payload = minimal_payload()
    payload["exploration"] = make_exploration()
    payload["exploration"]["approaches"][0]["harness"][field_name] = value

    with pytest.raises(ValueError):
        StudioManifest.model_validate(payload)


def test_loader_validation_failure_is_category_only(tmp_path):
    root = tmp_path / "manifest_root"
    create_run(root, "runs/v0/case-01/t1")
    probe = "zqxwv-unique-probe-value"
    payload = minimal_payload()
    payload["title"] = probe * 80
    path = write_manifest(root, payload)

    with pytest.raises(ValueError) as excinfo:
        load_studio_manifest(path)

    message = str(excinfo.value)
    assert probe not in message
    assert "manifest" in message


def test_contiguous_version_failure_is_category_only(tmp_path):
    root = tmp_path / "manifest_root"
    payload = minimal_payload()
    payload["iteration"]["versions"] = [
        make_version(
            "v0",
            cases=[make_case(case_id="case-v0", trials=[make_trial(run="runs/v0/case-v0/t1")])],
        ),
        make_version(
            "v7",
            cases=[make_case(case_id="case-v7", trials=[make_trial(run="runs/v7/case-v7/t1")])],
        ),
    ]
    path = write_manifest(root, payload)

    with pytest.raises(ValueError) as excinfo:
        load_studio_manifest(path)

    message = str(excinfo.value)
    assert "v7" not in message
    assert "case-v7" not in message


@pytest.mark.parametrize(
    "key",
    ["api_key", "apiKey", "api-key", "authorization", "cookie", "password", "secret", "token"],
)
def test_credential_bearing_keys_are_rejected_without_echo(tmp_path, key):
    root = tmp_path / "manifest_root"
    create_run(root, "runs/v0/case-01/t1")
    value = "value-that-must-not-echo"
    payload = minimal_payload()
    payload[key] = value
    path = write_manifest(root, payload)

    with pytest.raises(ValueError) as excinfo:
        load_studio_manifest(path)

    message = str(excinfo.value)
    assert value not in message
    assert key not in message


@pytest.mark.parametrize(
    "value",
    ["Bearer zqxwce123456", "sk-a1b2c3d4e5f6a1b2c3d4e5f6"],
)
def test_credential_shaped_values_are_rejected_without_echo(tmp_path, value):
    root = tmp_path / "manifest_root"
    create_run(root, "runs/v0/case-01/t1")
    payload = minimal_payload()
    payload["iteration"]["versions"][0]["summary"] = value
    path = write_manifest(root, payload)

    with pytest.raises(ValueError) as excinfo:
        load_studio_manifest(path)

    message = str(excinfo.value)
    assert value not in message


@pytest.mark.parametrize(
    "prose",
    [
        "Report token usage without credentials",
        "Never expose a secret in reports",
    ],
)
def test_ordinary_prose_summaries_are_accepted(tmp_path, prose):
    root = tmp_path / "manifest_root"
    create_run(root, "runs/v0/case-01/t1")
    payload = minimal_payload()
    payload["iteration"]["versions"][0]["summary"] = prose
    path = write_manifest(root, payload)

    manifest = load_studio_manifest(path)

    assert manifest.iteration.versions[0].summary == prose


@pytest.mark.parametrize(
    "value",
    [
        "BEARER abc123def456",
        "api_key=abcdef123456",
        "api-key: abcdef123456",
        "password=hunter-2-rotate",
        "token: abcdef123456",
        "secret=s3cr3t-value-12345",
    ],
)
def test_credential_assignment_shapes_are_rejected_without_echo(tmp_path, value):
    root = tmp_path / "manifest_root"
    create_run(root, "runs/v0/case-01/t1")
    payload = minimal_payload()
    payload["iteration"]["versions"][0]["summary"] = value
    path = write_manifest(root, payload)

    with pytest.raises(ValueError) as excinfo:
        load_studio_manifest(path)

    message = str(excinfo.value)
    assert value not in message


def test_schema_failure_has_no_exception_chain(tmp_path):
    root = tmp_path / "manifest_root"
    create_run(root, "runs/v0/case-01/t1")
    payload = minimal_payload()
    payload["title"] = "zqxwv-unique-probe-value" * 80
    path = write_manifest(root, payload)

    with pytest.raises(ValueError) as excinfo:
        load_studio_manifest(path)

    assert excinfo.value.__cause__ is None
