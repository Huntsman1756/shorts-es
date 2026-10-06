"""shorts-es CLI.

All commands share one core: the same parser, ledger and domain projections
used by the web API. No regulatory logic lives here - only presentation.
"""

from __future__ import annotations

import json
import logging
import sqlite3
from pathlib import Path

import typer

from .. import constants
from ..config import Config
from ..domain import identifiers, reconstruction, temporal, verification
from ..domain.diff import diff_snapshots
from ..domain.provenance import provenance_for, source_descriptor
from ..domain.states import DisclosureState, HistoryClass
from ..exceptions import (
    AmbiguousIdentifierError,
    InsufficientKnowledgeHistoryError,
    NoDataError,
    NotFoundError,
    ShortsEsError,
)
from ..pipeline import sync as run_sync
from ..storage import repository as repo

app = typer.Typer(
    name="shorts-es",
    help="Reproducible access to CNMV public net short-position disclosures.",
    no_args_is_help=True,
)

_data_dir: Path | None = None


@app.callback()
def _callback(
    data_dir: Path | None = typer.Option(
        None,
        "--data-dir",
        envvar="SHORTS_ES_DATA_DIR",
        help="Directory for snapshots + SQLite ledger.",
    ),
    verbose: bool = typer.Option(False, "-v", "--verbose"),
) -> None:
    global _data_dir
    _data_dir = data_dir
    logging.basicConfig(
        level=logging.DEBUG if verbose else logging.WARNING,
        format="%(levelname)s %(name)s: %(message)s",
    )


def _config() -> Config:
    return Config.resolve(_data_dir)


def _conn() -> sqlite3.Connection:
    cfg = _config()
    return repo_conn(cfg)


def repo_conn(cfg: Config) -> sqlite3.Connection:
    from ..pipeline import connect

    return connect(cfg)


def _latest_sha(conn) -> str:
    snap = repo.latest_snapshot(conn)
    if snap is None:
        raise NoDataError("no snapshots yet - run 'shorts-es sync' first")
    return snap["snapshot_sha256"]


def _err(exc: ShortsEsError) -> None:
    typer.secho(f"error {exc.code}: {exc.message}", err=True, fg=typer.colors.RED)
    if isinstance(exc, AmbiguousIdentifierError):
        for c in exc.candidates:
            typer.echo(f"  - {c}", err=True)
    raise typer.Exit(code=2)


def _knowledge_guard(conn, known_at) -> None:
    if known_at is None:
        return
    first = repo.first_observed_at(conn)
    if first and temporal.iso_utc(known_at) < first:
        raise InsufficientKnowledgeHistoryError(
            f"known_at {temporal.iso_utc(known_at)} predates our first "
            f"observation ({first}); nothing was verifiably known then"
        )


def _pct(row) -> str:
    return row["position_pct"]


def _hist_class(conn, row) -> str:
    first_snap = conn.execute("SELECT MIN(retrieved_at) FROM snapshot").fetchone()[0]
    if row["first_observed_at"] == first_snap or (row["first_observed_at"] <= (first_snap or "")):
        return HistoryClass.RECONSTRUCTED_HISTORICAL.value
    return HistoryClass.OBSERVED_CURRENT.value


# ---------------------------------------------------------------------- sync


@app.command()
def sync(
    file: Path | None = typer.Option(
        None, "--file", help="Ingest a local .xls instead of downloading."
    ),
    url: str | None = typer.Option(None, "--url", help="Override source URL."),
) -> None:
    """Fetch the CNMV workbook, snapshot it, and ingest disclosures."""
    try:
        result = run_sync(_config(), file=str(file) if file else None, url=url)
    except ShortsEsError as exc:
        _err(exc)
        return
    typer.echo(f"snapshot:  {result.sha256}")
    typer.echo(f"status:    {result.status}")
    typer.echo(f"retrieved: {result.retrieved_at}")
    if result.publication_date:
        typer.echo(f"published: {result.publication_date} (declared by source)")
    if result.status != "NO_CHANGE":
        typer.echo(f"rows:      {result.total_rows} parsed")
        typer.echo(f"new disclosures: {result.new_disclosures}")


