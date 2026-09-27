"""CLI entry point for task-aware context packing."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from .repository_service import RepositoryContextService


def main(argv: list[str] | None = None) -> int:
    """Run the command-line entry point."""
    parser = argparse.ArgumentParser(
        prog="acco-pack",
        description="Build a task-aware source context pack under a hard token budget.",
    )
    parser.add_argument("path", nargs="?", default=".")
    parser.add_argument("-q", "--query", default="", help="task/bug/feature description")
    parser.add_argument("--max-tokens", type=int, default=6000)
    parser.add_argument("--max-files", type=int, default=12)
    parser.add_argument(
        "--context-budget",
        type=int,
        help=(
            "optional total model-context budget; ACCO derives the source slice "
            "while --max-tokens remains a hard source cap"
        ),
    )
    parser.add_argument("--context-lines", type=int, default=6)
    parser.add_argument("--no-gitignore", action="store_true")
    parser.add_argument("--no-changed-boost", action="store_true")
    parser.add_argument("--graph-hops", type=int, default=1,
                        help="dependency/call graph expansion depth (default: 1)")
    parser.add_argument("--closure-items", type=int, default=20,
                        help="maximum related files considered during dependency closure")
    parser.add_argument("--duplicate-threshold", type=float, default=0.92,
                        help="identifier similarity at which a file is skipped")
    parser.add_argument("--session", help="remember the selected working set for related tasks")
    parser.add_argument(
        "--embeddings",
        "--semantic",
        dest="embeddings",
        action="store_true",
        help=(
            "enable persistent chunk-level semantic retrieval and hybrid "
            "lexical/vector fusion with an already-downloaded local model"
        ),
    )
    parser.add_argument("--typescript-semantic", action="store_true",
                        help="overlay TS/JS edges resolved by the repository's local TypeScript compiler")
    parser.add_argument("--strict-semantic", action="store_true",
                        help="fail instead of falling back when compiler semantic resolution is unavailable")
    parser.add_argument("--no-index-cache", action="store_true")
    parser.add_argument(
        "--no-retrieval-cache",
        action="store_true",
        help="bypass persistent completed-pack reuse for this invocation",
    )
    parser.add_argument("--target-symbol", help="prioritize and emit an exact symbol body")
    parser.add_argument("--json", action="store_true", help="emit structured JSON metadata and text")
    parser.add_argument("--explain", action="store_true",
                        help="print the top relevance scores on stderr")
    parser.add_argument("-o", "--out", help="write pack to a file instead of stdout")
    args = parser.parse_args(argv)

    root = Path(args.path).resolve()
    if not root.exists():
        print(f"not found: {root}", file=sys.stderr)
        return 1
    if not root.is_dir():
        print(f"not a directory: {root}", file=sys.stderr)
        return 1
    try:
        repository = RepositoryContextService(
            root,
            use_gitignore=not args.no_gitignore,
            persist_index=not args.no_index_cache,
            retrieval_cache_enabled=not args.no_retrieval_cache,
        )
        semantic_enabled = True if (args.typescript_semantic or args.strict_semantic) else None
        semantic_edges = repository.enrich_typescript(
            enabled=semantic_enabled,
            strict=args.strict_semantic,
        )
        pack = repository.build_context(
            args.query,
            max_tokens=args.max_tokens,
            max_files=args.max_files,
            context_lines=args.context_lines,
            changed_boost=not args.no_changed_boost,
            graph_hops=args.graph_hops,
            duplicate_threshold=args.duplicate_threshold,
            session=args.session,
            embeddings=args.embeddings,
            target_symbol=args.target_symbol,
            closure_max_items=args.closure_items,
            context_budget_total=args.context_budget,
        )
    except (ValueError, RuntimeError) as exc:
        print(str(exc), file=sys.stderr)
        return 2

    if args.json:
        import json
        payload = {
            "text": pack.text,
            "estimated_tokens": pack.estimated_tokens,
            "scanned_files": pack.scanned_files,
            "selected_files": pack.selected_files,
            "selected_symbols": pack.selected_symbols,
            "redactions": pack.redactions,
            "closure_files": pack.closure_files,
            "retrieval_plan": pack.retrieval_plan,
            "cache_hit": pack.cache_hit,
            "cache_key": pack.cache_key,
            "context_budget_plan": pack.context_budget_plan,
            "semantic_index": (
                repository.semantic_index_status() if args.embeddings else None
            ),
            "typescript_semantic_edges": semantic_edges,
        }
        rendered = json.dumps(payload, indent=2)
        if args.out:
            Path(args.out).write_text(rendered + "\n", encoding="utf-8")
        else:
            sys.stdout.write(rendered + "\n")
    elif args.out:
        Path(args.out).write_text(pack.text, encoding="utf-8")
        print(
            f"wrote {args.out} ({pack.estimated_tokens} estimated tokens, "
            f"{len(pack.selected_files)}/{pack.scanned_files} files"
            + (", cache hit" if pack.cache_hit else "")
            + ")",
            file=sys.stderr,
        )
    else:
        sys.stdout.write(pack.text)

    if args.explain:
        print("\nACCO RELEVANCE", file=sys.stderr)
        if semantic_edges:
            print(f"compiler semantic edges: {semantic_edges}", file=sys.stderr)
        for item in pack.ranked[: min(20, len(pack.ranked))]:
            marker = "*" if item.rel in pack.selected_files else " "
            print(
                f"{marker} {item.score:7.2f}  {item.rel:50}  {', '.join(item.reasons)}",
                file=sys.stderr,
            )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
