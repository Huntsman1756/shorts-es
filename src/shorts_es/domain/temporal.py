"""Temporal semantics: effective (regulatory) time vs knowledge time.

- ``position_date`` is the effective/regulatory date published by CNMV.
- ``first_observed_at`` is when shorts-es first saw the disclosure
  (knowledge time). All rows in the very first snapshot share that instant:
  they are RECONSTRUCTED_HISTORICAL, not knowledge we had back then.
"""

from __future__ import annotations

import re
from datetime import UTC, date, datetime

from ..exceptions import ParseError

_DATE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


def parse_effective_date(value: str) -> date:
    """Parse --effective-at / --since dates strictly as YYYY-MM-DD."""
    if not _DATE.match(value.strip()):
        raise ParseError(f"expected YYYY-MM-DD, got {value!r}")
    return date.fromisoformat(value.strip())


def parse_known_at(value: str) -> datetime:
    """Parse --known-at as ISO-8601 datetime (timezone required if offset
    semantics matter; naive values are treated as UTC)."""
    s = value.strip()
    try:
        dt = datetime.fromisoformat(s)
    except ValueError as exc:
        raise ParseError(f"expected ISO-8601 datetime, got {value!r}") from exc
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=UTC)
    return dt.astimezone(UTC)


def iso_utc(dt: datetime) -> str:
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=UTC)
    return dt.astimezone(UTC).isoformat()