# ------------------------------------------------------------------- current


def _print_pair_states(states, issuer_name: str, isin: str, conn) -> None:
    in_current = [s for s in states if s.in_current_sheet]
    not_current = [s for s in states if not s.in_current_sheet]
    total = sum(s.position_pct for s in in_current)
    typer.echo(f"{issuer_name} ({isin})")
    typer.echo("")
    typer.echo("Currently published (source Current sheet):")
    typer.echo(f"{'Holder':<62} {'Pos%':>6}  {'Date':<12} ID")
    for s in in_current:
        typer.echo(
            f"{s.holder_name[:60]:<62} {s.position_pct!s:>6}  "
            f"{s.position_date.isoformat():<12} {s.disclosure_id[:12]}"
        )
    typer.echo("")
    typer.echo(f"Publicly disclosed total: {total} %")
    typer.echo("(Sum of publicly disclosed individual positions. Not total short interest.)")
    if not_current:
        typer.echo("")
        typer.echo(
            f"Pairs with published history but no current publication: "
            f"{len(not_current)} (last published value shown; absence is not zero)"
        )
        typer.echo(f"{'Holder':<62} {'Pos%':>6}  {'Last date':<12}")
        for s in not_current:
            typer.echo(
                f"{s.holder_name[:60]:<62} {s.position_pct!s:>6}  "
                f"{s.position_date.isoformat():<12}"
            )


@app.command()
def current(
    identifier: str = typer.Argument(..., help="ISIN, LEI or issuer name."),
    effective_at: str | None = typer.Option(None, "--effective-at"),
    known_at: str | None = typer.Option(None, "--known-at"),
    json_out: bool = typer.Option(False, "--json"),
) -> None:
    """Latest published net-short disclosures for an issuer."""
    conn = _conn()
    try:
        snap_row = repo.latest_snapshot(conn)
        if snap_row is None:
            raise NoDataError("no snapshots yet - run 'shorts-es sync' first")
        refs = identifiers.resolve_issuers(conn, identifier)
        eff = temporal.parse_effective_date(effective_at) if effective_at else None
        kn = temporal.parse_known_at(known_at) if known_at else None
        _knowledge_guard(conn, kn)
        # Current-sheet membership is evaluated on the latest snapshot
        # observed at/before the knowledge cutoff, not silently dropped.
        snap_for_current = (
            repo.latest_snapshot_before(conn, temporal.iso_utc(kn)) if kn else snap_row
        )
        if snap_for_current is None:
            raise InsufficientKnowledgeHistoryError(
                f"no snapshot observed at/before {temporal.iso_utc(kn)}"
            )
        cur_pairs = reconstruction.current_pair_keys(conn, snap_for_current["snapshot_sha256"])
        for ref in refs:
            states = reconstruction.issuer_states(
                conn, ref.isin, effective_at=eff, known_at=kn, current_pairs=cur_pairs
            )
            if json_out:
                in_current = [s for s in states if s.in_current_sheet]
                typer.echo(
                    json.dumps(
                        {
                            "isin": ref.isin,
                            "lei": ref.lei,
                            "issuer_name": ref.issuer_name,
                            "snapshot_sha256": snap_for_current["snapshot_sha256"],
                            "disclosed_total_pct": str(sum(s.position_pct for s in in_current)),
                            "positions": [
                                {
                                    "holder_name": s.holder_name,
                                    "position_pct": str(s.position_pct),
                                    "position_date": s.position_date.isoformat(),
                                    "state": s.state.value,
                                    "in_current_sheet": s.in_current_sheet,
                                    "disclosure_id": s.disclosure_id,
                                }
                                for s in states
                            ],
                        },
                        ensure_ascii=False,
                    )
                )
            else:
                _print_pair_states(states, ref.issuer_name, ref.isin, conn)
    except ShortsEsError as exc:
        _err(exc)
    finally:
        conn.close()


