"""Pruebas de app/domain/history.py contra un repo bare real, construido
con el propio binario de git -- sin red, sin gestor-db, sin storage.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from app.domain import git_ops, history


async def _run(args: list[str], cwd: Path | None = None) -> None:
    await git_ops.run_git(args, cwd=cwd)


@pytest.fixture
async def bare_repo(tmp_path: Path) -> Path:
    work = tmp_path / "work"
    work.mkdir()
    await _run(["init", "-q", "-b", "main", str(work)])
    await _run(["config", "user.email", "test@freya.local"], cwd=work)
    await _run(["config", "user.name", "Test User"], cwd=work)

    (work / "a.txt").write_text("hello\n")
    await _run(["add", "a.txt"], cwd=work)
    await _run(["commit", "-q", "-m", "first commit"], cwd=work)

    (work / "a.txt").write_text("hello\nworld\n")
    (work / "b.txt").write_text("second file\n")
    await _run(["add", "-A"], cwd=work)
    await _run(["commit", "-q", "-m", "second commit"], cwd=work)

    bare = tmp_path / "bare"
    await _run(["clone", "-q", "--bare", str(work), str(bare)])
    await _run(["symbolic-ref", "HEAD", "refs/heads/main"], cwd=bare)
    return bare


async def test_list_branches(bare_repo: Path) -> None:
    branches = await history.list_branches(bare_repo, "main")
    assert len(branches) == 1
    assert branches[0]["name"] == "main"
    assert branches[0]["is_default"] is True


async def test_list_commits_orden_y_stats(bare_repo: Path) -> None:
    commits = await history.list_commits(
        bare_repo,
        branch="main",
        limit=10,
        offset=0,
        author=None,
        since=None,
        until=None,
    )
    assert len(commits) == 2
    assert commits[0]["message"] == "second commit"
    assert commits[1]["message"] == "first commit"
    assert commits[0]["stats"]["files_changed"] == 2
    assert commits[0]["author"]["name"] == "Test User"


async def test_list_commits_paginacion(bare_repo: Path) -> None:
    page = await history.list_commits(
        bare_repo,
        branch="main",
        limit=1,
        offset=0,
        author=None,
        since=None,
        until=None,
    )
    assert len(page) == 1
    assert page[0]["message"] == "second commit"

    next_page = await history.list_commits(
        bare_repo,
        branch="main",
        limit=1,
        offset=1,
        author=None,
        since=None,
        until=None,
    )
    assert len(next_page) == 1
    assert next_page[0]["message"] == "first commit"


async def test_create_and_list_tag(bare_repo: Path) -> None:
    await history.create_tag(
        bare_repo,
        name="v1.0.0",
        target_commit="main",
        message="primera release",
        tagger_name="Test User",
        tagger_email="test@freya.local",
    )
    tags = await history.list_tags(bare_repo)
    assert len(tags) == 1
    assert tags[0]["name"] == "v1.0.0"
    assert tags[0]["message"] == "primera release"
    assert tags[0]["tagger"]["name"] == "Test User"


def test_validate_tag_name_semver() -> None:
    history.validate_tag_name("v1.2.3")
    history.validate_tag_name("v1.2.3-beta.1")
    with pytest.raises(Exception):
        history.validate_tag_name("1.2.3")
    with pytest.raises(Exception):
        history.validate_tag_name("latest")


async def test_create_and_delete_branch(bare_repo: Path) -> None:
    commits = await history.list_commits(
        bare_repo,
        branch="main",
        limit=10,
        offset=0,
        author=None,
        since=None,
        until=None,
    )
    first_sha = commits[-1]["hash"]

    await history.create_branch(bare_repo, name="feature-x", from_commit=first_sha)
    branches = {b["name"] for b in await history.list_branches(bare_repo, "main")}
    assert "feature-x" in branches

    await history.delete_branch(bare_repo, name="feature-x", default_branch="main")
    branches = {b["name"] for b in await history.list_branches(bare_repo, "main")}
    assert "feature-x" not in branches


async def test_no_se_puede_borrar_la_rama_por_defecto(bare_repo: Path) -> None:
    with pytest.raises(Exception):
        await history.delete_branch(bare_repo, name="main", default_branch="main")
    branches = {b["name"] for b in await history.list_branches(bare_repo, "main")}
    assert "main" in branches


async def test_diff_entre_commits(bare_repo: Path) -> None:
    commits = await history.list_commits(
        bare_repo,
        branch="main",
        limit=10,
        offset=0,
        author=None,
        since=None,
        until=None,
    )
    head_sha, first_sha = commits[0]["hash"], commits[-1]["hash"]

    result = await history.diff(bare_repo, base=first_sha, head=head_sha, path=None)
    assert result["commits_ahead"] == 1
    assert result["stats"]["files_changed"] == 2
    paths = {f["path"] for f in result["files"]}
    assert paths == {"a.txt", "b.txt"}


async def test_tree_lista_el_directorio_raiz(bare_repo: Path) -> None:
    entries = await history.tree(bare_repo, ref="main", path="")
    names = {e["name"] for e in entries}
    assert names == {"a.txt", "b.txt"}
    assert all(e["type"] == "file" for e in entries)


async def test_rev_parse_falla_con_ref_inexistente(bare_repo: Path) -> None:
    with pytest.raises(Exception):
        await history.diff(bare_repo, base="no-existe", head="main", path=None)
