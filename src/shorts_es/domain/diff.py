"""Snapshot diff: compare two observed snapshots, never "nearest dates".

Two levels, kept distinct on purpose:
- *source diff*: which disclosures appeared/disappeared per sheet (physical).
- *state diff*: how the latest-per-pair state moved between snapshots
  (derived). Classification is factual: ADDED / REMOVED / CHANGED with the
  percentage delta; we do not invent regulatory event names.
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass, field
from decimal import Decimal

from ..exceptions import MissingSnapshotError
from ..storage import repository as repo


@dataclass(frozen=True)
class PairChange:
    lei: str
    isin: str
    issuer_name: str
    holder_name: str
    kind: str  # ADDED | REMOVED | CHANGED
    old: tuple[str, str] | None  # (date, pct)
    new: tuple[str, str] | None

    @property
    def direction(self) -> str | None:
        if self.kind != "CHANGED" or not (self.old and self.new):
            return None
        old, new = Decimal(self.old[1]), Decimal(self.new[1])
        if new > old:
            return "INCREASED"
        if new < old:
            return "DECREASED"
        return "SAME_VALUE"


@dataclass(frozen=True)
class SnapshotDiff:
    sha_a: str
    sha_b: str
    added_ids: set[str]
    removed_ids: set[str]
    changes: list[PairChange] = field(default_factory=list)


def _state_map(rows) -> dict:
    latest: dict[tuple, tuple] = {}
    names: dict[tuple, str] = {}
    for r in rows:
        key = (r["lei"], r["isin"], r["holder_name"])
        names[key] = r["issuer_name"]
        cand = (r["position_date"], r["position_pct"])
        if key not in latest or cand > latest[key]:
            latest[key] = cand
    return latest, names


def diff_snapshots(conn: sqlite3.Connection, sha_a: str, sha_b: str) -> SnapshotDiff:
    snap_a = repo.get_snapshot(conn, sha_a)
    snap_b = repo.get_snapshot(conn, sha_b)
    if snap_a is None:
        raise MissingSnapshotError(f"snapshot not found: {sha_a}")
    if snap_b is None:
        raise MissingSnapshotError(f"snapshot not found: {sha_b}")
    sha_a, sha_b = snap_a["snapshot_sha256"], snap_b["snapshot_sha256"]

    ids_a = repo.snapshot_disclosure_ids(conn, sha_a)
    ids_b = repo.snapshot_disclosure_ids(conn, sha_b)

    # State diff is computed on the union of published disclosures present in
    # each snapshot (all sheets) - the derived "latest known" projection.
    map_a, names_a = _state_map(repo.disclosures_for_snapshot(conn, sha_a))
    map_b, names_b = _state_map(repo.disclosures_for_snapshot(conn, sha_b))

    changes: list[PairChange] = []
    for key in sorted(set(map_a) | set(map_b)):
        a, b = map_a.get(key), map_b.get(key)
        lei, isin, holder = key
        issuer = names_b.get(key) or names_a.get(key) or ""
        if a is None:
            changes.append(PairChange(lei, isin, issuer, holder, "ADDED", None, b))
        elif b is None:
            changes.append(PairChange(lei, isin, issuer, holder, "REMOVED", a, None))
        elif a != b and not (a[0] == b[0] and Decimal(a[1]) == Decimal(b[1])):
            changes.append(PairChange(lei, isin, issuer, holder, "CHANGED", a, b))

    return SnapshotDiff(
        sha_a=sha_a,
        sha_b=sha_b,
        added_ids=ids_b - ids_a,
        removed_ids=ids_a - ids_b,
        changes=changes,
    )
