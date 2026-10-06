# ADR 0001 — Source contract: Current is authoritative, Series reconstructs it

## Status

Accepted (2026-10-06).

## Context

The workbook ships three data sheets whose generative process is
CNMV-internal. We needed to decide which sheet is the source of truth for
"currently published" and whether reconstruction can be verified.

## Decision

- `Última_-_Current` is the authoritative published current-state table —
  we never try to improve on it.
- `Serie_-_Series` is the complete notification history of every pair
  listed in Current. `Anteriores_-_Previous` is the full archive.
- Verification = reconstruct *latest-per-pair* from Series and diff against
  Current. Verified exact (63/63) on the reference snapshot.
- Union of all sheets (deduplicated) is the disclosure corpus.

## Consequences

- `verify` is an independent recomputation check, not a tautology.
- If CNMV ever publishes Series pairs missing from Current, `verify`
  reports `unexpected` rather than guessing why.
- Pairs in Current but absent from Series (or vice versa) are visible
  anomalies, not silent corrections.
