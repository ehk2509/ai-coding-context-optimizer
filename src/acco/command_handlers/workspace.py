"""CLI surface for ACCO multi-repository workspace intelligence."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

from ..workspace import (
    add_repository,
    build_workspace_context,
    init_workspace,
    remove_repository,
    workspace_status,
)


def _parse_repo(value: str) -> tuple[str, Path]:
    """Parse NAME=PATH repository arguments."""
    if "=" not in value:
        raise argparse.ArgumentTypeError("repository must use NAME=PATH")
    name, path = value.split("=", 1)
    name = name.strip()
    path = path.strip()
    if not name or not path:
        raise argparse.ArgumentTypeError("repository must use non-empty NAME=PATH")
    return name, Path(path)


def workspace_main(argv: list[str]) -> int:
    """Manage and query an ACCO multi-repository workspace."""
    parser = argparse.ArgumentParser(prog="acco workspace")
    sub = parser.add_subparsers(dest="action", required=True)

    init = sub.add_parser("init", help="create a workspace manifest")
    init.add_argument("path", nargs="?", default=".")
    init.add_argument(
        "--repo",
        action="append",
        type=_parse_repo,
        help="repository as NAME=PATH; repeatable",
    )
    init.add_argument(
        "--discover",
        action="store_true",
        help="discover repository-like direct children",
    )
    init.add_argument("--json", action="store_true")

    add = sub.add_parser("add", help="register one repository")
    add.add_argument("name")
    add.add_argument("repo_path")
    add.add_argument("--path", default=".")
    add.add_argument("--json", action="store_true")

    remove = sub.add_parser("remove", help="unregister one repository")
    remove.add_argument("name")
    remove.add_argument("--path", default=".")
    remove.add_argument("--json", action="store_true")

    status = sub.add_parser("status", help="show repositories and dependency edges")
    status.add_argument("path", nargs="?", default=".")
    status.add_argument("--json", action="store_true")

    pack = sub.add_parser("pack", help="build one bounded context pack across repositories")
    pack.add_argument("path", nargs="?", default=".")
    pack.add_argument("--query", "-q", required=True)
    pack.add_argument("--max-tokens", type=int, default=10000)
    pack.add_argument("--max-repositories", type=int, default=4)
    pack.add_argument("--max-files-per-repository", type=int, default=8)
    pack.add_argument("--context-lines", type=int, default=6)
    pack.add_argument("--semantic", "--embeddings", dest="embeddings", action="store_true")
    pack.add_argument("--json", action="store_true")
    pack.add_argument("-o", "--out")

    args = parser.parse_args(argv)
    try:
        if args.action == "init":
            root = Path(args.path)
            repositories = list(args.repo or [])
            manifest = init_workspace(
                root,
                repositories,
                discover=args.discover,
            )
            payload = manifest.to_dict()
            if args.json:
                print(json.dumps(payload, indent=2))
            else:
                print("ACCO WORKSPACE — INITIALIZED")
                print(f"root: {manifest.root}")
                for repo in manifest.repositories:
                    print(f"- {repo.name}: {repo.path}")
            return 0

        if args.action == "add":
            manifest = add_repository(
                Path(args.path),
                args.name,
                Path(args.repo_path),
            )
            if args.json:
                print(json.dumps(manifest.to_dict(), indent=2))
            else:
                print(f"added {args.name}")
            return 0

        if args.action == "remove":
            manifest = remove_repository(Path(args.path), args.name)
            if args.json:
                print(json.dumps(manifest.to_dict(), indent=2))
            else:
                print(f"removed {args.name}")
            return 0

        if args.action == "status":
            payload = workspace_status(Path(args.path))
            if args.json:
                print(json.dumps(payload, indent=2))
            else:
                print("ACCO WORKSPACE")
                print(f"root: {payload['root']}")
                for repo in payload["repositories"]:
                    suffix = f" package={repo['package']}" if repo["package"] else ""
                    print(f"- {repo['name']}: {repo['path']}{suffix}")
                if payload["dependency_edges"]:
                    print("dependencies:")
                    for edge in payload["dependency_edges"]:
                        print(f"  {edge['from']} -> {edge['to']}")
            return 0

        result = build_workspace_context(
            Path(args.path),
            args.query,
            max_tokens=args.max_tokens,
            max_repositories=args.max_repositories,
            max_files_per_repository=args.max_files_per_repository,
            context_lines=args.context_lines,
            embeddings=args.embeddings,
        )
        if args.json:
            rendered = json.dumps(result.to_dict(), indent=2)
        else:
            rendered = result.text
        if args.out:
            Path(args.out).write_text(rendered + ("" if rendered.endswith("\n") else "\n"), encoding="utf-8")
        else:
            sys.stdout.write(rendered + ("" if rendered.endswith("\n") else "\n"))
        return 0
    except (OSError, RuntimeError, ValueError) as exc:
        print(str(exc), file=sys.stderr)
        return 2
