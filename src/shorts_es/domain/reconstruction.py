"""Deterministic reconstruction of pair states from disclosures.

The only rule: within a (lei, isin, holder) pair, the disclosure with the
greatest ``position_date`` wins. No thresholds, no inference. A pair whose
latest published value is 0.00 is reported as such; a pair absent from the
Current sheet is "not currently published" — we never claim it is closed.
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal

from ..domain.states import DisclosureState
from ..domain.temporal import iso_utc
from ..storage import repository as repo


@dataclass(frozen=True)
class PairState:
    """Latest known disclosure for a (lei, isin, holder) pair."""

    lei: str
    isin: str
    issuer_name: str
    holder_name: str
    position_date: date
    position_pct: Decimal
    disclosure_id: str
    in_current_sheet: bool  # present in latest snapshot's Current sheet

    @property
    def state(self) -> DisclosureState:
        if self.position_pct > 0:
            return DisclosureState.PUBLIC_POSITION_OPEN
        return DisclosureState.PUBLIC_POSITION_ZERO

    @property
    def above_public_threshold(self) -> bool:
        return self.position_pct >= Decimal("0.5")


def latest_per_pair(
    rows: list[sqlite3.Row], effective_at: date | None = None
) -> dict[tuple[str, str, str], sqlite3.Row]:
    """Group disclosures by pair and keep the latest by position_date.

    Ties cannot occur in the real source (verified: no same-pair same-date
    distinct values); on a hypothetical tie the greater percentage wins for
    determinism.
    """
    best: dict[tuple[str, str, str], sqlite3.Row] = {}
    for row in rows:
        if effective_at and row["position_date"] > effective_at.isoformat():
            continue
        key = (row["lei"], row["isin"], row["holder_name"])
        cur = best.get(key)
        if cur is None or (row["position_date"], row["position_pct"]) > (
            cur["position_date"],
            cur["position_pct"],
        ):
            best[key] = row
    return best


def issuer_states(
    conn: sqlite3.Connection,
    isin: str,
    effective_at: date | None = None,
    known_at: datetime | None = None,
    current_pairs: set[tuple[str, str, str]] | None = None,
) -> list[PairState]:
    """Latest published state per holder pair for one ISIN."""
    rows = repo.disclosures_for_issuer(conn, isin, known_at=iso_utc(known_at) if known_at else None)
    result = []
    for (lei, i, holder), row in latest_per_pair(rows, effective_at).items():
        result.append(
            PairState(
                lei=lei,
                isin=i,
                issuer_name=row["issuer_name"],
                holder_name=holder,
                position_date=date.fromisoformat(row["position_date"]),
                position_pct=Decimal(row["position_pct"]),
                disclosure_id=row["disclosure_id"],
                in_current_sheet=(lei, i, holder) in (current_pairs or set()),
            )
        )
    result.sort(key=lambda p: (-p.position_pct, p.holder_name))
    return result


def holder_states(
    conn: sqlite3.Connection,
    holder: str,
    effective_at: date | None = None,
    known_at: datetime | None = None,
    current_pairs: set[tuple[str, str, str]] | None = None,
) -> list[PairState]:
    """Latest published state per issuer for one holder."""
    rows = repo.disclosures_for_holder(
        conn, holder, known_at=iso_utc(known_at) if known_at else None
    )
    result = []
    for (lei, i, h), row in latest_per_pair(rows, effective_at).items():
        result.append(
            PairState(
                lei=lei,
                isin=i,
                issuer_name=row["issuer_name"],
                holder_name=h,
                position_date=date.fromisoformat(row["position_date"]),
                position_pct=Decimal(row["position_pct"]),
                disclosure_id=row["disclosure_id"],
                in_current_sheet=(lei, i, h) in (current_pairs or set()),
            )
        )
    result.sort(key=lambda p: (p.issuer_name, -p.position_pct))
    return result


def current_pair_keys(conn: sqlite3.Connection, snapshot_sha256: str) -> set:
    return {
        (r["lei"], r["isin"], r["holder_name"])
        for r in repo.current_sheet_pairs(conn, snapshot_sha256)
    }
