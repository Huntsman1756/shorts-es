shorts-es
=========

Reproducible, auditable access to CNMV public net short-position disclosures.

```bash
uv tool install shorts-es
shorts-es sync
shorts-es current ES0125220311
```

```
ACCIONA, S.A. (ES0125220311)

Currently published (source Current sheet):
Holder                                                           Pos%  Date         ID
BlackRock Investment Management (UK) Limited                     0.62  2026-08-04   e7cce0b5fdf7
AQR Capital Management, LLC                                      0.49  2026-10-05   eb9072c50823

Publicly disclosed total: 1.11 %
(Sum of publicly disclosed individual positions. Not total short interest.)
```

> **Publicly disclosed positions are not total short interest.** And the
> absence of a disclosure is not evidence that no position exists.

## Why

Spain's CNMV publishes `NetShortPositions.xls` — the public registry of net
short positions — as a downloadable workbook. shorts-es is the
**executable verification layer** on top of it:

- Every snapshot is stored immutably, addressed by the **SHA-256** of its
  raw bytes.
- A deterministic parser produces **canonical disclosures** with
  content-addressed identities.
- Every answer traces back: `answer → disclosure → row → sheet → snapshot
  → sha256 → source URL`.
- `shorts-es verify` **reconstructs the Current sheet from the Series
  sheet** and diffs them — the same check anyone can rerun.

It is not a dashboard, not short-interest data, not a signal. It is the
layer that lets a third party check how a result was obtained.

## Install

Python ≥3.12, managed with [uv](https://docs.astral.sh/uv/):

```bash
uv tool install shorts-es        # as a tool
# or, from a clone:
uv sync && uv run shorts-es --help
```

Data lives outside the repo: `$SHORTS_ES_DATA_DIR`, else the platform
default (`~/.local/share/shorts-es`, `%LOCALAPPDATA%\shorts-es`, …).

## CLI

```bash
shorts-es sync                          # fetch + snapshot + parse + ingest
shorts-es verify                        # Series → reconstruct → compare Current
shorts-es current ES0125220311          # latest published positions (ISIN/LEI/name)
shorts-es history ES0125220311          # full published disclosure history
shorts-es holder "Marshall Wace LLP"    # a holder's positions across issuers
shorts-es changes --since 2026-10-01    # disclosures first observed since
shorts-es as-of ES0125220311 --effective-at 2026-06-30
shorts-es as-of ES0125220311 --known-at 2026-10-05T12:00:00+02:00
shorts-es snapshots                     # immutable snapshot log
shorts-es diff <sha-A> <sha-B>          # source diff + state changes
shorts-es source <disclosure-id>        # full provenance chain
shorts-es dataset-info
shorts-es web                           # serve the explorer on :8000
```

## Temporal model

Two clocks, never conflated:

- **`position_date`** — effective/regulatory time: what the source says
  the position was.
- **`first_observed_at`** — knowledge time: when *we* first saw it.

Rows present in our first snapshot are `RECONSTRUCTED_HISTORICAL`: they
existed in that publication, but we cannot claim they were public on their
position date. `--known-at` before the first snapshot errors with
`INSUFFICIENT_KNOWLEDGE_HISTORY` rather than inventing a past.

## Verification

```
$ shorts-es verify
CNMV current-state verification

Source snapshot:
  sha256: 6d9ea43b460bca3cb321018bd4da6b5e0708105a8e1d5505bac5fb8435cba5e9

Reconstructed states: 63
Source current states: 63

Exact matches:        63
Missing:               0
Unexpected:            0
Conflicts:             0

VERIFICATION: PASS
```

Schema drift (changed sheets/columns) fails closed: the raw snapshot is
kept, ingestion aborts, the event lands in the ledger and
`SOURCE-CHANGELOG.md`.

## Web

`shorts-es web` serves a read-only explorer + JSON API (`/api/v1/*`) —
search, issuer, holder, snapshot, disclosure-provenance and methodology
pages. For deployment, `docker compose up -d` runs the app behind Caddy
with automatic HTTPS (`DOMAIN=your.host` in env).

## Methodology, in one breath

CNMV publishes **all** notified net-short values — including below the
0.5 % public-disclosure threshold and explicit 0.00 % closings. We store
them verbatim (`Decimal`, no rounding). State = the latest publication per
(LEI, ISIN, holder) pair; verification independently reconstructs it. The
archive sheet duplicates rows — they collapse to one disclosure and keep
multiple provenance rows. See `docs/`.

## Known limitations

- No per-row publication timestamps exist in the source; knowledge before
  our first snapshot is unknowable.
- A pair leaving the Current sheet without a closing notification is
  reported as "no longer published" — never as zero.
- The source contains ISIN case-typo variants; normalized on ingest.
- Scope is whatever CNMV publishes (not ES-ISIN-only).
- The raw workbook is not redistributed (CNMV terms); the repo carries a
  manifest of hashes — see `DATA-NOTICE.md`.

## Docs

`ARCHITECTURE.md` · `PROVENANCE.md` · `DATA-NOTICE.md` ·
`SOURCE-CHANGELOG.md` · `docs/source-format.md` ·
`docs/temporal-semantics.md` · `docs/reconstruction.md` · `ROADMAP.md`

MIT licensed (software only — data per CNMV terms).
