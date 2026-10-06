# Data notice

## Source

All disclosure data in shorts-es derives from a single public file
published by the **Comisión Nacional del Mercado de Valores (CNMV)**:

- Workbook: `NetShortPositions.xls`
- URL: <https://internet.cnmv.es/DocPortal/Posiciones-Cortas/NetShortPositions.xls>
- Reference page: <https://www.cnmv.es/Portal/consultas/busqueda?id=29>
- Legal notice: <https://www.cnmv.es/portal/utilidades/notalegal.aspx>

## What shorts-es is (and is not)

shorts-es is an independent, open-source verification layer. It is **not**
an official CNMV product, and CNMV does not endorse it. The official
publication always prevails over anything this project computes or
displays.

## Reuse conditions

Per the CNMV legal notice, the site's contents are the exclusive property
of the CNMV and no general reuse licence is granted for them; information
is provided "a título informativo" and may be changed, suspended or
withdrawn without notice.

Consequently:

- **The raw workbook is not redistributed in this repository.** Every
  user downloads their own copy from CNMV via `shorts-es sync`, keeping a
  private, content-addressed snapshot on their machine.
- The repository publishes only **metadata** about snapshots
  (`data/snapshots.jsonl`): SHA-256, retrieval timestamps, sizes, row
  counts and schema fingerprints — sufficient for independent
  verification, not a copy of the data.
- Individual disclosure values (positions, dates, holders) are reported
  facts of public administrative record, quoted with full provenance.
- If the CNMV publishes explicit reuse terms in the future, this notice
  will be updated to match them.

## Corrections and errors

CNMV may change the file's structure or contents at any time. shorts-es
detects structural change via the schema fingerprint and **fails closed**
rather than parse under a stale contract; changes are logged in
`SOURCE-CHANGELOG.md`.

## No warranty

Data is provided as-is. Nothing here is investment advice. A publicly
disclosed net short position is not total short interest, and the absence
of a disclosure is not evidence that no position exists.
