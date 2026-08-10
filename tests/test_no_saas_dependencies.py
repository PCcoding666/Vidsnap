"""Repository boundary test for the approved SaaS-to-Harness migration."""

from pathlib import Path


def test_repository_has_no_saas_runtime_tree() -> None:
    root = Path(__file__).parents[1]

    assert not (root / "frontend").exists()
    assert not (root / "backend").exists()
    forbidden = ("sqlalchemy", "fastapi_users", "celery", "redis", "oauth", "smtp", "jwt")
    runtime = "\n".join(path.read_text(errors="ignore") for path in (root / "src").rglob("*.py"))
    assert not any(token in runtime.lower() for token in forbidden)
