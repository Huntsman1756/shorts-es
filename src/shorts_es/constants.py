"""Project-wide constants describing the CNMV source contract.

Everything in this module is a verified fact about the published workbook,
established during source inspection (G0). If the source changes shape the
schema fingerprint changes and ingestion fails closed.
"""

SOURCE_URL = "https://internet.cnmv.es/DocPortal/Posiciones-Cortas/NetShortPositions.xls"
SOURCE_PAGE_URL = "https://www.cnmv.es/Portal/consultas/busqueda?id=29"
SOURCE_AUTHORITY = "CNMV"
SOURCE_WORKBOOK_NAME = "NetShortPositions.xls"

# Parser contract version. Bump when parsing semantics change.
PARSER_VERSION = "cnmv-nsp-parser/1"

# OLE2 / Compound File Binary magic (real BIFF .xls container).
OLE2_MAGIC = bytes.fromhex("d0cf11e0a1b11ae1")

# Workbook sheet names, in published order. Sheet names are stored in the
# workbook with a mojibake-prone 'Ú' (0xDA); xlrd decodes them to unicode.
SHEET_METADATA = "Fecha_-_Date"
SHEET_CURRENT = "Última_-_Current"
SHEET_SERIES = "Serie_-_Series"
SHEET_PREVIOUS = "Anteriores_-_Previous"

DATA_SHEETS = (SHEET_CURRENT, SHEET_SERIES, SHEET_PREVIOUS)

# Rows above the header are blank filler published by the source.
HEADER_ROW_INDEX = 3

# Exact published headers, column order is part of the contract.
COL_LEI = "LEI"
COL_ISIN = "ISIN"
COL_ISSUER = "Emisor / Issuer"
COL_HOLDER = "Tenedor de la Posición / Position holder"
COL_DATE = "Fecha posición / Position date"
COL_PCT = "Posición corta (%) / Net short position (%)"

EXPECTED_HEADERS = (COL_LEI, COL_ISIN, COL_ISSUER, COL_HOLDER, COL_DATE, COL_PCT)

# Public-disclosure threshold under Regulation (EU) 236/2012 (SSR). This is a
# regulatory trigger, not a property of the data: CNMV publishes all notified
# positions including values below 0.5%.
PUBLIC_DISCLOSURE_THRESHOLD = "0.5"

ENV_DATA_DIR = "SHORTS_ES_DATA_DIR"

APP_NAME = "shorts-es"
DB_FILENAME = "shorts-es.db"
SNAPSHOTS_DIRNAME = "snapshots"
MANIFEST_FILENAME = "snapshots.jsonl"
