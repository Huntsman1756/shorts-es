"""Field normalization: source cell -> canonical value.

Rules (all verified against the published workbook):
- LEI: 20-char alphanumeric, upper case.
- ISIN: 12-char, normalized to upper case (source has case-typo variants).
- Names: stripped of surrounding whitespace; inner text preserved verbatim.
- Dates: published as *text* cells ``' YYYY-MM-DD '``; parsed strictly.
- Percentages: published as numeric cells; ``Decimal(str(float))`` is the
  exact shortest-representation value (formats are 'General', no rounding).
"""

from __future__ import annotations

import re
from datetime import date
from decimal import Decimal, InvalidOperation

from ..exceptions import ParseError

_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
_LEI_RE = re.compile(r"^[A-Z0-9]{20}$")
_ISIN_RE = re.compile(r"^[A-Z]{2}[A-Z0-9]{9}[0-9]$")


def norm_text(value: object, field: str) -> str:
    if not isinstance(value, str):
        raise ParseError(f"{field}: expected text cell, got {type(value).__name__}")
    return value.strip()


def norm_lei(value: object) -> str:
    lei = norm_text(value, "LEI").upper()
    if not _LEI_RE.match(lei):
        raise ParseError(f"invalid LEI: {value!r}")
    return lei


def norm_isin(value: object) -> str:
    isin = norm_text(value, "ISIN").upper()
    if not _ISIN_RE.match(isin):
        raise ParseError(f"invalid ISIN: {value!r}")
    return isin


def norm_date(value: object) -> date:
    s = norm_text(value, "position_date")
    if not _DATE_RE.match(s):
        raise ParseError(f"invalid position date: {value!r}")
    try:
        return date.fromisoformat(s)
    except ValueError as exc:
        raise ParseError(f"invalid position date: {value!r}") from exc


def norm_pct(value: object) -> Decimal:
    if not isinstance(value, int | float) or isinstance(value, bool):
        raise ParseError(f"position_pct: expected numeric cell, got {value!r}")
    try:
        pct = Decimal(str(value))
    except InvalidOperation as exc:
        raise ParseError(f"invalid percentage value: {value!r}") from exc
    if pct < 0:
        raise ParseError(f"negative net short position: {value!r}")
    return pct