# ------------------------------------------------------------------- history


@app.command()
def history(
    identifier: str = typer.Argument(..., help="ISIN, LEI or issuer name."),
    holder: str | None = typer.Option(None, "--holder", help="Restrict to one holder."),
    json_out: bool = typer.Option(False, "--json"),
) -> None:
    """Full published disclosure history for an issuer (optionally one holder)."""
    conn = _conn()
    try:
        refs = identifiers.resolve_issuers(conn, identifier)
        holder_name = identifiers.resolve_holder(conn, holder) if holder else None
        for ref in refs:
            rows = repo.disclosures_for_issuer(conn, ref.isin)
            if holder_name:
                rows = [r for r in rows if r["holder_name"] == holder_name]
            if json_out:
                typer.echo(
                    json.dumps(
                        [
                            {
                                "disclosure_id": r["disclosure_id"],
                                "holder_name": r["holder_name"],
                                "position_date": r["position_date"],
                                "position_pct": r["position_pct"],
                                "first_observed_at": r["first_observed_at"],
                                "history_class": _hist_class(conn, r),
                            }
                            for r in rows
                        ],
                        ensure_ascii=False,
                    )
                )
                continue
            typer.echo(f"{ref.issuer_name} ({ref.isin}) - {len(rows)} disclosures")
            typer.echo("")
            typer.echo(f"{'Date':<12} {'Pos%':>6}  {'Holder':<50} {'Class':<26} ID")
            for r in sorted(
                rows, key=lambda x: (x["holder_name"], x["position_date"]), reverse=False
            ):
                typer.echo(
                    f"{r['position_date']:<12} {r['position_pct']:>6}  "
                    f"{r['holder_name'][:48]:<50} {_hist_class(conn, r):<26} "
                    f"{r['disclosure_id'][:12]}"
                )
    except ShortsEsError as exc:
        _err(exc)
    finally:
        conn.close()


# -------------------------------------------------------------------- holder


@app.command()
def holder(
    name: str = typer.Argument(..., help="Position holder name."),
    json_out: bool = typer.Option(False, "--json"),
) -> None:
    """Latest published position of a holder on each issuer."""
    conn = _conn()
    try:
        sha = _latest_sha(conn)
        holder_name = identifiers.resolve_holder(conn, name)
        cur_pairs = reconstruction.current_pair_keys(conn, sha)
        states = reconstruction.holder_states(conn, holder_name, current_pairs=cur_pairs)
        if json_out:
            typer.echo(
                json.dumps(
                    {
                        "holder_name": holder_name,
                        "positions": [
                            {
                                "isin": s.isin,
                                "issuer_name": s.issuer_name,
                                "position_pct": str(s.position_pct),
                                "position_date": s.position_date.isoformat(),
                                "in_current_sheet": s.in_current_sheet,
                                "disclosure_id": s.disclosure_id,
                            }
                            for s in states
                        ],
                    },
                    ensure_ascii=False,
                )
            )
        else:
            typer.echo(f"{holder_name} - {len(states)} issuer pair(s)")
            typer.echo("")
            typer.echo(f"{'Issuer':<46} {'ISIN':<14} {'Pos%':>6}  {'Date':<12} {'Cur':<4}")
            for s in states:
                typer.echo(
                    f"{s.issuer_name[:44]:<46} {s.isin:<14} {s.position_pct!s:>6}  "
                    f"{s.position_date.isoformat():<12} {'yes' if s.in_current_sheet else '-':<4}"
                )
    except ShortsEsError as exc:
        _err(exc)
    finally:
        conn.close()


# ------------------------------------------------------------------- changes


