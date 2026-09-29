"""Stable contracts for command/content optimization."""

from __future__ import annotations

from dataclasses import dataclass
from enum import IntEnum
from typing import Protocol


class SafetyClass(IntEnum):
    """Describe how much information a transform may discard."""

    S0_EXACT = 0
    S1_COSMETIC = 1
    S2_STRUCTURAL_LOSSLESS = 2
    S3_BOUNDED_SELECTIVE = 3
    S4_LOSSY_RECOVERABLE = 4

    @property
    def requires_recovery(self) -> bool:
        """Return whether accepting this class requires exact source recovery."""
        return self >= SafetyClass.S3_BOUNDED_SELECTIVE


@dataclass(frozen=True)
class OutputResult:
    """Describe the result of one output-optimization pass."""

    text: str
    processor: str
    compressed: bool
    failed: bool
    recovered_lines: tuple[str, ...] = ()
    content_kind: str = "text"
    safety_class: SafetyClass = SafetyClass.S4_LOSSY_RECOVERABLE
    validation: str = "not-run"

    @property
    def requires_recovery(self) -> bool:
        """Return whether this accepted transform must keep exact source bytes."""
        return self.compressed and self.safety_class.requires_recovery


@dataclass(frozen=True)
class OutputPolicy:
    """Configure size and preservation thresholds for one pipeline run."""

    max_lines: int = 80
    keep_tail: int = 20
    min_reduction: float = 0.02


class OutputProcessor(Protocol):
    """Transform output for one recognized command/content family."""

    name: str
    priority: int
    handles_failure: bool

    def matches(self, command: str) -> bool:
        """Return whether this processor recognizes command."""
        ...

    def compress(
        self,
        command: str,
        text: str,
        *,
        failed: bool,
        max_lines: int,
        keep_tail: int,
    ) -> str:
        """Return a conservative transformed representation of text."""
        ...
