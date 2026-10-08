"""Identifier resolution: user input -> issuer security / holder.

No fuzzy matching. ISINs and LEIs match exactly (case-insensitive). Names
match exact-then-substring; any ambiguity is an explicit error listing
candidates, never a silent pick.
"""

from __future__ import annotations

import re
import sqlite3
from dataclasses import dataclass

from ..exceptions import AmbiguousIdentifierError, NotFoundError
from ..storage import repository as repo

_ISIN = re.compile(r"^[A-Za-z]{2}[A-Za-z0-9]{9}[0-9]$")
_LEI = re.compile(r"^[A-Za-z0-9]{20}$")


@dataclass(frozen=True)
class IssuerRef:
    isin: str
    lei: str
    issuer_name: str


def _issuer_rows(conn: sqlite3.Connection, isin: str) -> IssuerRef | None:
    row = conn.execute(
        "SELECT isin, lei, issuer_name FROM disclosure WHERE isin = ? LIMIT 1",
        (isin,),
    ).fetchone()
    return IssuerRef(row["isin"], row["lei"], row["issuer_name"]) if row else None


def resolve_issuers(conn: sqlite3.Connection, identifier: str) -> list[IssuerRef]:
    """Resolve an identifier to one or more issuer securities.

    A LEI may map to several ISINs (one legal entity, several securities);
    that is not ambiguity, it is the structure of the data.
    """
    ident = identifier.strip()
    if not ident:
        raise NotFoundError("empty identifier")

    if _ISIN.match(ident):
        ref = _issuer_rows(conn, ident.upper())
        if ref is None:
            raise NotFoundError(f"no issuer found with ISIN {ident.upper()}")
        return [ref]

    if _LEI.match(ident):
        isins = repo.isins_for_lei(conn, ident.upper())
        if not isins:
            raise NotFoundError(f"no issuer found with LEI {ident.upper()}")
        return [r for i in isins if (r := _issuer_rows(conn, i)) is not None]

    # Exact issuer-name match (case-insensitive), then substring.
    exact = conn.execute(
        "SELECT DISTINCT isin, lei, issuer_name FROM disclosure "
        "WHERE issuer_name = ? COLLATE NOCASE ORDER BY issuer_name",
        (ident,),
    ).fetchall()
    if exact:
        return [IssuerRef(r["isin"], r["lei"], r["issuer_name"]) for r in exact]

    partial = repo.issuer_names_matching(conn, ident)
    if not partial:
        raise NotFoundError(f"no issuer matching {identifier!r}")
    if len(partial) > 1:
        candidates = [f"{r['issuer_name']} ({r['isin']})" for r in partial]
        raise AmbiguousIdentifierError(
            f"{identifier!r} matches {len(partial)} issuers", candidates=candidates
        )
    r = partial[0]
    return [IssuerRef(r["isin"], r["lei"], r["issuer_name"])]


def resolve_holder(conn: sqlite3.Connection, name: str) -> str:
    """Resolve a holder name to the exact published form.

    Acepta también enlaces antiguos con `+` en vez de `%20` (en una ruta el `+`
    es un carácter literal, así que esos enlaces no resolvían el nombre).
    """
    candidatos = [name.strip()]
    con_mas = name.replace("+", " ").strip()
    if con_mas not in candidatos:
        candidatos.append(con_mas)

    ultimo_error: Exception | None = None
    for ident in candidatos:
        try:
            return _resolve_holder_exacto(conn, ident)
        except NotFoundError as exc:
            ultimo_error = exc
    raise ultimo_error or NotFoundError(f"no holder matching {name!r}")


def _resolve_holder_exacto(conn: sqlite3.Connection, name: str) -> str:
    ident = name.strip()
    exact = conn.execute(
        "SELECT DISTINCT holder_name FROM disclosure " "WHERE holder_name = ? COLLATE NOCASE",
        (ident,),
    ).fetchall()
    if len(exact) == 1:
        return exact[0][0]
    partial = repo.holder_names_matching(conn, ident)
    if not partial:
        raise NotFoundError(f"no holder matching {name!r}")
    if len(partial) > 1:
        raise AmbiguousIdentifierError(
            f"{name!r} matches {len(partial)} holders", candidates=partial
        )
    return partial[0]