@app.command()
def changes(
    since: str = typer.Option(
        ..., "--since", help="YYYY-MM-DD: disclosures first observed on/after this date."
    ),
) -> None:
    """Disclosures first observed since a date (observation time)."""
    conn = _conn()
    try:
        d = temporal.parse_effective_date(since)
        rows = repo.disclosures_first_observed_since(conn, d.isoformat())
        typer.echo(f"{len(rows)} disclosures first observed since {d.isoformat()}")
        typer.echo("")
        typer.echo(f"{'First seen':<26} {'ISIN':<14} {'Date':<12} {'Pos%':>6}  Holder")
        for r in rows:
            typer.echo(
                f"{r['first_observed_at']:<26} {r['isin']:<14} {r['position_date']:<12} "
                f"{r['position_pct']:>6}  {r['holder_name'][:50]}"
            )
    except ShortsEsError as exc:
        _err(exc)
    finally:
        conn.close()


# --------------------------------------------------------------------- as-of


@app.command(name="as-of")
def as_of(
    identifier: str = typer.Argument(..., help="ISIN, LEI or issuer name."),
    effective_at: str | None = typer.Option(
        None, "--effective-at", help="Regulatory date YYYY-MM-DD."
    ),
    known_at: str | None = typer.Option(None, "--known-at", help="Knowledge cutoff ISO-8601."),
    json_out: bool = typer.Option(False, "--json"),
) -> None:
    """Reconstruct published state as of a date / knowledge cutoff.

    --effective-at: latest disclosure with position_date <= D.
    --known-at: only disclosures first observed on/before T.
    """
    conn = _conn()
    try:
        refs = identifiers.resolve_issuers(conn, identifier)
        eff = temporal.parse_effective_date(effective_at) if effective_at else None
        kn = temporal.parse_known_at(known_at) if known_at else None
        _knowledge_guard(conn, kn)
        for ref in refs:
            states = reconstruction.issuer_states(conn, ref.isin, effective_at=eff, known_at=kn)
            open_states = [s for s in states if s.state == DisclosureState.PUBLIC_POSITION_OPEN]
            if json_out:
                typer.echo(
                    json.dumps(
                        {
                            "isin": ref.isin,
                            "issuer_name": ref.issuer_name,
                            "effective_at": eff.isoformat() if eff else None,
                            "known_at": temporal.iso_utc(kn) if kn else None,
                            "positions": [
                                {
                                    "holder_name": s.holder_name,
                                    "position_pct": str(s.position_pct),
                                    "position_date": s.position_date.isoformat(),
                                    "state": s.state.value,
                                    "disclosure_id": s.disclosure_id,
                                }
                                for s in states
                            ],
                        },
                        ensure_ascii=False,
                    )
                )
            else:
                bounds = []
                if eff:
                    bounds.append(f"effective_at={eff.isoformat()}")
                if kn:
                    bounds.append(f"known_at={temporal.iso_utc(kn)}")
                typer.echo(f"{ref.issuer_name} ({ref.isin})  [{', '.join(bounds) or 'latest'}]")
                typer.echo("")
                if not states:
                    typer.echo("No published disclosures in that context. (NO_DATA is not zero.)")
                for s in states:
                    typer.echo(
                        f"  {s.holder_name[:56]:<58} {s.position_pct!s:>6} %  "
                        f"@ {s.position_date.isoformat()}"
                    )
                typer.echo(
                    f"\nPublicly disclosed total: {sum(s.position_pct for s in open_states)} %"
                )
    except ShortsEsError as exc:
        _err(exc)
    finally:
        conn.close()


# ----------------------------------------------------------------- snapshots


