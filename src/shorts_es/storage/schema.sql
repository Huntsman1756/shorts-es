-- shorts-es storage schema (v1)
-- Immutable snapshots + canonical disclosures + per-row provenance.

CREATE TABLE IF NOT EXISTS snapshot (
    snapshot_sha256   TEXT PRIMARY KEY,
    retrieved_at      TEXT NOT NULL,            -- ISO-8601 UTC, when WE fetched it
    source_url        TEXT NOT NULL,
    http_status       INTEGER,
    content_type      TEXT,
    content_length    INTEGER,
    etag              TEXT,
    last_modified     TEXT,
    publication_date  TEXT,                     -- declared by the workbook itself
    parser_version    TEXT NOT NULL,
    schema_fingerprint TEXT NOT NULL,
    physical_fingerprint TEXT,                    -- audit-only, added in schema v2
    status            TEXT NOT NULL,            -- parsed | schema_drift | parse_error
    raw_path          TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS snapshot_sheet (
    snapshot_sha256 TEXT NOT NULL REFERENCES snapshot (snapshot_sha256),
    sheet_name      TEXT NOT NULL,
    sheet_order     INTEGER NOT NULL,
    row_count       INTEGER NOT NULL,
    col_count       INTEGER NOT NULL,
    PRIMARY KEY (snapshot_sha256, sheet_name)
);

CREATE TABLE IF NOT EXISTS disclosure (
    disclosure_id        TEXT PRIMARY KEY,      -- sha256 of canonical JSON
    lei                  TEXT NOT NULL,
    isin                 TEXT NOT NULL,         -- normalized upper-case
    issuer_name          TEXT NOT NULL,
    holder_name          TEXT NOT NULL,
    position_date        TEXT NOT NULL,         -- YYYY-MM-DD (regulatory/effective date)
    position_pct         TEXT NOT NULL,         -- canonical decimal string
    canonical_json       TEXT NOT NULL,
    first_observed_at    TEXT NOT NULL,         -- knowledge-time: earliest sighting
    first_snapshot_sha256 TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_disclosure_isin   ON disclosure (isin);
CREATE INDEX IF NOT EXISTS idx_disclosure_lei    ON disclosure (lei);
CREATE INDEX IF NOT EXISTS idx_disclosure_holder ON disclosure (holder_name);
CREATE INDEX IF NOT EXISTS idx_disclosure_date   ON disclosure (position_date);
CREATE INDEX IF NOT EXISTS idx_disclosure_first_seen ON disclosure (first_observed_at);

-- Which physical rows carried each disclosure in each snapshot.
-- The same disclosure can appear on multiple rows (source duplicates) and
-- multiple sheets (Current also appears in Series).
CREATE TABLE IF NOT EXISTS snapshot_disclosure (
    snapshot_sha256 TEXT NOT NULL REFERENCES snapshot (snapshot_sha256),
    disclosure_id   TEXT NOT NULL REFERENCES disclosure (disclosure_id),
    sheet_name      TEXT NOT NULL,
    row_number      INTEGER NOT NULL,           -- 1-based workbook row
    PRIMARY KEY (snapshot_sha256, sheet_name, row_number)
);

CREATE INDEX IF NOT EXISTS idx_sd_disclosure ON snapshot_disclosure (disclosure_id);
CREATE INDEX IF NOT EXISTS idx_sd_sheet ON snapshot_disclosure (snapshot_sha256, sheet_name);

CREATE TABLE IF NOT EXISTS verification (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    snapshot_sha256 TEXT NOT NULL REFERENCES snapshot (snapshot_sha256),
    verified_at     TEXT NOT NULL,
    result          TEXT NOT NULL,              -- PASS | FAIL
    pairs_checked   INTEGER NOT NULL,
    matched         INTEGER NOT NULL,
    missing         INTEGER NOT NULL,
    unexpected      INTEGER NOT NULL,
    conflicts       INTEGER NOT NULL,
    details_json    TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS meta (
    key   TEXT PRIMARY KEY,
    value TEXT NOT NULL
);
