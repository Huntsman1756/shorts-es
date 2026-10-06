# Temporal semantics

Two clocks govern every answer shorts-es gives. Keeping them separate is
the core honesty guarantee of the project.

## Effective (regulatory) time — `position_date`

The `Fecha posición / Position date` column: the date the source
attributes to the position itself. Queries with `--effective-at D`
reconstruct "the latest publication on or before D" — that is, what the
record *says* the position was at D.

## Knowledge (observation) time — `first_observed_at`

The instant shorts-es first saw the disclosure, i.e. the retrieval time of
the earliest snapshot containing it. Queries with `--known-at T` restrict
the evidence to disclosures observed on or before T.

## The first snapshot is a boundary

Everything in the first sync (including rows with `position_date` years in
the past) shares one `first_observed_at`. Those rows are
`RECONSTRUCTED_HISTORICAL`:

- We know they existed in that publication.
- We do **not** know when CNMV first published them.
- We do **not** claim they were publicly visible on their position date.

Disclosures appearing in later snapshots are `OBSERVED_CURRENT` — we
observed them appear.

A `--known-at` earlier than the first snapshot is not an empty answer, it
is an error: `INSUFFICIENT_KNOWLEDGE_HISTORY`. Nothing was verifiably
known then.

## What we cannot reconstruct

- When a historical row was first published (the source has no per-row
  publication timestamp).
- When a pair left the published Current list before our first snapshot.
- Positions that exist but were never publicly disclosed.

## Worked example

Workbook synced on 2026-10-06 contains an AKO/Acciona notification of
0.00 % dated 2021-02-19.

| Query | Answer |
|-------|--------|
| `--effective-at 2021-03-01` | AKO/Acciona latest ≤ that date = 0.00 % |
| `--known-at 2021-03-01` | `INSUFFICIENT_KNOWLEDGE_HISTORY` — first snapshot is 2026-10-06 |
| `--effective-at 2021-03-01 --known-at 2026-10-06` | 0.00 %, provenance to the 2026-10-06 snapshot |

The last row is the honest statement: *as of the record we hold, the
published value for that date was 0.00 % — first observed by us on
2026-10-06.*
