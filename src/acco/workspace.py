"""Federated multi-repository workspace retrieval for ACCO."""

from __future__ import annotations

from dataclasses import asdict, dataclass
import json
from pathlib import Path
import re
from typing import Any

try:
    import tomllib
except ModuleNotFoundError:  # pragma: no cover - Python 3.10
    import tomli as tomllib

from .estimate import estimate_tokens
from .repository_service import RepositoryContextService

WORKSPACE_SCHEMA = 1
WORKSPACE_FILE = ".acco-workspace.json"
_PACKAGE_TERM = re.compile(r"[A-Za-z0-9_.@/+-]{2,}")


@dataclass(frozen=True)
class WorkspaceRepository:
    """One repository registered in a workspace manifest."""

    name: str
    path: str

    def to_dict(self) -> dict[str, str]:
        """Return a JSON-safe repository record."""
        return asdict(self)


@dataclass(frozen=True)
class PackageMetadata:
    """Package identity and declared cross-package dependency names."""

    identity: str | None
    dependencies: tuple[str, ...]


@dataclass(frozen=True)
class WorkspaceManifest:
    """Validated workspace configuration."""

    root: str
    repositories: tuple[WorkspaceRepository, ...]

    def to_dict(self) -> dict[str, Any]:
        """Return the persisted manifest representation."""
        return {
            "schema": WORKSPACE_SCHEMA,
            "root": self.root,
            "repositories": [repo.to_dict() for repo in self.repositories],
        }


@dataclass
class WorkspacePack:
    """Combined bounded context pack with repository provenance."""

    text: str
    estimated_tokens: int
    selected_repositories: list[str]
    repository_budgets: dict[str, int]
    repository_scores: dict[str, float]
    selected_files: dict[str, list[str]]
    scanned_files: dict[str, int]
    dependency_edges: list[dict[str, str]]

    def to_dict(self) -> dict[str, Any]:
        """Return a JSON-safe workspace-pack payload."""
        return {
            "text": self.text,
            "estimated_tokens": self.estimated_tokens,
            "selected_repositories": self.selected_repositories,
            "repository_budgets": self.repository_budgets,
            "repository_scores": self.repository_scores,
            "selected_files": self.selected_files,
            "scanned_files": self.scanned_files,
            "dependency_edges": self.dependency_edges,
        }


def workspace_path(root: Path) -> Path:
    """Return the workspace manifest path."""
    return root.resolve() / WORKSPACE_FILE


def _safe_repo_name(value: str) -> str:
    """Normalize and validate one human-facing repository name."""
    name = value.strip()
    if not name or any(char in name for char in "\n\r\t"):
        raise ValueError("workspace repository name must be non-empty")
    return name


def _repo_record(root: Path, name: str, path: Path) -> WorkspaceRepository:
    """Create one repository record using a portable relative path when possible."""
    resolved = path.expanduser().resolve()
    if not resolved.is_dir():
        raise ValueError(f"workspace repository is not a directory: {resolved}")
    try:
        stored = str(resolved.relative_to(root.resolve()))
        if stored == ".":
            stored = "."
    except ValueError:
        stored = str(resolved)
    return WorkspaceRepository(name=_safe_repo_name(name), path=stored)


def _resolve_repo_path(root: Path, stored: str) -> Path:
    """Resolve one manifest repository path against the workspace root."""
    candidate = Path(stored).expanduser()
    if not candidate.is_absolute():
        candidate = root / candidate
    return candidate.resolve()


def _atomic_write(path: Path, payload: dict[str, Any]) -> None:
    """Write a deterministic manifest without partially replacing it."""
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(payload, indent=2, sort_keys=False) + "\n",
        encoding="utf-8",
    )
    temporary.replace(path)


