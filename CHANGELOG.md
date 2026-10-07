# Changelog

## [0.1.2] — 2026-10-06

### Changed

- Security upgrades: `fastapi>=0.142` (starlette 1.7) and dev `pytest` 9,
  addressing published advisories. No functional changes.

## [0.1.1] — 2026-10-06

Superseded by 0.1.2 within the same day; no GitHub release was cut for it.

### Fixed

- `sync`: retry transient drops from the CNMV endpoint in `fetch_source`.

### Changed

- Consolidated public documentation: pruned internal process scaffolding
  (decision records, gates, ROADMAP); operational contracts remain in
  `docs/source-format.md`, `docs/source-changelog.md` and `DATA-NOTICE.md`.
- Packaging metadata and project URLs updated for the repository layout.

## [0.1.0] — 2026-10-06

Initial release.

### Added

- `shorts-es sync`: fetch the CNMV `NetShortPositions.xls` workbook into
  immutable, SHA-256-addressed snapshots with full HTTP provenance;
  `--file` for offline ingest.
- Deterministic BIFF8 parser (`cnmv-nsp-parser/2`) producing canonical
  disclosures with content-addressed ids; `Decimal` percentages; ISIN
  case normalization.
- Schema fingerprinting with fail-closed `SCHEMA_DRIFT` detection.
- SQLite ledger (snapshots, sheets, disclosures, row-level provenance,
  verification results) with idempotent ingestion.
- Temporal model separating `position_date` (effective) from
  `first_observed_at` (knowledge); `RECONSTRUCTED_HISTORICAL` vs
  `OBSERVED_CURRENT` classes; `INSUFFICIENT_KNOWLEDGE_HISTORY` guard.
- CLI: `sync`, `current`, `history`, `holder`, `changes`, `as-of`,
  `snapshots`, `diff`, `source`, `verify`, `dataset-info`, `web`.
- `verify`: reconstructs the Current sheet from Series and diffs —
  PASS (63/63) on the reference snapshot.
- Read-only FastAPI under `/api/v1` + sober HTML explorer (search,
  issuer, holder, snapshot, disclosure provenance, methodology pages).
- Dockerfile + compose (web + Caddy TLS) with `/data` persistence.
- CI: offline lint/test/build; separate scheduled live-source check.

### Data notes

- First known schema established from snapshot
  `6d9ea43b460bca3cb321018bd4da6b5e0708105a8e1d5505bac5fb8435cba5e9`
  (2026-10-06). See `docs/source-changelog.md` and `docs/source-format.md`.
