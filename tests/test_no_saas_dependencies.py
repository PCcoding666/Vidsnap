"""Repository boundary test for the approved SaaS-to-Harness migration."""

import importlib.metadata
from pathlib import Path


def test_repository_has_no_saas_runtime_tree() -> None:
    root = Path(__file__).parents[1]

    assert not (root / "frontend").exists()
    assert not (root / "backend").exists()
    forbidden = ("sqlalchemy", "fastapi_users", "celery", "redis", "oauth", "smtp", "jwt")
    runtime = "\n".join(
        path.read_text(errors="ignore")
        for path in (root / "src").rglob("*.py")
        if path.name != "conformance.py"
    )
    assert not any(token in runtime.lower() for token in forbidden)


def test_declared_runtime_dependencies_exclude_the_saas_stack() -> None:
    forbidden = {
        "sqlalchemy",
        "fastapi-users",
        "celery",
        "redis",
        "uvicorn",
        "pyjwt",
        "python-jose",
        "aiosmtplib",
    }
    required = importlib.metadata.requires("vidsnap-harness") or []
    declared = {
        requirement.split(";")[0].strip().lower().replace("_", "-")
        for requirement in required
        if "extra ==" not in requirement
    }
    assert declared, "package metadata must declare runtime dependencies"
    assert not declared & forbidden