def _validate_manifest(root: Path, payload: Any) -> WorkspaceManifest:
    """Validate one workspace manifest before any repository access."""
    if not isinstance(payload, dict) or payload.get("schema") != WORKSPACE_SCHEMA:
        raise ValueError("unsupported ACCO workspace manifest")
    raw_repos = payload.get("repositories")
    if not isinstance(raw_repos, list) or not raw_repos:
        raise ValueError("workspace must contain at least one repository")

    seen_names: set[str] = set()
    seen_paths: set[str] = set()
    repos: list[WorkspaceRepository] = []
    for item in raw_repos:
        if not isinstance(item, dict):
            raise ValueError("workspace repository entries must be objects")
        name = _safe_repo_name(str(item.get("name", "")))
        stored = str(item.get("path", "")).strip()
        if not stored:
            raise ValueError(f"workspace repository {name!r} has no path")
        resolved = _resolve_repo_path(root, stored)
        if not resolved.is_dir():
            raise ValueError(f"workspace repository not found: {resolved}")
        path_key = str(resolved)
        if name in seen_names:
            raise ValueError(f"duplicate workspace repository name: {name}")
        if path_key in seen_paths:
            raise ValueError(f"duplicate workspace repository path: {resolved}")
        seen_names.add(name)
        seen_paths.add(path_key)
        repos.append(WorkspaceRepository(name=name, path=stored))
    return WorkspaceManifest(root=str(root.resolve()), repositories=tuple(repos))


def load_workspace(root: Path) -> WorkspaceManifest:
    """Load and validate an ACCO workspace manifest."""
    root = root.expanduser().resolve()
    path = workspace_path(root)
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise ValueError(f"workspace manifest not found: {path}") from exc
    except (OSError, ValueError) as exc:
        raise ValueError(f"invalid workspace manifest: {path}") from exc
    return _validate_manifest(root, payload)


def _discover_direct_repositories(root: Path) -> list[tuple[str, Path]]:
    """Discover repository-like direct children without recursively crawling disks."""
    found: list[tuple[str, Path]] = []
    if (root / ".git").exists():
        found.append((root.name, root))
    try:
        children = sorted(
            (item for item in root.iterdir() if item.is_dir() and not item.name.startswith(".")),
            key=lambda item: item.name.lower(),
        )
    except OSError as exc:
        raise ValueError(f"cannot inspect workspace root: {root}") from exc
    for child in children:
        if (
            (child / ".git").exists()
            or (child / ".acco.toml").exists()
            or (child / "package.json").exists()
            or (child / "pyproject.toml").exists()
            or (child / "Cargo.toml").exists()
            or (child / "go.mod").exists()
        ):
            found.append((child.name, child))
    return found


def init_workspace(
    root: Path,
    repositories: list[tuple[str, Path]] | None = None,
    *,
    discover: bool = False,
) -> WorkspaceManifest:
    """Create a workspace manifest from explicit and/or discovered repositories."""
    root = root.expanduser().resolve()
    root.mkdir(parents=True, exist_ok=True)
    candidates = list(repositories or [])
    if discover or not candidates:
        candidates.extend(_discover_direct_repositories(root))
    if not candidates:
        raise ValueError("no repositories supplied or discovered for workspace")

    records: list[WorkspaceRepository] = []
    seen_names: set[str] = set()
    seen_paths: set[str] = set()
    for name, path in candidates:
        record = _repo_record(root, name, path)
        resolved = str(_resolve_repo_path(root, record.path))
        if record.name in seen_names or resolved in seen_paths:
            continue
        seen_names.add(record.name)
        seen_paths.add(resolved)
        records.append(record)
    if not records:
        raise ValueError("workspace contains no unique repositories")

    manifest = WorkspaceManifest(root=str(root), repositories=tuple(records))
    _atomic_write(workspace_path(root), manifest.to_dict())
    return manifest


def add_repository(root: Path, name: str, path: Path) -> WorkspaceManifest:
    """Add one repository while preserving manifest order."""
    root = root.expanduser().resolve()
    current = load_workspace(root)
    record = _repo_record(root, name, path)
    resolved_new = _resolve_repo_path(root, record.path)
    for existing in current.repositories:
        if existing.name == record.name:
            raise ValueError(f"workspace repository already exists: {record.name}")
        if _resolve_repo_path(root, existing.path) == resolved_new:
            raise ValueError(f"workspace repository path already registered: {resolved_new}")
    updated = WorkspaceManifest(
        root=str(root),
        repositories=(*current.repositories, record),
    )
    _atomic_write(workspace_path(root), updated.to_dict())
    return updated


