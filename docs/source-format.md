# Source format: `NetShortPositions.xls` (CNMV)

Established by direct byte-level inspection on 2026-10-06 (gate G0). Every
claim here was verified against the real file, not inferred from names.

## Transport

- URL: `https://internet.cnmv.es/DocPortal/Posiciones-Cortas/NetShortPositions.xls`
- Method: plain `GET`, no authentication, no cookies.
- Observed response headers: `content-type: application/vnd.ms-excel`,
  `content-length`, `etag`, `last-modified`.
- Reference page: `https://www.cnmv.es/Portal/consultas/busqueda?id=29`

## Container

- Real OLE2 / Compound File (`d0cf11e0 a1b11ae1` magic) containing a BIFF8
  workbook (`xlrd` reports `biff_version = 80`, `datemode = 0`,
  `codepage = 1200` UTF-16LE).
- It is **not** SpreadsheetML, HTML or CSV disguised as `.xls`.
- Parsed with `xlrd`. No `pandas`, no LibreOffice.

## Sheet inventory (snapshot `6d9ea43b…`)

| # | Name | Rows | Cols | Role |
|---|------|------|------|------|
| 0 | `Fecha_-_Date` | 4 | 2 | metadata: publication date |
| 1 | `Última_-_Current` | 67 | 6 | latest disclosure per active pair |
| 2 | `Serie_-_Series` | 1590 | 6 | full notification series of listed pairs |
| 3 | `Anteriores_-_Previous` | 13098 | 6 | historical archive, all pairs incl. closed |
| 4–9 | `Hoja2`…`Hoja7` | 0 | 0 | empty |

The `Ú` in `Última` is stored as U+00DA; console display may mangle it but
the decoded sheet name is exact.

### Metadata sheet

Cells `(1,1)='Fecha de Publicación'`, `(2,1)='Date of publication'`,
`(3,1)=' YYYY-MM-DD '` — the publication date is a **text** cell with
surrounding spaces.

## Data-sheet layout

- Rows 1–3 (indexes 0–2): empty filler.
- Row 4 (index 3): headers, exact text:

| Col | Header |
|-----|--------|
| 0 | `LEI` |
| 1 | `ISIN` |
| 2 | `Emisor / Issuer` |
| 3 | `Tenedor de la Posición / Position holder` |
| 4 | `Fecha posición / Position date` |
| 5 | `Posición corta (%) / Net short position (%)` |

- Data rows from index 4; no gaps, no subtotals.

## Cell types and values

| Column | Cell type | Content |
|--------|-----------|---------|
| LEI | text | 20-char `[A-Z0-9]` LEI, always valid |
| ISIN | text | 12-char ISIN; **case-typo variants exist** (`eS0118594417`, `es0132945017`, `ES0113860a34`, `ES0178430e18`). Normalized to upper case on ingest; the raw bytes keep the typo. |
| Issuer | text | legal name, e.g. `ACCIONA, S.A.` |
| Holder | text | legal name; unicode names present (`Caisse de dépôt et placement du Québec`, `ZÜRCHER KANTONALBANK`, `BPI Gestão de Ativos…`) |
| Position date | **text** | ` YYYY-MM-DD ` with surrounding spaces; every cell parses strictly as ISO-8601 |
| Position (%) | number | IEEE-754 double, `General` format; shortest `repr` is the published value |

### Percentage facts (all verified)

- Range observed: `0.00` – `4.49`.
- Up to **3 decimal places** (`0.599`, `0.492`, `2.547`, `0.007`).
- **Values below 0.5 % are published** — including the Current sheet
  (e.g. `0.49`, `0.46` dated 2026-10-05/02). CNMV publishes all notified
  values; the 0.5 % figure is a *regulatory trigger*, not a data boundary.
- `0.00` appears only in Previous, always as the **latest row of its pair**
  (93 instances): an explicit closing notification.
- No negative values.
- **Unit semantics (audited 2026-10-06):** every numeric cell in all
  data sheets uses the `General` number format, so the displayed value
  is the stored value verbatim — `0.007` really is 0,007 %. The parser
  requires `General` on the pct column and fails closed on any other
  format, since a real percent format would decouple stored vs
  displayed semantics.

## Sheet semantics (verified by cross-sheet analysis)

- `Última_-_Current` ⊆ `Serie_-_Series`, exactly: every Current row also
  appears in Series, one row per `(LEI, ISIN, holder)` pair, and it is the
  pair's latest-dated row. Reconstructing *latest-per-pair* from Series
  reproduces Current **exactly** (63/63 in the reference snapshot).
- `Serie_-_Series` contains the complete notification series of every pair
  listed in Current, in contiguous blocks sorted by date descending.
- `Anteriores_-_Previous` is the archive: all pairs including ones that no
  longer have a current entry. It **overlaps** Series (479 shared rows) and
  contains **1 949 duplicated physical rows** (same pair/date/value on
  several rows). Duplicates are a source quirk; they collapse to one
  canonical disclosure and keep multiple provenance rows.
- Two distinct termination mechanisms exist and are kept apart:
  explicit `0.00` closing notifications (always pair-terminal, 93 found)
  and silent exits — 661 pairs leave publication **without** any closing
  notification. The latter are `PUBLIC_POSITION_NO_LONGER_CURRENT`,
  never "closed".
- Union of the three sheets: **12 252 unique canonical disclosures**;
  90 ISINs, 80 LEIs, 228 holders, 817 pairs.
- Two pairs appear in Series only under case-typo ISINs and merge into
  Current pairs after ISIN normalization.
- Scope is not ES-only: at least one `GB` ISIN appears (HBX Group
  International PLC) — CNMV lists instruments under its competence.
- No `(pair, date)` has two different values anywhere in the workbook:
  published corrections are new rows, not conflicting cells.

## Normalization applied on ingest (and only this)

- Strip surrounding whitespace on all text fields.
- `isin.upper()`.
- `Decimal(str(cell_value))` for percentages (exact shortest repr).
- `position_date` parsed from the padded ISO text.
- Everything else is preserved verbatim in the canonical JSON.

## Known limitations

- We cannot tell *when* a historical row was first published; the workbook
  carries no publication timestamp per row. See
  `docs/temporal-semantics.md`.
- `Fecha posición` is the position (effective) date; the workbook itself
  names it `Position date`.
