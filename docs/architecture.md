# Architecture

```
                   CNMV
                    │
                    ▼
         NetShortPositions.xls          (OLE2/BIFF8)
                    │
                    ▼
              FETCH LAYER               source/fetch.py
        raw bytes + HTTP metadata       (httpx, timeouts, headers)
                    │
                    ▼
            IMMUTABLE SNAPSHOT          source/snapshot.py
        SHA-256 content-addressed       snapshots/<sha>.xls
                    │
                    ▼
             XLS INSPECTOR              source/inspect.py
          schema fingerprint            (sheets, headers, types)
                    │  validate ──► SCHEMA_DRIFT = fail closed
                    ▼
          DETERMINISTIC PARSER          parser/ (xlrd, Decimal, strict)
             canonical disclosures      content-addressed ids
                    │
                    ▼
              SQLite ledger             storage/ (stdlib sqlite3, WAL)
        snapshots · sheets · disclosures · provenance
                    │
                    ▼
              DOMAIN CORE               domain/ (pure projections)
        reconstruction · temporal · verify · diff · identifiers
              /                \
            ▼                  ▼
          CLI (Typer)      FastAPI + Jinja  (read-only)
```

## Data flow

```
source → snapshot → parse → canonical representation
       → deterministic projection → interfaces
```

The web layer never contains logic: every endpoint calls the same domain
functions the CLI calls.

## Components

| Layer | Module | Responsibility |
|-------|--------|----------------|
| Fetch | `source/fetch.py` | Download bytes + capture HTTP provenance |
| Snapshot | `source/snapshot.py` | Immutable, content-addressed raw storage |
| Inspect | `source/inspect.py` | Sheet inventory + semantic & physical schema fingerprints |
| Schema | `source/schema.py` | Contract validation, fail closed |
| Parse | `parser/` | BIFF rows → canonical `Disclosure` (Decimal, strict types) |
| Store | `storage/` | SQLite ledger; idempotent ingest; provenance bridge |
| Domain | `domain/` | latest-per-pair, temporal bounds, verify, diff, identity |
| CLI | `cli/main.py` | sync + queries |
| Web | `web/` | `/api/v1` JSON + server-rendered HTML explorer |

## Storage layout

```
$SHORTS_ES_DATA_DIR (platform default: XDG/AppData)
├── shorts-es.db            SQLite ledger (WAL)
├── snapshots/<sha256>.xls  raw bytes, immutable
└── snapshots.jsonl         append-only runtime snapshot manifest
# repo also ships data/reference-snapshots.jsonl (release-tied refs only)
```

## Tables

- `snapshot` — one row per distinct source publication (keyed by sha256).
- `snapshot_sheet` — per-sheet inventory per snapshot.
- `disclosure` — canonical rows; `first_observed_at` = knowledge time.
- `snapshot_disclosure` — physical provenance: which `(snapshot, sheet,
  row)` carried each disclosure (a disclosure may appear on several rows
  and sheets).
- `verification` — recorded results of `shorts-es verify`.

## Invariants

- Same bytes → same parse → same disclosure ids (determinism).
- Re-ingesting the same snapshot writes nothing new (idempotence).
- Schema drift aborts ingestion but still records the raw snapshot + the
  drifted fingerprint (auditability).
- Historical snapshots are never overwritten (immutability).
- No float arithmetic on percentages (Decimal throughout).

## Failure model (fail closed)

`SOURCE_UNAVAILABLE` · `UNSUPPORTED_WORKBOOK` · `SCHEMA_DRIFT` ·
`PARSE_ERROR` · `AMBIGUOUS_IDENTIFIER` · `NOT_FOUND` · `MISSING_SNAPSHOT` ·
`INSUFFICIENT_KNOWLEDGE_HISTORY` · `VERIFICATION_FAILED` · `NO_DATA`
