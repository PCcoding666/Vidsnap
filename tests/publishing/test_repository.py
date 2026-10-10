"""RED-first tests: real repository-root detection instead of a blind cwd.

These tests specify find_repository_root: walk up from a start path and return
the nearest ancestor marked by .git (directory or worktree file) or by
pyproject.toml beside src/vidsnap, resolving relative starts; when the start
tree is unmarked, walk the installed vidsnap package's ancestors to a marked
repository root so editable installs keep protecting the real repository, and
only fall back to the package directory itself when no package ancestor is
marked. They import vidsnap.publishing.repository, which does not exist yet.
"""

from pathlib import Path

import vidsnap
from vidsnap.publishing.repository import find_repository_root


def _marked_with_git_dir(root: Path) -> Path:
    (root / ".git").mkdir(parents=True)
    return root


def _marked_with_pyproject(root: Path) -> Path:
    root.mkdir(parents=True, exist_ok=True)
    (root / "pyproject.toml").write_text("[project]\nname = 'vidsnap'\n", encoding="utf-8")
    (root / "src" / "vidsnap").mkdir(parents=True)
    return root


def test_git_directory_marker_is_found_from_nested_subdir(tmp_path: Path) -> None:
    root = _marked_with_git_dir(tmp_path / "repo")
    nested = root / "src" / "deep"
    nested.mkdir(parents=True)

    assert find_repository_root(nested) == root.resolve()


def test_git_worktree_file_marker_is_found(tmp_path: Path) -> None:
    root = tmp_path / "worktree"
    root.mkdir()
    (root / ".git").write_text("gitdir: /elsewhere/.git/worktrees/x", encoding="utf-8")

    assert find_repository_root(root / "sub" / "deeper") == root.resolve()


def test_pyproject_and_src_marker_is_found(tmp_path: Path) -> None:
    root = _marked_with_pyproject(tmp_path / "repo")

    assert find_repository_root(root / "src" / "vidsnap" / "publishing") == root.resolve()


def test_pyproject_without_src_layout_is_not_a_root(tmp_path: Path) -> None:
    decoy = tmp_path / "decoy"
    decoy.mkdir()
    (decoy / "pyproject.toml").write_text("[project]\n", encoding="utf-8")

    assert find_repository_root(decoy / "sub") != decoy.resolve()


def test_nearest_marked_ancestor_wins(tmp_path: Path) -> None:
    outer = _marked_with_git_dir(tmp_path / "outer")
    inner = _marked_with_git_dir(outer / "inner")

    assert find_repository_root(inner / "pkg") == inner.resolve()


def test_relative_start_is_resolved(tmp_path: Path, monkeypatch) -> None:
    root = _marked_with_git_dir(tmp_path / "repo")
    nested = root / "nested"
    nested.mkdir()
    monkeypatch.chdir(nested)

    assert find_repository_root(Path(".")) == root.resolve()


def test_unmarked_cwd_falls_back_to_marked_repo_around_editable_package(
    tmp_path: Path, monkeypatch
) -> None:
    """An editable install must protect its real repository from an external cwd."""
    repo = _marked_with_git_dir(tmp_path / "repo")
    package_init = repo / "src" / "vidsnap" / "__init__.py"
    package_init.parent.mkdir(parents=True)
    package_init.write_text("__version__ = '0'\n", encoding="utf-8")
    monkeypatch.setattr(vidsnap, "__file__", str(package_init))

    external = tmp_path / "elsewhere" / "deep"
    external.mkdir(parents=True)

    root = find_repository_root(external)

    assert root == repo.resolve()
    assert Path(vidsnap.__file__).resolve().parent.is_relative_to(root)


def test_fallback_is_package_dir_when_no_package_ancestor_is_marked(
    tmp_path: Path, monkeypatch
) -> None:
    package_init = tmp_path / "site" / "vidsnap" / "__init__.py"
    package_init.parent.mkdir(parents=True)
    package_init.write_text("__version__ = '0'\n", encoding="utf-8")
    monkeypatch.setattr(vidsnap, "__file__", str(package_init))

    external = tmp_path / "elsewhere" / "deep"
    external.mkdir(parents=True)

    assert find_repository_root(external) == package_init.resolve().parent
