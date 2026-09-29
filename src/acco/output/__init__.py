"""Composable command-output optimization subsystem."""

from .content_engine import ContentProfile, detect_content, validate_candidate
from .contracts import OutputPolicy, OutputProcessor, OutputResult, SafetyClass
from .pipeline import OutputPipeline, detect_failure, explain_processor, process_output
from .processors import (
    GenericProcessor,
    GitLogProcessor,
    JsTestProcessor,
    PackageInstallProcessor,
    PytestProcessor,
    default_processors,
)
from .registry import DEFAULT_REGISTRY, ProcessorRegistry
from .text import (
    ERROR_HINTS,
    filter_text,
    preprocess,
    recover_critical_lines,
)

__all__ = [
    "DEFAULT_REGISTRY",
    "ERROR_HINTS",
    "GenericProcessor",
    "GitLogProcessor",
    "JsTestProcessor",
    "OutputPipeline",
    "OutputPolicy",
    "OutputProcessor",
    "OutputResult",
    "SafetyClass",
    "ContentProfile",
    "PackageInstallProcessor",
    "ProcessorRegistry",
    "PytestProcessor",
    "default_processors",
    "detect_failure",
    "detect_content",
    "explain_processor",
    "filter_text",
    "preprocess",
    "process_output",
    "recover_critical_lines",
    "validate_candidate",
]