@app.command()
def snapshots() -> None:
    """List recorded snapshots."""
    conn = _conn()
    try:
        rows = repo.list_snapshots(conn)
        if not rows:
            typer.echo("no snapshots - run 'shorts-es sync'")
            return
        typer.echo(f"{'Retrieved at':<26} {'SHA-256':<18} {'Status':<12} {'Published':<12} Rows")
        for r in rows:
            n = conn.execute(
                "SELECT COUNT(*) FROM snapshot_disclosure WHERE snapshot_sha256 = ?",
                (r["snapshot_sha256"],),
            ).fetchone()[0]
            typer.echo(
                f"{r['retrieved_at']:<26} {r['snapshot_sha256'][:16]:<18} "
                f"{r['status']:<12} {(r['publication_date'] or '-'):<12} {n}"
            )
    finally:
        conn.close()


# ---------------------------------------------------------------------- diff


@app.command()
def diff(
    snapshot_a: str = typer.Argument(..., help="SHA-256 (or prefix) of older snapshot."),
    snapshot_b: str = typer.Argument(..., help="SHA-256 (or prefix) of newer snapshot."),
) -> None:
    """Diff two observed snapshots (source diff + derived state changes)."""
    conn = _conn()
    try:
        d = diff_snapshots(conn, snapshot_a, snapshot_b)
        typer.echo(f"A: {d.sha_a}")
        typer.echo(f"B: {d.sha_b}")
        typer.echo("")
        typer.echo(f"Source diff: +{len(d.added_ids)} / -{len(d.removed_ids)} disclosure rows")
        typer.echo(f"State changes (latest-per-pair): {len(d.changes)}")
        typer.echo("")
        for c in d.changes:
            old = f"{c.old[1]} @ {c.old[0]}" if c.old else "-"
            new = f"{c.new[1]} @ {c.new[0]}" if c.new else "-"
            direction = f" ({c.direction})" if c.direction else ""
            typer.echo(
                f"  {c.kind:<8} {c.isin:<14} {c.holder_name[:36]:<38} "
                f"{old:>18} -> {new:<18}{direction}"
            )
    except ShortsEsError as exc:
        _err(exc)
    finally:
        conn.close()


# -------------------------------------------------------------------- source


@app.command()
def source(
    disclosure_id: str = typer.Argument(..., help="Disclosure ID (sha256 or prefix)."),
) -> None:
    """Full provenance chain for a disclosure."""
    conn = _conn()
    try:
        d = repo.get_disclosure(conn, disclosure_id)
        if d is None:
            # try prefix
            rows = conn.execute(
                "SELECT disclosure_id FROM disclosure WHERE disclosure_id LIKE ? LIMIT 2",
                (disclosure_id + "%",),
            ).fetchall()
            if len(rows) == 1:
                disclosure_id = rows[0][0]
                d = repo.get_disclosure(conn, disclosure_id)
        if d is None:
            raise NotFoundError(f"disclosure not found: {disclosure_id}")
        p = provenance_for(conn, disclosure_id)
        src = source_descriptor()
        typer.echo("Disclosure:")
        typer.echo(f"  id:            {p.disclosure_id}")
        typer.echo(f"  canonical:     {p.canonical_json}")
        typer.echo("")
        typer.echo("Source:")
        typer.echo(f"  authority:     {src['authority']}")
        typer.echo(f"  workbook:      {src['workbook']}")
        typer.echo("")
        typer.echo("Locations (snapshot / sheet / row):")
        for loc in p.locations:
            typer.echo(
                f"  {loc['snapshot_sha256'][:16]}  {loc['sheet_name']:<24} "
                f"row {loc['row_number']:<6} retrieved {loc['retrieved_at']}"
            )
        typer.echo("")
        typer.echo(f"First observed:  {p.first_observed_at}")
        typer.echo(f"Original source: {src['source_url']}")
    except ShortsEsError as exc:
        _err(exc)
    finally:
        conn.close()


# -------------------------------------------------------------------- verify


