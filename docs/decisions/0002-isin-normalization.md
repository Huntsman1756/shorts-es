# ADR 0002 — ISIN normalized to upper case for identity

## Status

Accepted (2026-10-06).

## Context

The source contains case-typo ISIN variants (`eS0118594417`,
`es0132945017`, `ES0113860a34`, `ES0178430e18`). With raw-case keys, two
pairs in Series appeared to have no Current entry; after upper-casing,
Series pairs and Current pairs coincide exactly (63/63).

## Decision

`isin.upper()` is part of canonicalization — before hashing and before
pairing. ISIN case carries no semantics; the typo'd bytes remain in the
immutable snapshot.

## Consequences

- A typo fix by CNMV does not create phantom disclosures or pair splits.
- Identity covers the *disclosed fact*, not the spreadsheet's typo.
- Documented in `docs/source-format.md` and `methodology`.
