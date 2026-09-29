"""Session-efficiency services: continuity, deduplication, waste signals, and reports."""

from .guardian import capture_guardian, guardian_context, guardian_report
from .ledger import recent_ledger_events, resume_ledger_context, search_ledger
from .report import continuity_report, dashboard_report
from .service import (
    continuity_context,
    deduplicate_output,
    observe_prompt,
    observe_tool,
    start_session,
)

__all__ = [
    "capture_guardian",
    "guardian_context",
    "guardian_report",
    "recent_ledger_events",
    "resume_ledger_context",
    "search_ledger",
    "continuity_context",
    "continuity_report",
    "dashboard_report",
    "deduplicate_output",
    "observe_prompt",
    "observe_tool",
    "start_session",
]
