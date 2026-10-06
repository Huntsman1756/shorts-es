"""Provenance chain: answer -> disclosure -> rows -> snapshots -> source."""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass

from .. import constants
from ..exceptions import NotFoundError
from ..storage import repository as repo


@dataclass(frozen=True)
class ProvenanceRecord:
    disclosure_id: str
    canonical_json: str
    first_observed_at: str
    first_snapshot_sha256: str
    locations: list[dict]  # snapshot, sheet, row


def provenance_for(conn: sqlite3.Connection, disclosure_id: str) -> ProvenanceRecord:
    d = repo.get_disclosure(conn, disclosure_id)
    if d is None:
        raise NotFoundError(f"disclosure not found: {disclosure_id}")
    rows = repo.disclosure_provenance(conn, disclosure_id)
    locations = [
        {
            "snapshot_sha256": r["snapshot_sha256"],
            "sheet_name": r["sheet_name"],
            "row_number": r["row_number"],
            "retrieved_at": r["retrieved_at"],
            "parser_version": r["parser_version"],
            "schema_fingerprint": r["schema_fingerprint"],
        }
        for r in rows
    ]
    return ProvenanceRecord(
        disclosure_id=d["disclosure_id"],
        canonical_json=d["canonical_json"],
        first_observed_at=d["first_observed_at"],
        first_snapshot_sha256=d["first_snapshot_sha256"],
        locations=locations,
    )


def source_descriptor() -> dict:
    return {
        "authority": constants.SOURCE_AUTHORITY,
        "workbook": constants.SOURCE_WORKBOOK_NAME,
        "source_url": constants.SOURCE_URL,
        "reference_page": constants.SOURCE_PAGE_URL,
    }
