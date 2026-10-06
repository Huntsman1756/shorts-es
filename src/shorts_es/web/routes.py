"""API (/api/v1) and HTML routes. All read-only."""

from __future__ import annotations

import sqlite3
from datetime import date
from decimal import Decimal

from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import HTMLResponse, RedirectResponse

from .. import __version__, constants
from ..domain import identifiers, reconstruction, verification
from ..domain.diff import diff_snapshots
from ..domain.provenance import provenance_for, source_descriptor
from ..exceptions import AmbiguousIdentifierError, NotFoundError
from ..storage import repository as repo
from .app import dataset_or_404, get_conn

api = APIRouter()
pages = APIRouter(default_response_class=HTMLResponse)


# ------------------------------------------------------------------ helpers


def _disclosure_json(row) -> dict:
    return {
        "disclosure_id": row["disclosure_id"],
        "lei": row["lei"],
        "isin": row["isin"],
        "issuer_name": row["issuer_name"],
        "holder_name": row["holder_name"],
        "position_date": row["position_date"],
        "position_pct": row["position_pct"],
        "first_observed_at": row["first_observed_at"],
        "first_snapshot_sha256": row["first_snapshot_sha256"],
    }


def _pair_json(s: reconstruction.PairState) -> dict:
    return {
        "lei": s.lei,
        "isin": s.isin,
        "issuer_name": s.issuer_name,
        "holder_name": s.holder_name,
        "position_date": s.position_date.isoformat(),
        "position_pct": str(s.position_pct),
        "state": s.state.value,
        "above_public_threshold": s.above_public_threshold,
        "in_current_sheet": s.in_current_sheet,
        "disclosure_id": s.disclosure_id,
    }


def _snapshot_json(row) -> dict:
    return {
        "snapshot_sha256": row["snapshot_sha256"],
        "retrieved_at": row["retrieved_at"],
        "source_url": row["source_url"],
        "content_length": row["content_length"],
        "etag": row["etag"],
        "last_modified": row["last_modified"],
        "publication_date": row["publication_date"],
        "parser_version": row["parser_version"],
        "schema_fingerprint": row["schema_fingerprint"],
        "status": row["status"],
    }


def _dataset_payload(conn) -> dict:
    stats = repo.dataset_stats(conn)
    latest = repo.latest_snapshot(conn)
    payload = {
        "app": "shorts-es",
        "version": __version__,
        "parser_version": constants.PARSER_VERSION,
        "authority": constants.SOURCE_AUTHORITY,
        "source_url": constants.SOURCE_URL,
        "stats": dict(stats),
        "latest_snapshot": _snapshot_json(latest) if latest else None,
    }
    if latest:
        v = repo.latest_verification(conn, latest["snapshot_sha256"])
        payload["verification"] = (
            {
                "result": v["result"],
                "verified_at": v["verified_at"],
                "pairs_checked": v["pairs_checked"],
                "matched": v["matched"],
            }
            if v
            else None
        )
    return payload


def _known_bounds(conn) -> tuple[date | None, object]:
    eff = None
    return eff, None


# ---------------------------------------------------------------------- API


@api.get("/health")
def health(conn: sqlite3.Connection = Depends(get_conn)) -> dict:
    latest = repo.latest_snapshot(conn)
    return {
        "status": "ok" if latest else "empty",
        "version": __version__,
        "latest_snapshot": latest["snapshot_sha256"] if latest else None,
    }


@api.get("/dataset")
def dataset(conn: sqlite3.Connection = Depends(get_conn)) -> dict:
    return _dataset_payload(conn)


@api.get("/current/{identifier}")
def current(identifier: str, conn: sqlite3.Connection = Depends(get_conn)) -> dict:
    snap = dataset_or_404(conn)
    refs = identifiers.resolve_issuers(conn, identifier)
    cur_pairs = reconstruction.current_pair_keys(conn, snap["snapshot_sha256"])
    issuers = []
    for ref in refs:
        states = reconstruction.issuer_states(conn, ref.isin, current_pairs=cur_pairs)
        issuers.append(
            {
                "isin": ref.isin,
                "lei": ref.lei,
                "issuer_name": ref.issuer_name,
                "disclosed_total_pct": str(
                    sum((s.position_pct for s in states if s.in_current_sheet), Decimal(0))
                ),
                "positions": [_pair_json(s) for s in states],
            }
        )
    return {
        "snapshot_sha256": snap["snapshot_sha256"],
        "observed_at": snap["retrieved_at"],
        "issuers": issuers,
        "note": "Publicly disclosed positions are not total short interest.",
    }


