"""API (/api/v1) and HTML routes. All read-only."""

from __future__ import annotations

import sqlite3
from datetime import date
from decimal import Decimal

from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from markupsafe import Markup

from .. import __version__, constants
from ..domain import identifiers, reconstruction, verification
from ..domain.diff import diff_snapshots
from ..domain.provenance import provenance_for, source_descriptor
from ..exceptions import AmbiguousIdentifierError, NotFoundError
from ..storage import repository as repo
from .app import dataset_or_404, get_conn

# Valid sort columns and their SQL equivalents per entity type
ISSUER_SORT_COLUMNS = {
    "capital": "disclosed_total",
    "funds": "funds",
    "date": "last_position_date",
    "name": "issuer_name",
    "isin": "isin",
}

HOLDER_SORT_COLUMNS = {
    "positions": "positions",
    "capital": "disclosed_total",
    "issuers": "issuers",
    "date": "last_position_date",
    "name": "holder_name",
}

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


@api.get("/issuers")
def issuers_ranking(conn: sqlite3.Connection = Depends(get_conn)) -> dict:
    snap = dataset_or_404(conn)
    return {
        "snapshot_sha256": snap["snapshot_sha256"],
        "issuers": repo.issuer_current_ranking(conn, snap["snapshot_sha256"]),
        "note": "disclosed_total = sum of published individual positions. "
        "Not total short interest.",
    }


