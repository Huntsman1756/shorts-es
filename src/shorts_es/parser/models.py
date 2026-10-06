"""Canonical data model. All values are immutable and hash-stable."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import date
from decimal import Decimal


@dataclass(frozen=True)
class Disclosure:
    """One published net-short-position notification (canonical form).

    ``isin`` is normalized to upper case: the source contains case variants
    (``eS0118594417``) that denote the same security, and case is not
    semantically meaningful in an ISIN. All other text is preserved verbatim
    (after surrounding-whitespace stripping).
    """

    lei: str
    isin: str
    issuer_name: str
    holder_name: str
    position_date: date
    position_pct: Decimal

    @property
    def pct_str(self) -> str:
        """Canonical decimal rendering: no exponent, no trailing zeros."""
        d = self.position_pct.normalize()
        if d == d.to_integral():
            return str(d.quantize(Decimal(1)))
        return format(d, "f")

    def canonical_dict(self) -> dict:
        return {
            "lei": self.lei,
            "isin": self.isin,
            "issuer_name": self.issuer_name,
            "holder_name": self.holder_name,
            "position_date": self.position_date.isoformat(),
            "position_pct": self.pct_str,
        }

    def canonical_json(self) -> str:
        return json.dumps(
            self.canonical_dict(), ensure_ascii=False, sort_keys=True, separators=(",", ":")
        )

    @property
    def disclosure_id(self) -> str:
        """Content-addressed identity. Independent of observation time,
        row position and snapshot."""
        return hashlib.sha256(self.canonical_json().encode("utf-8")).hexdigest()

    @property
    def pair_key(self) -> tuple[str, str, str]:
        """The (issuer security, holder) pair this disclosure belongs to."""
        return (self.lei, self.isin, self.holder_name)


@dataclass(frozen=True)
class ParsedRow:
    """A canonical disclosure plus its physical location in the workbook."""

    sheet_name: str
    row_number: int  # 1-based, matching what a user sees in Excel
    disclosure: Disclosure


@dataclass(frozen=True)
class ParsedWorkbook:
    publication_date: date | None
    rows: tuple[ParsedRow, ...]

    def disclosures(self) -> list[Disclosure]:
        return [r.disclosure for r in self.rows]