@api.get("/history/{identifier}")
def history(
    identifier: str,
    holder: str | None = Query(default=None),
    conn: sqlite3.Connection = Depends(get_conn),
) -> dict:
    refs = identifiers.resolve_issuers(conn, identifier)
    holder_name = identifiers.resolve_holder(conn, holder) if holder else None
    out = []
    for ref in refs:
        rows = repo.disclosures_for_issuer(conn, ref.isin)
        if holder_name:
            rows = [r for r in rows if r["holder_name"] == holder_name]
        out.append(
            {
                "isin": ref.isin,
                "issuer_name": ref.issuer_name,
                "disclosures": [_disclosure_json(r) for r in rows],
            }
        )
    return {"issuers": out}


@api.get("/holders/{name}")
def holder_positions(name: str, conn: sqlite3.Connection = Depends(get_conn)) -> dict:
    snap = dataset_or_404(conn)
    holder = identifiers.resolve_holder(conn, name)
    cur = reconstruction.current_pair_keys(conn, snap["snapshot_sha256"])
    states = reconstruction.holder_states(conn, holder, current_pairs=cur)
    return {
        "holder_name": holder,
        "snapshot_sha256": snap["snapshot_sha256"],
        "positions": [_pair_json(s) for s in states],
    }


@api.get("/changes")
def changes(since: date, conn: sqlite3.Connection = Depends(get_conn)) -> dict:
    rows = repo.disclosures_first_observed_since(conn, since.isoformat())
    return {
        "since": since.isoformat(),
        "count": len(rows),
        "disclosures": [_disclosure_json(r) for r in rows],
    }


@api.get("/snapshots")
def snapshots(conn: sqlite3.Connection = Depends(get_conn)) -> dict:
    rows = repo.list_snapshots(conn)
    return {"snapshots": [_snapshot_json(r) for r in rows]}


@api.get("/snapshots/{sha}/diff/{other}")
def snapshot_diff(sha: str, other: str, conn: sqlite3.Connection = Depends(get_conn)) -> dict:
    d = diff_snapshots(conn, sha, other)
    return {
        "a": d.sha_a,
        "b": d.sha_b,
        "added_disclosures": len(d.added_ids),
        "removed_disclosures": len(d.removed_ids),
        "changes": [
            {
                "lei": c.lei,
                "isin": c.isin,
                "issuer_name": c.issuer_name,
                "holder_name": c.holder_name,
                "kind": c.kind,
                "direction": c.direction,
                "old": c.old,
                "new": c.new,
            }
            for c in d.changes
        ],
    }


@api.get("/disclosures/{disclosure_id}")
def disclosure_detail(disclosure_id: str, conn: sqlite3.Connection = Depends(get_conn)) -> dict:
    p = provenance_for(conn, disclosure_id)
    return {
        "disclosure_id": p.disclosure_id,
        "canonical": p.canonical_json,
        "first_observed_at": p.first_observed_at,
        "first_snapshot_sha256": p.first_snapshot_sha256,
        "locations": p.locations,
        "source": source_descriptor(),
    }


@api.get("/verify")
def verify(conn: sqlite3.Connection = Depends(get_conn)) -> dict:
    snap = dataset_or_404(conn)
    result = verification.verify_snapshot(conn, snap["snapshot_sha256"])
    return {
        "snapshot_sha256": result.snapshot_sha256,
        "result": "PASS" if result.passed else "FAIL",
        **result.counts(),
        "details": result.details(),
    }


# --------------------------------------------------------------------- HTML


def _t(request: Request):
    return request.app.state.templates


def _base_ctx(request: Request, conn) -> dict:
    return {
        "request": request,
        "data": _dataset_payload(conn),
        "constants": constants,
        "version": __version__,
    }


@pages.get("/")
def index(request: Request, conn: sqlite3.Connection = Depends(get_conn)):
    return _t(request).TemplateResponse(request, "index.html", _base_ctx(request, conn))


@pages.get("/search")
def search(request: Request, q: str, conn: sqlite3.Connection = Depends(get_conn)):
    q = q.strip()
    try:
        refs = identifiers.resolve_issuers(conn, q)
    except NotFoundError:
        # try holder
        try:
            name = identifiers.resolve_holder(conn, q)
            return RedirectResponse(f"/holder/{name}", status_code=303)
        except NotFoundError:
            ctx = _base_ctx(request, conn)
            ctx.update({"q": q, "error": f"No issuer or holder matches {q!r}."})
            return _t(request).TemplateResponse(request, "index.html", ctx, status_code=404)
    except AmbiguousIdentifierError as exc:
        ctx = _base_ctx(request, conn)
        ctx.update({"q": q, "candidates": exc.candidates})
        return _t(request).TemplateResponse(request, "index.html", ctx)
    if len(refs) == 1:
        return RedirectResponse(f"/issuer/{refs[0].isin}", status_code=303)
    ctx = _base_ctx(request, conn)
    ctx.update({"q": q, "issuer_refs": refs})
    return _t(request).TemplateResponse(request, "index.html", ctx)


