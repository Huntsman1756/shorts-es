# Provenance

Every answer shorts-es produces can be walked back to CNMV bytes:

```
answer
  → derived state (latest-per-pair projection)
  → disclosure       sha256 of canonical JSON
  → row              (sheet, 1-based row number)
  → sheet            Última / Serie / Anteriores
  → snapshot         sha256 of raw workbook bytes
  → HTTP metadata    retrieved_at, etag, last_modified, content_length
  → source URL       https://internet.cnmv.es/DocPortal/Posiciones-Cortas/NetShortPositions.xls
```

## Disclosure identity

`disclosure_id = sha256(canonical_json)` where the canonical JSON is
`{lei, isin, issuer_name, holder_name, position_date, position_pct}` —
sorted keys, UTF-8, no whitespace. Identity depends only on published
content:

- independent of `observed_at` (knowledge time never enters identity);
- independent of sheet or row position;
- independent of snapshot (the same content re-published keeps its id).

Normalization applied before hashing: whitespace stripping, ISIN upper
case, `Decimal` canonical percentage rendering. Everything else is
verbatim.

## Row-level provenance

`snapshot_disclosure` records each physical location where a disclosure
appeared. The source itself duplicates rows in `Anteriores_-_Previous`
(1 949 instances in the reference snapshot): one disclosure, several
locations — all preserved.

## Example

```
$ shorts-es source e7cce0b5fdf7

Disclosure:
  id:        e7cce0b5fdf73ea304be87c4125960f7ba9c080c48aa719062e823642dd21a18
  canonical: {"holder_name":"BlackRock Investment Management (UK) Limited",
              "isin":"ES0125220311","issuer_name":"ACCIONA, S.A.",
              "lei":"54930002KP75TLLLNO21",
              "position_date":"2026-08-04","position_pct":"0.62"}

Locations:
  6d9ea43b460bca3c  Última_-_Current   row 5   retrieved 2026-10-06T20:25Z
  6d9ea43b460bca3c  Serie_-_Series     row 5   retrieved 2026-10-06T20:25Z
```

## Snapshot manifest

`data/reference-snapshots.jsonl` (repo) and `$SHORTS_ES_DATA_DIR/snapshots.jsonl`
(local) record, per snapshot: sha256, retrieved_at, source_url, size,
etag, last_modified, publication_date, parser_version,
schema_fingerprint and per-sheet row counts. Raw bytes are not
redistributed (see `DATA-NOTICE.md`).

## Verifying independently

1. Download the workbook from CNMV.
2. `sha256sum NetShortPositions.xls` — compare with the manifest.
3. `shorts-es sync --file NetShortPositions.xls` — parse into a fresh
   data dir.
4. `shorts-es verify` — reconstruct Current from Series; expect PASS.
5. `shorts-es source <disclosure_id>` — trace any number to its row.
