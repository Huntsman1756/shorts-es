"""Regresiones de presentación pedidas por el usuario:

1. Toda tabla que muestra una columna "Fecha de posición" va en orden
   cronológico descendente (lo más reciente primero), sea cual sea la entidad.
2. El modo tarjeta de móvil (≤768px) se apoya en la clase `.table-row-cards`:
   la cabecera de la tabla debe ocultarse y la tabla debe dejar de comportarse
   como tabla, porque era la cabecera la que fijaba el ancho de las columnas y
   obligaba a desplazarse en horizontal.
"""

from __future__ import annotations

from pathlib import Path

from shorts_es.domain import reconstruction
from shorts_es.storage import repository as repo

CSS = Path(__file__).resolve().parents[2] / "src" / "shorts_es" / "web" / "static" / "style.css"
TEMPLATES = Path(__file__).resolve().parents[2] / "src" / "shorts_es" / "web" / "templates"


def _fechas_descendentes(fechas: list[str]) -> bool:
    return all(fechas[i - 1] >= fechas[i] for i in range(1, len(fechas)))


def test_historial_de_emisor_en_orden_cronologico(conn):
    isins = [r[0] for r in conn.execute("SELECT DISTINCT isin FROM disclosure")]
    assert isins, "el fixture debe traer datos"
    for isin in isins:
        fechas = [r["position_date"] for r in repo.disclosures_for_issuer(conn, isin)]
        assert _fechas_descendentes(fechas), f"{isin}: {fechas}"


def test_historial_de_titular_en_orden_cronologico(conn):
    holders = [r[0] for r in conn.execute("SELECT DISTINCT holder_name FROM disclosure")]
    for holder in holders:
        fechas = [r["position_date"] for r in repo.disclosures_for_holder(conn, holder)]
        assert _fechas_descendentes(fechas), f"{holder}: {fechas}"


def test_estados_de_emisor_en_orden_cronologico(conn):
    isins = [r[0] for r in conn.execute("SELECT DISTINCT isin FROM disclosure")]
    for isin in isins:
        estados = reconstruction.issuer_states(conn, isin)
        fechas = [s.position_date.isoformat() for s in estados]
        assert _fechas_descendentes(fechas), f"{isin}: {fechas}"


def test_estados_de_titular_en_orden_cronologico(conn):
    holders = [r[0] for r in conn.execute("SELECT DISTINCT holder_name FROM disclosure")]
    for holder in holders:
        estados = reconstruction.holder_states(conn, holder)
        fechas = [s.position_date.isoformat() for s in estados]
        assert _fechas_descendentes(fechas), f"{holder}: {fechas}"


def test_historial_de_pareja_en_orden_cronologico(conn):
    filas = conn.execute(
        "SELECT DISTINCT lei, isin, holder_name FROM disclosure LIMIT 20"
    ).fetchall()
    for lei, isin, holder in filas:
        fechas = [
            r["position_date"]
            for r in repo.resolve_pair_disclosures(conn, lei, isin, holder)
        ]
        assert _fechas_descendentes(fechas), f"{lei}/{isin}/{holder}: {fechas}"


def test_css_oculta_la_cabecera_en_modo_tarjeta():
    css = CSS.read_text(encoding="utf-8")
    assert ":has(.table-row-cards)" in css, "falta el modo tarjeta por tabla"
    assert ".compact-table:has(.table-row-cards) thead { display: none; }" in css, (
        "la cabecera debe ocultarse en móvil (si no, la tabla mide más que la pantalla)"
    )


def test_plantillas_incluyen_variante_tarjeta():
    """Toda tabla ancha va dentro de .table-wrap (para poder desplazarse dentro
    de su caja, nunca de la página) y las dos listas principales traen además la
    variante de tarjeta para móvil."""
    anchas = []
    for ruta in sorted(TEMPLATES.glob("*.html")):
        html = ruta.read_text(encoding="utf-8")
        if "compact-table" not in html:
            continue
        anchas.append(ruta.name)
        assert "table-wrap" in html, f"{ruta.name}: tabla sin .table-wrap"
    assert anchas, "no se encontró ninguna tabla ancha"

    for nombre in ("issuers.html", "holders.html", "index.html", "issuer.html", "holder.html"):
        html = (TEMPLATES / nombre).read_text(encoding="utf-8")
        assert "table-row-cards" in html, f"{nombre} no tiene filas de tarjeta"