@app.command()
def verify(
    snapshot: str | None = typer.Argument(None, help="Snapshot sha256/prefix (default: latest)."),
    record: bool = typer.Option(True, "--record/--no-record", help="Store result in ledger."),
) -> None:
    """Reconstruct Current from Series and compare against the source."""
    conn = _conn()
    try:
        sha = snapshot or _latest_sha(conn)
        snap = repo.get_snapshot(conn, sha)
        if snap is None:
            raise NotFoundError(f"snapshot not found: {sha}")
        sha = snap["snapshot_sha256"]
        result = verification.verify_snapshot(conn, sha)
        logging.getLogger("shorts_es").info(
            "verification_%s snapshot=%s matched=%d",
            "pass" if result.passed else "fail",
            sha[:12],
            result.matched,
        )
        if record:
            repo.record_verification(
                conn,
                sha,
                "PASS" if result.passed else "FAIL",
                result.counts(),
                result.details(),
            )
        typer.echo("CNMV current-state verification")
        typer.echo("")
        typer.echo("Source snapshot:")
        typer.echo(f"  sha256: {result.snapshot_sha256}")
        typer.echo("")
        typer.echo(f"Reconstructed states: {result.pairs_checked}")
        typer.echo(f"Source current states: {len(repo.current_sheet_pairs(conn, sha))}")
        typer.echo("")
        typer.echo(f"Exact matches:        {result.matched}")
        typer.echo(f"Missing:              {len(result.missing)}")
        typer.echo(f"Unexpected:           {len(result.unexpected)}")
        typer.echo(f"Conflicts:            {len(result.conflicts)}")
        typer.echo("")
        typer.echo(f"VERIFICATION: {'PASS' if result.passed else 'FAIL'}")
        if not result.passed:
            for group, items in (
                ("missing", result.missing),
                ("unexpected", result.unexpected),
                ("conflict", result.conflicts),
            ):
                for p in items[:10]:
                    typer.echo(
                        f"  {group}: {p.isin} {p.holder_name} "
                        f"expected={p.expected} actual={p.actual}"
                    )
            raise typer.Exit(code=1)
    except ShortsEsError as exc:
        _err(exc)
    finally:
        conn.close()


# -------------------------------------------------------------- dataset-info


@app.command(name="dataset-info")
def dataset_info() -> None:
    """Summary of the local dataset."""
    conn = _conn()
    try:
        stats = repo.dataset_stats(conn)
        latest = repo.latest_snapshot(conn)
        typer.echo("shorts-es dataset")
        typer.echo(f"  parser:          {constants.PARSER_VERSION}")
        typer.echo(f"  snapshots:       {stats['snapshots']}")
        typer.echo(f"  disclosures:     {stats['disclosures']}")
        typer.echo(f"  issuers (ISIN):  {stats['issuers']}")
        typer.echo(f"  issuers (LEI):   {stats['leis']}")
        typer.echo(f"  holders:         {stats['holders']}")
        typer.echo(f"  pairs:           {stats['pairs']}")
        typer.echo(f"  position dates:  {stats['earliest']} .. {stats['latest']}")
        if latest:
            typer.echo(f"  latest snapshot: {latest['snapshot_sha256']}")
            typer.echo(f"  retrieved_at:    {latest['retrieved_at']}")
            v = repo.latest_verification(conn, latest["snapshot_sha256"])
            typer.echo(f"  verification:    {v['result'] if v else 'not run'}")
        cfg = _config()
        typer.echo(f"  data dir:        {cfg.data_dir}")
    finally:
        conn.close()


# ----------------------------------------------------------------------- web


@app.command()
def web(
    host: str = typer.Option("127.0.0.1", "--host"),
    port: int = typer.Option(8000, "--port"),
) -> None:
    """Serve the read-only web explorer (API + HTML)."""
    import uvicorn

    from ..web.app import create_app

    cfg = _config()
    uvicorn.run(create_app(cfg), host=host, port=port)


def main() -> None:
    app()


if __name__ == "__main__":
    main()