@pages.get("/issuer/{identifier}")
def issuer_page(request: Request, identifier: str, conn: sqlite3.Connection = Depends(get_conn)):
    snap = dataset_or_404(conn)
    refs = identifiers.resolve_issuers(conn, identifier)
    if len(refs) != 1:
        ctx = _base_ctx(request, conn)
        ctx.update({"issuer_refs": refs, "q": identifier})
        return _t(request).TemplateResponse(request, "index.html", ctx)
    ref = refs[0]
    cur = reconstruction.current_pair_keys(conn, snap["snapshot_sha256"])
    states = reconstruction.issuer_states(conn, ref.isin, current_pairs=cur)
    history_rows = repo.disclosures_for_issuer(conn, ref.isin)
    ctx = _base_ctx(request, conn)
    ctx.update(
        {
            "issuer": ref,
            "in_current": [s for s in states if s.in_current_sheet],
            "not_current": [s for s in states if not s.in_current_sheet],
            "disclosed_total": sum(
                (s.position_pct for s in states if s.in_current_sheet), Decimal(0)
            ),
            "history": history_rows,
            "snapshot": snap,
        }
    )
    return _t(request).TemplateResponse(request, "issuer.html", ctx)


@pages.get("/holder/{name}")
def holder_page(request: Request, name: str, conn: sqlite3.Connection = Depends(get_conn)):
    snap = dataset_or_404(conn)
    holder = identifiers.resolve_holder(conn, name)
    cur = reconstruction.current_pair_keys(conn, snap["snapshot_sha256"])
    states = reconstruction.holder_states(conn, holder, current_pairs=cur)
    rows = repo.disclosures_for_holder(conn, holder)
    ctx = _base_ctx(request, conn)
    ctx.update(
        {
            "holder_name": holder,
            "states": states,
            "history": rows,
            "snapshot": snap,
        }
    )
    return _t(request).TemplateResponse(request, "holder.html", ctx)


@pages.get("/snapshots")
def snapshots_page(request: Request, conn: sqlite3.Connection = Depends(get_conn)):
    ctx = _base_ctx(request, conn)
    rows = repo.list_snapshots(conn)
    ctx["snapshots"] = [
        {
            **_snapshot_json(r),
            "n_rows": conn.execute(
                "SELECT COUNT(*) FROM snapshot_disclosure WHERE snapshot_sha256=?",
                (r["snapshot_sha256"],),
            ).fetchone()[0],
            "verification": (v := repo.latest_verification(conn, r["snapshot_sha256"]))
            and {
                "result": v["result"],
                "matched": v["matched"],
                "pairs_checked": v["pairs_checked"],
            },
        }
        for r in rows
    ]
    return _t(request).TemplateResponse(request, "snapshots.html", ctx)


@pages.get("/snapshots/{sha}")
def snapshot_page(request: Request, sha: str, conn: sqlite3.Connection = Depends(get_conn)):
    snap = repo.get_snapshot(conn, sha)
    if snap is None:
        raise NotFoundError(f"snapshot not found: {sha}")
    ctx = _base_ctx(request, conn)
    ctx.update(
        {
            "snapshot": snap,
            "sheets": repo.snapshot_sheets(conn, snap["snapshot_sha256"]),
            "verification": repo.latest_verification(conn, snap["snapshot_sha256"]),
        }
    )
    return _t(request).TemplateResponse(request, "snapshot.html", ctx)


@pages.get("/disclosure/{disclosure_id}")
def disclosure_page(
    request: Request, disclosure_id: str, conn: sqlite3.Connection = Depends(get_conn)
):
    d = repo.get_disclosure(conn, disclosure_id)
    if d is None:
        rows = conn.execute(
            "SELECT disclosure_id FROM disclosure WHERE disclosure_id LIKE ? LIMIT 2",
            (disclosure_id + "%",),
        ).fetchall()
        if len(rows) == 1:
            d = repo.get_disclosure(conn, rows[0][0])
    if d is None:
        raise NotFoundError(f"disclosure not found: {disclosure_id}")
    p = provenance_for(conn, d["disclosure_id"])
    ctx = _base_ctx(request, conn)
    ctx.update({"d": d, "prov": p, "source": source_descriptor()})
    return _t(request).TemplateResponse(request, "disclosure.html", ctx)


@pages.get("/changes")
def changes_page(request: Request, since: date, conn: sqlite3.Connection = Depends(get_conn)):
    rows = repo.disclosures_first_observed_since(conn, since.isoformat())
    ctx = _base_ctx(request, conn)
    ctx.update({"since": since, "rows": rows})
    return _t(request).TemplateResponse(request, "changes.html", ctx)


@pages.get("/methodology")
def methodology_page(request: Request, conn: sqlite3.Connection = Depends(get_conn)):
    return _t(request).TemplateResponse(request, "methodology.html", _base_ctx(request, conn))
