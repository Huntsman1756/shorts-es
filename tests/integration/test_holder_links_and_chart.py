"""Regresiones de dos fallos reportados por el usuario:

1. Los enlaces a la ficha de un titular daban 404: la plantilla codificaba el
   nombre con `urlencode` (estilo cadena de consulta), que convierte los espacios
   en `+`. En un segmento de ruta el `+` es un carácter literal, así que
   `/holder/Marshall+Wace+LLP` no resolvía nada. Ahora se usa `pathquote` (`%20`)
   y el backend además tolera los enlaces antiguos con `+`.
2. El gráfico SVG llevaba los colores incrustados (pensados para tema claro):
   en modo oscuro la línea y las etiquetas quedaban con muy poco contraste. Los
   colores se resuelven ahora por CSS con variables de tema.
"""

from __future__ import annotations

import re
from pathlib import Path
from urllib.parse import quote

import pytest
from fastapi.testclient import TestClient

from shorts_es.web.app import create_app
from shorts_es.web.routes import svg_line_chart

CSS = Path(__file__).resolve().parents[2] / "src" / "shorts_es" / "web" / "static" / "style.css"


@pytest.fixture()
def client(synced):
    return TestClient(create_app(synced[0]))


def _holders(client) -> list[str]:
    return [h["holder_name"] for h in client.get("/api/v1/holders").json()["holders"]]


def test_todos_los_titulares_abren_con_url_codificada(client):
    nombres = _holders(client)
    assert len(nombres) > 1
    for nombre in nombres:
        r = client.get(f"/holder/{quote(nombre, safe='')}")
        assert r.status_code == 200, f"{nombre} -> {r.status_code}"


def test_enlaces_antiguos_con_mas_tambien_abren(client):
    """`/holder/Marshall+Wace+LLP` (el enlace que el usuario pegó) debe resolver."""
    for nombre in _holders(client):
        con_mas = quote(nombre.replace(" ", "+"), safe="+")
        r = client.get(f"/holder/{con_mas}")
        assert r.status_code == 200, f"{nombre} -> {r.status_code}"


def test_los_enlaces_de_la_lista_de_titulares_resuelven(client):
    """End-to-end: cada href de /holders se pide y debe dar 200."""
    html = client.get("/holders").text
    hrefs = sorted(set(re.findall(r'href="(/holder/[^"]+)"', html)))
    assert hrefs, "la lista no tiene enlaces a titulares"
    for href in hrefs:
        r = client.get(href)
        assert r.status_code == 200, f"{href} -> {r.status_code}"


def test_ninguna_plantilla_codifica_rutas_con_urlencode():
    """`urlencode` (con `+`) solo vale para cadenas de consulta, no para rutas."""
    plantillas = (Path(__file__).resolve().parents[2] / "src/shorts_es/web/templates")
    for ruta in plantillas.glob("*.html"):
        texto = ruta.read_text(encoding="utf-8")
        assert "holder_name | urlencode" not in texto, f"{ruta.name}: usar pathquote"
        assert "pathquote" not in texto or "/holder/" in texto or "/issuer/" in texto


def test_el_grafico_no_lleva_colores_incrustados():
    filas = [
        {"position_date": "2024-01-01", "position_pct": "1.00%"},
        {"position_date": "2024-02-01", "position_pct": "2.00%"},
        {"position_date": "2024-03-01", "position_pct": "1.50%"},
    ]
    svg = str(svg_line_chart(filas, "2.00"))
    assert 'class="chart-line"' in svg
    assert 'class="chart-label"' in svg
    assert not re.search(r'(fill|stroke)="#[0-9a-fA-F]{3,6}"', svg), (
        "los colores deben venir del CSS (variables de tema), no del SVG"
    )


def test_el_css_tiene_variables_de_grafico_en_claro_y_oscuro():
    css = CSS.read_text(encoding="utf-8")
    for variable in ("--chart-line", "--chart-grid", "--chart-label", "--chart-value"):
        assert css.count(f"{variable}:") == 2, f"{variable} debe definirse en claro y oscuro"
    oscuro = css.split("@media (prefers-color-scheme: dark)")[1]
    assert "--chart-line:" in oscuro
    for clase in (".chart-line", ".chart-dot", ".chart-label", ".chart-value"):
        assert clase in css


def test_el_grafico_no_amontona_etiquetas():
    """Con muchas fechas no puede haber una etiqueta por punto: era ilegible."""
    from shorts_es.web.routes import _puntos_destacados

    # dataset largo con dientes de sierra: solo deben sobrevivir los extremos claros
    valores = [1.0 + (0.001 if i % 2 else 0) for i in range(200)]
    valores[100] = 9.0   # un pico que sí importa
    valores[150] = 0.2   # un valle que sí importa
    elegidos = _puntos_destacados(valores)
    assert len(elegidos) <= 12
    assert elegidos == sorted(elegidos)
    assert 199 in elegidos, "el valor vigente (último) debe ir marcado"
    assert 100 in elegidos and 150 in elegidos

    filas = [
        {"position_date": f"2024-01-{d:02d}", "position_pct": f"{v:.2f}%"}
        for d, v in zip(range(1, 29), [1.0 + (i % 5) * 0.3 for i in range(28)])
    ]
    svg = str(svg_line_chart(filas, "1.00"))
    assert svg.count('class="chart-dot"') <= 12
    assert svg.count('class="chart-value"') <= 12
    # la polilínea debe llevar todos los puntos y en sintaxis válida de <polyline>
    puntos = re.search(r'<polyline points="([^"]+)"', svg).group(1)
    pares = puntos.split(" ")
    assert len(pares) == 28, "la línea debe seguir todos los puntos"
    assert not re.search(r"[A-Za-z]", puntos), (
        "las coordenadas de <polyline> son pares 'x,y': con prefijos M/L el navegador no pinta nada"
    )
    for par in pares:
        x, y = par.split(",")
        float(x), float(y)


def test_grafico_corto_marca_todos_los_puntos():
    from shorts_es.web.routes import _puntos_destacados

    assert _puntos_destacados([1.0, 2.0, 3.0]) == [0, 1, 2]
    assert _puntos_destacados([]) == []
