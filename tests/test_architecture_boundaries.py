"""Regression tests for the explicit architecture extension seams."""

import ast
import inspect

import acco.command_handlers.context as context_commands
import acco.commands as commands_facade
import acco.mcp_server.tools as mcp_tools
import acco.native_hooks as native_hooks
import acco.pack_cli as pack_cli
from acco.command_handlers.context import browse_main as vertical_browse_main
from acco.command_registry import (
    DEFAULT_COMMAND_REGISTRY,
    CommandRegistry,
    CommandSpec,
)
from acco.output import OutputPipeline, ProcessorRegistry
from acco.output_processors import OutputPipeline as CompatibilityPipeline


def test_command_registry_extends_dispatch_without_entry_changes():
    """A new command should require registration, not a new dispatcher branch."""
    seen: list[list[str]] = []

    def handler(args: list[str]) -> int:
        """Capture command arguments for the registry test."""
        seen.append(args)
        return 7

    def fallback(args: list[str]) -> int:
        """Provide an unused fallback for the registry test."""
        return 9

    registry = CommandRegistry([CommandSpec("custom", handler)])
    assert registry.dispatch(["custom", "a", "b"], fallback) == 7
    assert seen == [["a", "b"]]


def test_command_registry_rejects_duplicate_names():
    """Duplicate command names must fail during composition rather than at runtime."""
    handler = lambda args: 0
    try:
        CommandRegistry(
            [CommandSpec("same", handler), CommandSpec("same", handler)]
        )
    except ValueError as exc:
        assert "duplicate command registration" in str(exc)
    else:
        raise AssertionError("duplicate command registration was accepted")


def test_output_pipeline_accepts_injected_processors_without_core_changes():
    """Custom processors should plug into the pipeline through the contract only."""
    class CustomProcessor:
        """Small custom processor used to exercise dependency inversion."""

        name = "custom"
        priority = 1
        handles_failure = True

        def matches(self, command: str) -> bool:
            """Match the synthetic custom command."""
            return command == "custom"

        def compress(
            self,
            command: str,
            text: str,
            *,
            failed: bool,
            max_lines: int,
            keep_tail: int,
        ) -> str:
            """Return a compact deterministic representation."""
            return "summary\n"

    class GenericProcessor(CustomProcessor):
        """Fallback processor required by the registry contract."""

        name = "generic"
        priority = 999

        def matches(self, command: str) -> bool:
            """Match every command as the fallback."""
            return True

    pipeline = OutputPipeline(
        ProcessorRegistry([CustomProcessor(), GenericProcessor()])
    )
    result = pipeline.process("noise\n" * 100, "custom")
    assert result.processor == "custom"
    assert result.text == "summary\n"


def test_output_processors_module_remains_a_compatibility_facade():
    """Existing callers should receive the same pipeline type through the old module."""
    assert CompatibilityPipeline is OutputPipeline


def test_commands_module_is_a_thin_compatibility_facade():
    """Legacy command imports should delegate without reintroducing handler logic."""
    source = inspect.getsource(commands_facade)
    assert "\ndef " not in source
    assert commands_facade.browse_main is vertical_browse_main


def test_default_registry_bypasses_the_commands_compatibility_facade():
    """Registered handlers should come from vertical modules, not the legacy facade."""
    modules = {
        handler.__module__
        for name, handler in DEFAULT_COMMAND_REGISTRY._handlers.items()
        if name != "pack"
    }
    assert modules
    assert all(module.startswith("acco.command_handlers.") for module in modules)


def test_repository_integrations_use_application_service_boundary():
    """Host-facing repository integrations should not import low-level orchestration."""
    forbidden = {
        "build_context_pack",
        "browse_context",
        "analyze_impact",
        "build_index",
        "record_feedback",
    }
    for module in (context_commands, mcp_tools, pack_cli):
        tree = ast.parse(inspect.getsource(module))
        imported = {
            alias.name
            for node in ast.walk(tree)
            if isinstance(node, (ast.Import, ast.ImportFrom))
            for alias in node.names
        }
        assert forbidden.isdisjoint(imported)


def test_native_hook_adapters_translate_without_owning_domain_policy():
    """Non-Claude hook adapters must reuse the shared runtime instead of forking policy."""
    source = inspect.getsource(native_hooks)

    assert "build_hook_runtime" in source
    for forbidden in (
        "OutputPipeline",
        "RecoveryStore",
        "decide_read",
        "route_context",
        "automatic_output_policy",
        "automatic_model_route",
    ):
        assert forbidden not in source
