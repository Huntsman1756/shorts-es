"""Typed errors with stable machine-readable codes.

Every failure mode that can affect provenance, reproducibility or temporal
semantics is a distinct, visible error - never a silent fallback.
"""

from __future__ import annotations


class ShortsEsError(Exception):
    """Base class. ``code`` is the stable public error code."""

    code = "ERROR"

    def __init__(self, message: str = "") -> None:
        super().__init__(message or self.code)
        self.message = message or self.code


class SourceUnavailableError(ShortsEsError):
    code = "SOURCE_UNAVAILABLE"


class UnsupportedWorkbookError(ShortsEsError):
    code = "UNSUPPORTED_WORKBOOK"


class SchemaDriftError(ShortsEsError):
    code = "SCHEMA_DRIFT"


class ParseError(ShortsEsError):
    code = "PARSE_ERROR"


class AmbiguousIdentifierError(ShortsEsError):
    code = "AMBIGUOUS_IDENTIFIER"

    def __init__(self, message: str, candidates: list[str] | None = None) -> None:
        super().__init__(message)
        self.candidates = candidates or []


class NotFoundError(ShortsEsError):
    code = "NOT_FOUND"


class MissingSnapshotError(ShortsEsError):
    code = "MISSING_SNAPSHOT"


class InsufficientKnowledgeHistoryError(ShortsEsError):
    code = "INSUFFICIENT_KNOWLEDGE_HISTORY"


class VerificationFailedError(ShortsEsError):
    code = "VERIFICATION_FAILED"


class NoDataError(ShortsEsError):
    code = "NO_DATA"