@api.get("/holders")
def holders_ranking(conn: sqlite3.Connection = Depends(get_conn)) -> dict:
    snap = dataset_or_404(conn)
    return {
        "snapshot_sha256": snap["snapshot_sha256"],
        "holders": repo.holder_current_ranking(conn, snap["snapshot_sha256"]),
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


@api.get("/integrity")
def integrity_check(conn: sqlite3.Connection = Depends(get_conn)) -> dict:
    """Run SQLite PRAGMA integrity_check."""
    result = conn.execute("PRAGMA integrity_check").fetchone()[0]
    stats = repo.dataset_stats(conn)
    return {
        "integrity": result,
        "stats": dict(stats),
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
        "_safe_float": _safe_float,
    }


def _sort_link_params(sort_col: str, direction: str, query: str | None = None, column_keys: dict[str, str] | None = None) -> str:
    """Build query-string fragment for sort link.
    
    The returned string starts with ? or & so it can be appended to the current path.
    """
    parts: list[str] = []
    if query:
        parts.append(f"q={query}")
    parts.append(f"orden={sort_col}")
    parts.append(f"dir={direction}")
    return "?" + "&".join(parts)


def _pct_width(value_str: str, max_val: float) -> float:
    """Return bar width (px) for a percentage value."""
    try:
        val = float(value_str.replace("%", ""))
    except (ValueError, TypeError):
        return 0
    if max_val <= 0:
        return 0
    width = (val / max_val) * 100
    return min(width, 100)


def _filter_issuers(issuers: list[dict], q: str) -> list[dict]:
    """Server-side filter issuers by name, ISIN or LEI."""
    if not q:
        return issuers
    q_lower = q.lower()
    return [
        i for i in issuers
        if q_lower in i["issuer_name"].lower()
        or q_lower in i["isin"].lower()
        or (i.get("lei") and q_lower in i["lei"].lower())
    ]


def _apply_issuer_sort(issuers: list[dict], sort_col: str, direction: str) -> list[dict]:
    """Apply server-side sort to an already-computed issuer ranking."""
    key_map = {
        "capital": lambda e: _safe_float(e.get("disclosed_total", "0").replace("%", "")),
        "funds": lambda e: int(e.get("funds", 0)),
        "date": lambda e: e.get("last_position_date", ""),
        "name": lambda e: e.get("issuer_name", ""),
        "isin": lambda e: e.get("isin", ""),
    }
    key_fn = key_map.get(sort_col, key_map["capital"])
    reverse = direction == "desc"
    return sorted(issuers, key=key_fn, reverse=reverse)


def _safe_float(s: str) -> float:
    try:
        return float(s)
    except (ValueError, TypeError):
        return 0.0


def svg_line_chart(history_rows: list, disclosed_total: str, width: int = 700, height: int = 200) -> str:
    """Generate an inline SVG line chart of aggregated % over time."""
    from collections import defaultdict
    from markupsafe import Markup

    date_totals: dict[str, float] = defaultdict(float)
    for r in history_rows:
        try:
            pct = float(r["position_pct"].replace("%", ""))
        except (ValueError, TypeError):
            continue
        date_totals[r["position_date"]] += pct

    if not date_totals:
        return Markup('<text x="10" y="100" font-size="14" fill="#64748b">Sin datos</text>')

    dates = sorted(date_totals.keys())
    values = [date_totals[d] for d in dates]
    n = len(dates)
    if n < 2:
        return Markup('<text x="10" y="100" font-size="14" fill="#64748b">Necesito al menos 2 fechas</text>')

    margin = {"top": 20, "right": 20, "bottom": 40, "left": 50}
    cw = width - margin["left"] - margin["right"]
    ch = height - margin["top"] - margin["bottom"]

    min_val = min(values)
    max_val = max(values)
    val_range = max_val - min_val if max_val != min_val else 1.0
    min_val -= val_range * 0.05
    max_val += val_range * 0.05
    val_range = max_val - min_val

    def x_pos(i):
        return margin["left"] + (i / (n - 1)) * cw if n > 1 else margin["left"] + cw / 2

    def y_pos(val):
        return margin["top"] + ch - ((val - min_val) / val_range) * ch

    parts = []
    parts.append(f'<line x1="{margin['left']}" y1="{margin['top']}" x2="{margin['left']}" y2="{margin['top']+ch}" stroke="#e2e8f0" stroke-width="1"/>')
    parts.append(f'<line x1="{margin['left']}" y1="{margin['top']+ch}" x2="{margin['left']+cw}" y2="{margin['top']+ch}" stroke="#e2e8f0" stroke-width="1"/>')

    for i in range(6):
        val = min_val + (val_range * i / 5)
        y = y_pos(val)
        parts.append(f'<text x="{margin['left']-5}" y="{y+4}" text-anchor="end" font-size="10" fill="#64748b">{val:.2f}%</text>')
        parts.append(f'<line x1="{margin['left']}" y1="{y}" x2="{margin['left']+cw}" y2="{y}" stroke="#f1f5f9" stroke-width="1"/>')

    step = max(1, n // 10)
    for i in range(0, n, step):
        x = x_pos(i)
        parts.append(f'<text x="{x}" y="{margin['top']+ch+20}" text-anchor="middle" font-size="9" fill="#64748b">{dates[i]}</text>')

    line_parts = []
    for i in range(n):
        x = x_pos(i)
        y = y_pos(values[i])
        line_parts.append(f'M{x},{y}' if i == 0 else f'L{x},{y}')
    parts.append(f'<polyline points="{" ".join(line_parts)}" fill="none" stroke="#2563eb" stroke-width="2" stroke-linejoin="round"/>')

    for i in range(n):
        x = x_pos(i)
        y = y_pos(values[i])
        parts.append(f'<circle cx="{x}" cy="{y}" r="3.5" fill="#2563eb"/>')
        parts.append(f'<text x="{x}" y="{y-8}" text-anchor="middle" font-size="9" font-weight="600" fill="#0f172a">{values[i]:.2f}%</text>')

    return Markup("".join(parts))


def _filter_holders(holders: list[dict], q: str) -> list[dict]:
    """Server-side filter holders by name."""
    if not q:
        return holders
    q_lower = q.lower()
    return [
        h for h in holders
        if q_lower in h["holder_name"].lower()
    ]


def _apply_holder_sort(holders: list[dict], sort_col: str, direction: str) -> list[dict]:
    key_map = {
        "positions": lambda e: int(e.get("positions", 0)),
        "capital": lambda e: _safe_float(e.get("disclosed_total", "0").replace("%", "")),
        "issuers": lambda e: int(e.get("issuers", 0)),
        "date": lambda e: e.get("last_position_date", ""),
        "name": lambda e: e.get("holder_name", ""),
    }
    key_fn = key_map.get(sort_col, key_map["positions"])
    reverse = direction == "desc"
    return sorted(holders, key=key_fn, reverse=reverse)


@pages.get("/")
def index(request: Request, conn: sqlite3.Connection = Depends(get_conn)):
    ctx = _base_ctx(request, conn)
    snap = repo.latest_snapshot(conn)
    if snap:
        sha = snap["snapshot_sha256"]
        top_iss = repo.issuer_current_ranking(conn, sha)[:10]
        top_holds = repo.holder_current_ranking(conn, sha)[:10]
        max_p_i = max((_safe_float(i.get("disclosed_total", "0").replace("%", "")) for i in top_iss), default=1.0)
        if max_p_i == 0: max_p_i = 1.0
        max_p_h = max((_safe_float(h.get("disclosed_total", "0").replace("%", "")) for h in top_holds), default=1.0)
        if max_p_h == 0: max_p_h = 1.0
        ctx.update(
            {
                "top_issuers": top_iss,
                "top_holders": top_holds,
                "latest_rows": repo.latest_current_rows(conn, sha, limit=12),
                "pct_width": lambda val, mx: _pct_width(val, mx),
                "max_pct_i": max_p_i,
                "max_pct_h": max_p_h,
            }
        )
    return _t(request).TemplateResponse(request, "index.html", ctx)


@pages.get("/issuers")
def issuers_page(
    request: Request,
    conn: sqlite3.Connection = Depends(get_conn),
    orden: str = Query(default="capital", description="Orden de clasificación"),
    dir: str = Query(default="desc", description="Dirección asc/desc"),
    q: str | None = Query(default=None, description="Filtro por nombre, ISIN o LEI"),
):
    snap = dataset_or_404(conn)
    raw = repo.issuer_current_ranking(conn, snap["snapshot_sha256"])
    issuers = _filter_issuers(raw, q or "")
    # Default sort is capital desc; apply user sort if valid
    valid_sorts = set(ISSUER_SORT_COLUMNS.keys())
    if orden in valid_sorts and dir in ("asc", "desc"):
        issuers = _apply_issuer_sort(issuers, orden, dir)
    else:
        issuers = sorted(issuers, key=lambda e: -float(e.get("disclosed_total", "0").replace("%", "")) or 0)
    # Compute max_pct for bar widths
    max_pct = max((_safe_float(e.get("disclosed_total", "0").replace("%", "")) for e in issuers), default=1.0)
    if max_pct == 0:
        max_pct = 1.0
    ctx = _base_ctx(request, conn)
    ctx.update(
        {
            "issuers": issuers,
            "snapshot": snap,
            "sort": orden,
            "dir": dir,
            "q": q,
            "sort_link_params": _sort_link_params,
            "pct_width": lambda val, mx: _pct_width(val, mx),
            "max_pct": max_pct,
        }
    )
    return _t(request).TemplateResponse(request, "issuers.html", ctx)


@pages.get("/holders")
def holders_page(
    request: Request,
    conn: sqlite3.Connection = Depends(get_conn),
    orden: str = Query(default="positions", description="Orden de clasificación"),
    dir: str = Query(default="desc", description="Dirección asc/desc"),
    q: str | None = Query(default=None, description="Filtro por nombre"),
):
    snap = dataset_or_404(conn)
    raw = repo.holder_current_ranking(conn, snap["snapshot_sha256"])
    holders = _filter_holders(raw, q or "")
    valid_sorts = set(HOLDER_SORT_COLUMNS.keys())
    if orden in valid_sorts and dir in ("asc", "desc"):
        holders = _apply_holder_sort(holders, orden, dir)
    else:
        holders = sorted(holders, key=lambda e: -int(e.get("positions", 0)))
    max_pct = max((_safe_float(e.get("disclosed_total", "0").replace("%", "")) for e in holders), default=1.0)
    if max_pct == 0:
        max_pct = 1.0
    ctx = _base_ctx(request, conn)
    ctx.update(
        {
            "holders": holders,
            "snapshot": snap,
            "sort": orden,
            "dir": dir,
            "q": q,
            "sort_link_params": _sort_link_params,
            "pct_width": lambda val, mx: _pct_width(val, mx),
            "max_pct": max_pct,
        }
    )
    return _t(request).TemplateResponse(request, "holders.html", ctx)


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
    n_holders = len([s for s in states if s.in_current_sheet])
    total_pct = str(sum(
        (s.position_pct for s in states if s.in_current_sheet), Decimal(0)
    ))
    if n_holders > 0:
        summary = f"{n_holders} fondos tienen posición corta en {ref.issuer_name}; en total, el {total_pct} % del capital está en corto"
    else:
        summary = f"No se encuentran posiciones publicadas actualmente para {ref.issuer_name}."
    ctx.update(
        {
            "issuer": ref,
            "in_current": [s for s in states if s.in_current_sheet],
            "not_current": [s for s in states if not s.in_current_sheet],
            "disclosed_total": total_pct,
            "history": history_rows,
            "snapshot": snap,
            "svg_line_chart": svg_line_chart,
            "summary": summary,
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
    # Pre-compute summary
    from ..domain import reconstruction as recon
    cur_states = [s for s in states if s.in_current_sheet]
    n_issuers = len(cur_states)
    total_pct = sum((s.position_pct for s in cur_states), Decimal(0))
    pct_str = str(total_pct)
    if n_issuers > 0:
        summary = f"{n_issuers} emisores con posición corta de {pct_str}; en total, el {pct_str}% del capital está en corto de {holder}"
    else:
        summary = f"No se encuentran posiciones publicadas actualmente para este titular."
    holder_lei = cur_states[0].lei if cur_states else None
    ctx = _base_ctx(request, conn)
    ctx.update(
        {
            "holder_name": holder,
            "states": states,
            "history": rows,
            "snapshot": snap,
            "summary": summary,
            "holder_lei": holder_lei,
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


@pages.get("/glossary")
def glossary_page(request: Request, conn: sqlite3.Connection = Depends(get_conn)):
    return _t(request).TemplateResponse(request, "glossary.html", _base_ctx(request, conn))
