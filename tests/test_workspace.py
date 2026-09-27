"""Tests for federated multi-repository workspace intelligence."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from acco import workspace
from acco.command_handlers.workspace import workspace_main
from acco.packing.contracts import ContextPack


def _repo(path: Path, package: str, dependency: str | None = None) -> None:
    path.mkdir(parents=True)
    deps = {dependency: "workspace:*"} if dependency else {}
    (path / "package.json").write_text(
        json.dumps({"name": package, "dependencies": deps}),
        encoding="utf-8",
    )
    (path / "index.js").write_text(
        f"export const name = {package!r};\n",
        encoding="utf-8",
    )


def test_workspace_manifest_and_cross_repo_dependency_graph(tmp_path):
    """Package manifests should create explicit cross-repository graph edges."""
    frontend = tmp_path / "frontend"
    shared = tmp_path / "shared"
    _repo(frontend, "@app/frontend", "@app/shared")
    _repo(shared, "@app/shared")

    manifest = workspace.init_workspace(
        tmp_path,
        [("frontend", frontend), ("shared", shared)],
    )
    assert [repo.path for repo in manifest.repositories] == ["frontend", "shared"]

    status = workspace.workspace_status(tmp_path)
    assert status["dependency_edges"] == [
        {
            "from": "frontend",
            "to": "shared",
            "reason": "package-dependency",
        }
    ]


def test_workspace_discovery_is_bounded_to_direct_children(tmp_path):
    """Discovery should not recursively crawl arbitrary parent directories."""
    direct = tmp_path / "direct"
    nested = tmp_path / "group" / "nested"
    _repo(direct, "@app/direct")
    _repo(nested, "@app/nested")

    manifest = workspace.init_workspace(tmp_path, discover=True)
    assert [repo.name for repo in manifest.repositories] == ["direct"]


def test_workspace_pack_allocates_global_budget_and_preserves_provenance(
    tmp_path, monkeypatch
):
    """Federation should keep repository-local retrieval authoritative."""
    frontend = tmp_path / "frontend"
    backend = tmp_path / "backend"
    shared = tmp_path / "shared"
    _repo(frontend, "@app/frontend")
    _repo(backend, "@app/backend")
    _repo(shared, "@app/shared")
    workspace.init_workspace(
        tmp_path,
        [("frontend", frontend), ("backend", backend), ("shared", shared)],
    )

    score_by_root = {
        "frontend": 90.0,
        "backend": 10.0,
        "shared": 2.0,
    }
    calls = []

    class FakeService:
        def __init__(self, root):
            self.root = Path(root)

        def explain_ranking(self, query, **kwargs):
            del query, kwargs
            return {
                "results": [
                    {"final_score": score_by_root[self.root.name]},
                ]
            }

        def build_context(self, query, **kwargs):
            calls.append((self.root.name, query, kwargs["max_tokens"]))
            text = f"{self.root.name} evidence\n" + "x " * min(80, kwargs["max_tokens"] // 4)
            return ContextPack(
                text=text,
                estimated_tokens=min(80, kwargs["max_tokens"] // 4),
                scanned_files=3,
                selected_files=[f"{self.root.name}.js"],
                ranked=[],
            )

    monkeypatch.setattr(workspace, "RepositoryContextService", FakeService)
    result = workspace.build_workspace_context(
        tmp_path,
        "frontend authentication",
        max_tokens=2000,
        max_repositories=2,
    )

    assert result.selected_repositories == ["frontend", "backend"]
    assert result.estimated_tokens <= 2000
    assert "## repository: frontend" in result.text
    assert "## repository: backend" in result.text
    assert result.repository_budgets["frontend"] > result.repository_budgets["backend"]
    assert sum(result.repository_budgets.values()) <= int(2000 * 0.88)
    assert {name for name, _query, _budget in calls} == {"frontend", "backend"}


def test_workspace_pack_can_expand_dependency_when_slot_remains(tmp_path, monkeypatch):
    """A selected repository may pull a declared workspace dependency into a free slot."""
    frontend = tmp_path / "frontend"
    shared = tmp_path / "shared"
    misc = tmp_path / "misc"
    _repo(frontend, "@app/frontend", "@app/shared")
    _repo(shared, "@app/shared")
    _repo(misc, "@app/misc")
    workspace.init_workspace(
        tmp_path,
        [("frontend", frontend), ("shared", shared), ("misc", misc)],
    )

    class FakeService:
        def __init__(self, root):
            self.root = Path(root)

        def explain_ranking(self, query, **kwargs):
            del query, kwargs
            score = {"frontend": 100.0, "misc": 50.0, "shared": 1.0}[self.root.name]
            return {"results": [{"final_score": score}]}

        def build_context(self, query, **kwargs):
            del query
            return ContextPack(
                text=self.root.name + "\n",
                estimated_tokens=1,
                scanned_files=1,
                selected_files=[self.root.name + ".txt"],
                ranked=[],
            )

    monkeypatch.setattr(workspace, "RepositoryContextService", FakeService)
    result = workspace.build_workspace_context(
        tmp_path,
        "frontend task",
        max_tokens=3000,
        max_repositories=2,
    )
    assert result.selected_repositories == ["frontend", "shared"]
    assert result.dependency_edges == [
        {"from": "frontend", "to": "shared", "reason": "package-dependency"}
    ]


def test_workspace_add_remove_and_duplicate_guards(tmp_path):
    """Workspace lifecycle should never mutate repositories themselves."""
    one = tmp_path / "one"
    two = tmp_path / "two"
    _repo(one, "@app/one")
    _repo(two, "@app/two")
    workspace.init_workspace(tmp_path, [("one", one)])

    updated = workspace.add_repository(tmp_path, "two", two)
    assert [repo.name for repo in updated.repositories] == ["one", "two"]
    with pytest.raises(ValueError, match="already exists"):
        workspace.add_repository(tmp_path, "two", two)

    reduced = workspace.remove_repository(tmp_path, "two")
    assert [repo.name for repo in reduced.repositories] == ["one"]
    assert two.exists()
    with pytest.raises(ValueError, match="final repository"):
        workspace.remove_repository(tmp_path, "one")


def test_workspace_cli_status_json(tmp_path, capsys):
    """CLI should expose machine-readable workspace graph metadata."""
    one = tmp_path / "one"
    _repo(one, "@app/one")
    workspace.init_workspace(tmp_path, [("one", one)])

    assert workspace_main(["status", str(tmp_path), "--json"]) == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["repositories"][0]["name"] == "one"
    assert payload["repositories"][0]["package"] == "@app/one"


def test_workspace_rejects_too_small_global_budget(tmp_path):
    """The federation layer should fail rather than silently exceed its hard budget."""
    one = tmp_path / "one"
    _repo(one, "@app/one")
    workspace.init_workspace(tmp_path, [("one", one)])
    with pytest.raises(ValueError, match="at least 800"):
        workspace.build_workspace_context(
            tmp_path,
            "task",
            max_tokens=400,
        )