def remove_repository(root: Path, name: str) -> WorkspaceManifest:
    """Remove one named repository without touching the repository itself."""
    root = root.expanduser().resolve()
    current = load_workspace(root)
    remaining = tuple(repo for repo in current.repositories if repo.name != name)
    if len(remaining) == len(current.repositories):
        raise ValueError(f"workspace repository not found: {name}")
    if not remaining:
        raise ValueError("workspace cannot remove its final repository")
    updated = WorkspaceManifest(root=str(root), repositories=remaining)
    _atomic_write(workspace_path(root), updated.to_dict())
    return updated


def _package_metadata(repo: Path) -> PackageMetadata:
    """Read a bounded set of package manifests for cross-repository graph hints."""
    package_json = repo / "package.json"
    if package_json.is_file():
        try:
            payload = json.loads(package_json.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            payload = {}
        if isinstance(payload, dict):
            identity = payload.get("name")
            identity = identity.strip() if isinstance(identity, str) and identity.strip() else None
            dependencies: set[str] = set()
            for key in (
                "dependencies",
                "devDependencies",
                "peerDependencies",
                "optionalDependencies",
            ):
                section = payload.get(key)
                if isinstance(section, dict):
                    dependencies.update(
                        str(name) for name in section if isinstance(name, str)
                    )
            return PackageMetadata(identity=identity, dependencies=tuple(sorted(dependencies)))

    pyproject = repo / "pyproject.toml"
    if pyproject.is_file():
        try:
            payload = tomllib.loads(pyproject.read_text(encoding="utf-8"))
        except (OSError, tomllib.TOMLDecodeError):
            payload = {}
        project = payload.get("project", {}) if isinstance(payload, dict) else {}
        if isinstance(project, dict):
            identity = project.get("name")
            identity = identity.strip() if isinstance(identity, str) and identity.strip() else None
            dependencies: set[str] = set()
            raw_dependencies = project.get("dependencies", [])
            if isinstance(raw_dependencies, list):
                for item in raw_dependencies:
                    if isinstance(item, str):
                        match = re.match(r"\s*([A-Za-z0-9_.-]+)", item)
                        if match:
                            dependencies.add(match.group(1))
            return PackageMetadata(identity=identity, dependencies=tuple(sorted(dependencies)))

    cargo = repo / "Cargo.toml"
    if cargo.is_file():
        try:
            payload = tomllib.loads(cargo.read_text(encoding="utf-8"))
        except (OSError, tomllib.TOMLDecodeError):
            payload = {}
        package = payload.get("package", {}) if isinstance(payload, dict) else {}
        deps = payload.get("dependencies", {}) if isinstance(payload, dict) else {}
        identity = package.get("name") if isinstance(package, dict) else None
        identity = identity.strip() if isinstance(identity, str) and identity.strip() else None
        dependencies = tuple(sorted(str(name) for name in deps)) if isinstance(deps, dict) else ()
        return PackageMetadata(identity=identity, dependencies=dependencies)

    gomod = repo / "go.mod"
    if gomod.is_file():
        try:
            lines = gomod.read_text(encoding="utf-8").splitlines()
        except OSError:
            lines = []
        identity = None
        dependencies: set[str] = set()
        in_require = False
        for raw in lines:
            line = raw.strip()
            if line.startswith("module "):
                identity = line.split(None, 1)[1].strip()
            elif line == "require (":
                in_require = True
            elif in_require and line == ")":
                in_require = False
            elif line.startswith("require "):
                parts = line.split()
                if len(parts) >= 2:
                    dependencies.add(parts[1])
            elif in_require and line and not line.startswith("//"):
                dependencies.add(line.split()[0])
        return PackageMetadata(identity=identity, dependencies=tuple(sorted(dependencies)))

    return PackageMetadata(identity=None, dependencies=())


def dependency_edges(root: Path, manifest: WorkspaceManifest | None = None) -> list[dict[str, str]]:
    """Return package-manifest edges between registered workspace repositories."""
    root = root.expanduser().resolve()
    manifest = manifest or load_workspace(root)
    metadata: dict[str, PackageMetadata] = {}
    identities: dict[str, str] = {}
    for repo in manifest.repositories:
        path = _resolve_repo_path(root, repo.path)
        meta = _package_metadata(path)
        metadata[repo.name] = meta
        if meta.identity:
            identities[meta.identity.lower()] = repo.name

    edges: list[dict[str, str]] = []
    seen: set[tuple[str, str]] = set()
    for repo in manifest.repositories:
        for dependency in metadata[repo.name].dependencies:
            target = identities.get(dependency.lower())
            if target and target != repo.name and (repo.name, target) not in seen:
                seen.add((repo.name, target))
                edges.append(
                    {
                        "from": repo.name,
                        "to": target,
                        "reason": "package-dependency",
                    }
                )
    return edges


def workspace_status(root: Path) -> dict[str, Any]:
    """Return repository and cross-repository package graph metadata."""
    root = root.expanduser().resolve()
    manifest = load_workspace(root)
    repos: list[dict[str, Any]] = []
    for repo in manifest.repositories:
        resolved = _resolve_repo_path(root, repo.path)
        meta = _package_metadata(resolved)
        repos.append(
            {
                "name": repo.name,
                "path": str(resolved),
                "package": meta.identity,
                "declared_dependencies": list(meta.dependencies),
            }
        )
    return {
        "root": str(root),
        "manifest": str(workspace_path(root)),
        "repositories": repos,
        "dependency_edges": dependency_edges(root, manifest),
    }


def _query_terms(query: str) -> set[str]:
    """Return normalized query terms for lightweight repository identity hints."""
    return {match.group(0).lower() for match in _PACKAGE_TERM.finditer(query)}


def _repository_score(
    service: RepositoryContextService,
    *,
    query: str,
    repo_name: str,
    package: PackageMetadata,
) -> float:
    """Score one repository using its existing ranking pipeline plus identity hints."""
    if not query.strip():
        return 1.0
    report = service.explain_ranking(
        query,
        max_files=3,
        changed_boost=True,
        embeddings=False,
    )
    results = report.get("results", [])
    top = sum(max(0.0, float(item.get("final_score", 0.0))) for item in results[:3])
    terms = _query_terms(query)
    identity_bonus = 0.0
    for candidate in (repo_name, package.identity or ""):
        lowered = candidate.lower()
        if lowered and any(term in lowered or lowered in term for term in terms):
            identity_bonus += 100.0
    return max(0.001, top + identity_bonus)


def _allocate_budgets(
    scores: dict[str, float],
    total: int,
    *,
    minimum: int = 450,
) -> dict[str, int]:
    """Allocate an integer token budget without exceeding the workspace total."""
    if total <= 0 or not scores:
        raise ValueError("workspace token budget must be positive")
    names = list(scores)
    if total < minimum * len(names):
        base = total // len(names)
        result = dict.fromkeys(names, base)
        for name in names[: total - base * len(names)]:
            result[name] += 1
        return result

    result = dict.fromkeys(names, minimum)
    remaining = total - minimum * len(names)
    weight_total = sum(max(0.001, scores[name]) for name in names)
    fractions: list[tuple[float, str]] = []
    used = 0
    for name in names:
        exact = remaining * max(0.001, scores[name]) / weight_total
        extra = int(exact)
        result[name] += extra
        used += extra
        fractions.append((exact - extra, name))
    for _fraction, name in sorted(fractions, reverse=True)[: remaining - used]:
        result[name] += 1
    return result


def build_workspace_context(
    root: Path,
    query: str,
    *,
    max_tokens: int = 10000,
    max_repositories: int = 4,
    max_files_per_repository: int = 8,
    context_lines: int = 6,
    embeddings: bool = False,
) -> WorkspacePack:
    """Build one provenance-preserving context pack across registered repositories."""
    if max_tokens < 800:
        raise ValueError("workspace max_tokens must be at least 800")
    if max_repositories <= 0:
        raise ValueError("max_repositories must be positive")
    root = root.expanduser().resolve()
    manifest = load_workspace(root)
    edges = dependency_edges(root, manifest)

    services: dict[str, RepositoryContextService] = {}
    packages: dict[str, PackageMetadata] = {}
    scores: dict[str, float] = {}
    for repo in manifest.repositories:
        resolved = _resolve_repo_path(root, repo.path)
        service = RepositoryContextService(resolved)
        services[repo.name] = service
        packages[repo.name] = _package_metadata(resolved)
        scores[repo.name] = _repository_score(
            service,
            query=query,
            repo_name=repo.name,
            package=packages[repo.name],
        )

    ordered = sorted(
        manifest.repositories,
        key=lambda repo: (-scores[repo.name], repo.name.lower()),
    )
    seed_count = (
        1
        if max_repositories == 1
        else min(len(ordered), max_repositories - 1)
    )
    selected = [repo.name for repo in ordered[:seed_count]]
    selected_set = set(selected)

    # Reserve at most one bounded slot for a direct package dependency of the
    # strongest selected repositories, then fill any remaining slots by score.
    for edge in edges:
        if edge["from"] in selected_set and edge["to"] not in selected_set:
            selected.append(edge["to"])
            selected_set.add(edge["to"])
            if len(selected) >= max_repositories:
                break

    if len(selected) < max_repositories:
        for repo in ordered:
            if repo.name in selected_set:
                continue
            selected.append(repo.name)
            selected_set.add(repo.name)
            if len(selected) >= max_repositories:
                break

    # Reserve 12% for repository headers/provenance and keep individual packs
    # independently bounded by the existing repository packer.
    content_budget = max(1, int(max_tokens * 0.88))
    selected_scores = {name: scores[name] for name in selected}
    budgets = _allocate_budgets(selected_scores, content_budget)

    packs: dict[str, Any] = {}
    for name in selected:
        packs[name] = services[name].build_context(
            query,
            max_tokens=budgets[name],
            max_files=max_files_per_repository,
            context_lines=context_lines,
            embeddings=embeddings,
            session=None,
        )

    def render(names: list[str]) -> str:
        parts = [
            "# ACCO WORKSPACE CONTEXT",
            f"query: {query}",
            f"workspace: {root}",
            "",
        ]
        for name in names:
            repo_record = next(repo for repo in manifest.repositories if repo.name == name)
            resolved = _resolve_repo_path(root, repo_record.path)
            parts.extend(
                [
                    f"## repository: {name}",
                    f"path: {resolved}",
                    f"allocated_tokens: {budgets[name]}",
                    "",
                    packs[name].text.rstrip(),
                    "",
                ]
            )
        related = [
            edge
            for edge in edges
            if edge["from"] in names and edge["to"] in names
        ]
        if related:
            parts.append("## cross-repository dependencies")
            for edge in related:
                parts.append(f"- {edge['from']} -> {edge['to']} [{edge['reason']}]")
            parts.append("")
        return "\n".join(parts).rstrip() + "\n"

    final_names = list(selected)
    text = render(final_names)
    while len(final_names) > 1 and estimate_tokens(text) > max_tokens:
        final_names.pop()
        text = render(final_names)

    if estimate_tokens(text) > max_tokens:
        only = final_names[0]
        reduced = max(400, int(budgets[only] * 0.75))
        packs[only] = services[only].build_context(
            query,
            max_tokens=reduced,
            max_files=max_files_per_repository,
            context_lines=context_lines,
            embeddings=embeddings,
            session=None,
        )
        budgets[only] = reduced
        text = render(final_names)

    tokens = estimate_tokens(text)
    if tokens > max_tokens:
        raise RuntimeError(
            f"workspace pack exceeded hard budget: {tokens} > {max_tokens}"
        )

    return WorkspacePack(
        text=text,
        estimated_tokens=tokens,
        selected_repositories=final_names,
        repository_budgets={name: budgets[name] for name in final_names},
        repository_scores={name: scores[name] for name in final_names},
        selected_files={
            name: list(packs[name].selected_files) for name in final_names
        },
        scanned_files={
            name: int(packs[name].scanned_files) for name in final_names
        },
        dependency_edges=[
            edge
            for edge in edges
            if edge["from"] in final_names and edge["to"] in final_names
        ],
    )
