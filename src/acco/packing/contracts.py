"""Shared data contracts for the context-packing pipeline."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path


@dataclass(frozen=True)
class RankingScoreEvent:
    """Record one score transition produced by a ranking component or stage."""

    stage: str
    before: float
    after: float
    delta: float
    evidence: tuple[str, ...] = ()

    @classmethod
    def from_scores(
        cls,
        stage: str,
        before: float,
        after: float,
        evidence: tuple[str, ...] = (),
    ) -> RankingScoreEvent:
        """Create an event while deriving its exact score delta."""
        return cls(
            stage=stage,
            before=before,
            after=after,
            delta=after - before,
            evidence=evidence,
        )

    def to_dict(self) -> dict:
        """Return a JSON-serializable score-transition payload."""
        return {
            "stage": self.stage,
            "before": self.before,
            "after": self.after,
            "delta": self.delta,
            "evidence": list(self.evidence),
        }


@dataclass
class RankedFile:
    """Represent one ranked repository file and its retrieval evidence."""

    path: Path
    rel: str
    text: str
    outline: str
    score: float
    reasons: list[str] = field(default_factory=list)
    term_hits: int = 0
    changed: bool = False
    score_trace: list[RankingScoreEvent] = field(default_factory=list)
    semantic_ranges: list[tuple[int, int]] = field(default_factory=list)


@dataclass
class ContextPack:
    """Represent a completed bounded context pack and its evidence metadata."""

    text: str
    estimated_tokens: int
    scanned_files: int
    selected_files: list[str]
    ranked: list[RankedFile]
    selected_symbols: list[str] = field(default_factory=list)
    selected_symbol_identities: list[str] = field(default_factory=list)
    redactions: list[str] = field(default_factory=list)
    closure_files: list[str] = field(default_factory=list)
    retrieval_plan: dict[str, int] = field(default_factory=dict)
    cache_hit: bool = False
    cache_key: str | None = None
    context_budget_plan: dict | None = None
