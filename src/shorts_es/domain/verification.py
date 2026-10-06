"""Independent verification: derive Current from Series, compare.

The workbook's Current sheet claims to be the latest disclosure per pair.
We recompute "latest per pair" from the Series sheet and diff. This is the
core executable-verification test of shorts-es.
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass, field
from decimal import Decimal

from .. import constants
from ..storage import repository as repo


@dataclass(frozen=True)
class PairReport:
    lei: str
    isin: str
    holder_name: str
    expected: tuple[str, str] | None  # (date, pct) reconstructed from Series
    actual: tuple[str, str] | None  # (date, pct) published in Current


@dataclass(frozen=True)
class VerificationResult:
    snapshot_sha256: str
    pairs_checked: int
    matched: int
    missing: list[PairReport] = field(default_factory=list)  # in Current, not in Series
    unexpected: list[PairReport] = field(default_factory=list)  # in Series, not in Current
    conflicts: list[PairReport] = field(default_factory=list)  # both, different latest

    @property
    def passed(self) -> bool:
        return not (self.missing or self.unexpected or self.conflicts)

    def counts(self) -> dict:
        return {
            "pairs_checked": self.pairs_checked,
            "matched": self.matched,
            "missing": len(self.missing),
            "unexpected": len(self.unexpected),
            "conflicts": len(self.conflicts),
        }

    def details(self) -> dict:
        def rep(p: PairReport) -> dict:
            return {
                "lei": p.lei,
                "isin": p.isin,
                "holder_name": p.holder_name,
                "expected": p.expected,
                "actual": p.actual,
            }

        return {
            "missing": [rep(p) for p in self.missing],
            "unexpected": [rep(p) for p in self.unexpected],
            "conflicts": [rep(p) for p in self.conflicts],
        }


def verify_snapshot(conn: sqlite3.Connection, snapshot_sha256: str) -> VerificationResult:
    series = repo.disclosures_for_snapshot(conn, snapshot_sha256, constants.SHEET_SERIES)
    current = repo.disclosures_for_snapshot(conn, snapshot_sha256, constants.SHEET_CURRENT)

    # Reconstruct: latest per pair from Series.
    latest: dict[tuple[str, str, str], tuple[str, str]] = {}
    for r in series:
        key = (r["lei"], r["isin"], r["holder_name"])
        cand = (r["position_date"], r["position_pct"])
        if key not in latest or cand > latest[key]:
            latest[key] = cand

    published: dict[tuple[str, str, str], tuple[str, str]] = {}
    for r in current:
        key = (r["lei"], r["isin"], r["holder_name"])
        published[key] = (r["position_date"], r["position_pct"])

    missing, unexpected, conflicts = [], [], []
    matched = 0
    for key in sorted(set(latest) | set(published)):
        lei, isin, holder = key
        exp, act = latest.get(key), published.get(key)
        report = PairReport(lei=lei, isin=isin, holder_name=holder, expected=exp, actual=act)
        if exp is None:
            missing.append(report)
        elif act is None:
            unexpected.append(report)
        elif exp != act:
            # Compare decimal-normalized pct to avoid '0.6' vs '0.60' noise.
            if exp[0] == act[0] and Decimal(exp[1]) == Decimal(act[1]):
                matched += 1
            else:
                conflicts.append(report)
        else:
            matched += 1

    return VerificationResult(
        snapshot_sha256=snapshot_sha256,
        pairs_checked=len(set(latest) | set(published)),
        matched=matched,
        missing=missing,
        unexpected=unexpected,
        conflicts=conflicts,
    )
