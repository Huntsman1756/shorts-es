# shorts-es

**An executable verification layer for CNMV public net short-position
disclosures.**

[![CI](https://github.com/Huntsman1756/shorts-es/actions/workflows/ci.yml/badge.svg)](https://github.com/Huntsman1756/shorts-es/actions/workflows/ci.yml)
![Python 3.12+](https://img.shields.io/badge/python-3.12+-blue)
[![License: MIT](https://img.shields.io/badge/license-MIT-green)](LICENSE)

```text
CNMV Series
     ↓
deterministic reconstruction
     ↓
63 current positions reconstructed
     ↓
63/63 exact matches against CNMV Current
```

`shorts-es` fetches the official CNMV registry workbook, stores immutable
byte-level snapshots addressed by SHA-256, parses them deterministically,
and lets anyone recompute — not just query — every published result.

> **Publicly disclosed positions are not total short interest.** And the
> absence of a disclosure is not evidence that no position exists.

## Quick start

Python ≥3.12, managed with [uv](https://docs.astral.sh/uv/):

```bash
# until the PyPI package is published:
uv tool install git+https://github.com/Huntsman1756/shorts-es.git
# or from a clone: uv sync && uv run shorts-es --help

shorts-es sync                      # fetch + snapshot + parse + ingest
shorts-es verify                    # reconstruct + reconcile vs source
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

Data lives outside the repo: `$SHORTS_ES_DATA_DIR`, else the platform
default (`~/.local/share/shorts-es`, `%LOCALAPPDATA%\shorts-es`, …).

## What it guarantees

- Every raw snapshot is stored immutably, addressed by the SHA-256 of
  its bytes — the source is never overwritten or edited.
- Parsing is deterministic and fail-closed: unexpected workbook
  structure is `SCHEMA_DRIFT`, not a best-effort parse.
- Percentages are `Decimal` — never floats, never rounded. Audited:
  all pct cells use Excel `General` format, so stored == displayed.
- Every answer traces back: `answer → disclosure → row → sheet →
  snapshot → sha256 → source URL`.
- Two clocks, never conflated: `position_date` (regulatory time) vs
  `first_observed_at` (when we saw it). `--known-at` before the first
  snapshot errors with `INSUFFICIENT_KNOWLEDGE_HISTORY` rather than
  inventing a past.
- Termination is honest: explicit `0.00` closings vs silent exits
  (`PUBLIC_POSITION_NO_LONGER_CURRENT`) are never conflated.

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

## Web

`shorts-es web` serves a read-only explorer + JSON API (`/api/v1/*`) —
search, issuer/holder rankings, snapshot, disclosure-provenance and
methodology pages. `docker compose up -d` runs it behind Caddy with
automatic HTTPS (`DOMAIN=your.host`).

## Data semantics and limitations

- The CNMV workbook contains published net-short values below 0.5 %, as
  well as explicit 0.00 % terminal records — all stored verbatim.
- A pair leaving the Current sheet without a closing notification is
  reported as "no longer current" — never as zero.
- The source contains ISIN case-typo variants; normalized on ingest.
- Scope is whatever CNMV publishes (not ES-ISIN-only).
- The raw workbook is not redistributed (CNMV terms); the repo carries a
  reference manifest of hashes — see `DATA-NOTICE.md`.

## Documentation

`docs/architecture.md` · `docs/provenance.md` · `docs/source-format.md` ·
`docs/reconstruction.md` · `docs/temporal-semantics.md` ·
`docs/source-changelog.md` · `docs/deployment.md`

## Related projects

Other projects make public short disclosures easier to consume;
`shorts-es` focuses on making the Spanish CNMV register reproducible and
independently verifiable:

- [w3stling/blankningsregistret](https://github.com/w3stling/blankningsregistret)
  — OSS wrapper over the Swedish FI registry (query, not verification).
- [nebmit/assets](https://github.com/nebmit/assets) — snapshot-validated
  German Bundesanzeiger ingestion; closest in spirit.
- [QuiVad](https://www.quivad.com) — multi-market aggregator with a clean
  methodology/moves view.
- [ShortRegister](https://shortregister.com) — European disclosure
  explorer with a CNMV-based Spain page.

## License

MIT for the software (see `LICENSE`). CNMV data remains subject to CNMV
terms (see `DATA-NOTICE.md`).
