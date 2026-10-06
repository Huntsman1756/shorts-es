"""Synthetic CNMV-layout workbook builder for tests.

Produces real OLE2/BIFF8 .xls bytes (via xlwt) matching the published
structure: metadata sheet, three data sheets with 3 blank rows + header at
index 3, plus empty Hoja sheets. Lets us exercise every parser path offline
and deterministically, including edge cases seen in production data.
"""

from __future__ import annotations

from io import BytesIO

import xlwt

from shorts_es import constants

HEADER = list(constants.EXPECTED_HEADERS)


def _write_metadata(wb: xlwt.Workbook, pub_date: str | None) -> None:
    sh = wb.add_sheet(constants.SHEET_METADATA)
    sh.write(1, 1, "Fecha de Publicación")
    sh.write(2, 1, "Date of publication")
    if pub_date:
        sh.write(3, 1, f" {pub_date} ")


def _write_data_sheet(
    wb: xlwt.Workbook, name: str, rows: list[tuple], blank_top: int = 3
) -> None:
    sh = wb.add_sheet(name)
    for c, h in enumerate(HEADER):
        sh.write(blank_top, c, h)
    for i, row in enumerate(rows):
        for c, v in enumerate(row):
            sh.write(blank_top + 1 + i, c, v)


def build_workbook(
    current: list[tuple] | None = None,
    series: list[tuple] | None = None,
    previous: list[tuple] | None = None,
    publication_date: str | None = "2026-10-06",
    extra_sheets: tuple[str, ...] = ("Hoja2", "Hoja3", "Hoja4", "Hoja5", "Hoja6", "Hoja7"),
) -> bytes:
    """Build workbook bytes. Row tuples are (lei, isin, issuer, holder,
    date_str, pct_float)."""
    wb = xlwt.Workbook()
    _write_metadata(wb, publication_date)
    _write_data_sheet(wb, constants.SHEET_CURRENT, current or [])
    _write_data_sheet(wb, constants.SHEET_SERIES, series or [])
    _write_data_sheet(wb, constants.SHEET_PREVIOUS, previous or [])
    for name in extra_sheets:
        wb.add_sheet(name)
    buf = BytesIO()
    wb.save(buf)
    return buf.getvalue()


def row(lei: str, isin: str, issuer: str, holder: str, date: str, pct: float) -> tuple:
    """Row using the source's text-date convention (padded ISO string)."""
    return (lei, isin, issuer, holder, f" {date} ", pct)


# Realistic values drawn from production data characteristics.
LEI_A = "54930002KP75TLLLNO21"      # ACCIONA
LEI_B = "959800R7QMXKF0NFMT29"      # AENA
LEI_C = "95980020140005308793"      # LEI with case-variant ISINs in source

ISIN_A = "ES0125220311"
ISIN_B = "ES0105046017"
ISIN_C = "ES0118594417"

ISSUER_A = "ACCIONA, S.A."
ISSUER_B = "AENA, S.M.E., S.A."
ISSUER_C = "FERROVIAL, S.A."

H_BLACKROCK = "BlackRock Investment Management (UK) Limited"
H_AQR = "AQR Capital Management, LLC"
H_MW = "Marshall Wace LLP"
H_UNICODE = "Caisse de dépôt et placement du Québec"

# Standard fixture dataset mirroring production edge cases:
# - a pair currently published below 0.5 (AQR/A 0.49)
# - ISIN case-typo variant inside a series (eS0118594417)
# - a terminal 0.00 closing notification (MW/A)
# - duplicated rows in the Previous sheet (Citadel)
# - unicode holder, 3-decimal pct, sub-0.1 and >4 values
SERIES_A = [
    row(LEI_A, ISIN_A, ISSUER_A, H_BLACKROCK, "2026-08-04", 0.62),
    row(LEI_A, ISIN_A, ISSUER_A, H_BLACKROCK, "2026-03-13", 0.78),
    row(LEI_A, ISIN_A, ISSUER_A, H_BLACKROCK, "2025-11-18", 1.0),
    row(LEI_A, ISIN_A, ISSUER_A, H_AQR, "2026-10-05", 0.49),
    row(LEI_A, ISIN_A, ISSUER_A, H_AQR, "2026-02-05", 1.44),
    row(LEI_A, ISIN_A, ISSUER_A, H_AQR, "2026-01-28", 1.32),
    row(LEI_B, ISIN_B, ISSUER_B, H_BLACKROCK, "2026-09-14", 0.51),
    row(LEI_B, ISIN_B, ISSUER_B, H_UNICODE, "2025-12-04", 0.72),
    row(LEI_C, ISIN_C, ISSUER_C, H_AQR, "2026-10-02", 1.49),
    row(LEI_C, ISIN_C, ISSUER_C, H_AQR, "2026-09-25", 1.58),
    # Case-typo ISIN inside the same pair's history (production quirk).
    row(LEI_C, "eS0118594417", ISSUER_C, H_AQR, "2014-12-23", 0.55),
]

CURRENT_A = [
    row(LEI_A, ISIN_A, ISSUER_A, H_BLACKROCK, "2026-08-04", 0.62),
    row(LEI_A, ISIN_A, ISSUER_A, H_AQR, "2026-10-05", 0.49),
    row(LEI_B, ISIN_B, ISSUER_B, H_BLACKROCK, "2026-09-14", 0.51),
    row(LEI_B, ISIN_B, ISSUER_B, H_UNICODE, "2025-12-04", 0.72),
    row(LEI_C, ISIN_C, ISSUER_C, H_AQR, "2026-10-02", 1.49),
]

PREVIOUS_A = [
    # A closed position: MW/A ends at 0.00 and never appears again.
    row(LEI_A, ISIN_A, ISSUER_A, H_MW, "2021-02-19", 0.0),
    row(LEI_A, ISIN_A, ISSUER_A, H_MW, "2021-02-18", 0.55),
    row(LEI_A, ISIN_A, ISSUER_A, H_MW, "2021-01-26", 0.66),
    # Disappeared without a zero notification.
    row(LEI_A, ISIN_A, ISSUER_A, "GLG Partners LP", "2012-07-19", 0.492),
    row(LEI_A, ISIN_A, ISSUER_A, "GLG Partners LP", "2012-05-25", 0.505),
    # Duplicated rows in the archive (production quirk).
    row(LEI_A, ISIN_A, ISSUER_A, "Citadel Advisors Europe Limited", "2025-06-06", 0.5),
    row(LEI_A, ISIN_A, ISSUER_A, "Citadel Advisors Europe Limited", "2025-06-06", 0.5),
    row(LEI_A, ISIN_A, ISSUER_A, "Citadel Advisors Europe Limited", "2025-05-28", 0.59),
    # Tiny and large values, 3 decimals, second ISIN of issuer B.
    row(LEI_B, "ES0105046009", ISSUER_B, H_AQR, "2021-06-09", 0.48),
    row(LEI_B, "ES0105046009", ISSUER_B, H_AQR, "2021-06-08", 0.5),
    row(LEI_B, ISIN_B, ISSUER_B, "Qube Research & Technologies Ltd", "2025-07-04", 0.02),
    row(LEI_B, ISIN_B, ISSUER_B, "JPMorgan Asset Management (UK) Limited", "2011-03-15", 0.599),
    row(LEI_B, ISIN_B, ISSUER_B, "JPMorgan Asset Management (UK) Limited", "2011-02-22", 0.609),
    row(LEI_C, ISIN_C, ISSUER_C, H_BLACKROCK, "2025-05-29", 4.49),
]
