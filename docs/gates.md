# Gates — v0.1.0 evidence

Status of every release gate, with where the evidence lives.

## G0 — Source ✅

| Check | Evidence |
|-------|----------|
| Source downloadable automatically | `sync` over HTTPS verified end-to-end (CLI + Docker) |
| Real file type identified | OLE2/BIFF8 — `docs/source-format.md` |
| Sheets enumerated | 10 sheets incl. metadata + 6 empty — documented |
| Headers enumerated | exact 6 columns, row index 3 |
| Cell types understood | 5 text cols + 1 numeric; dates are *text* |
| Dates understood | padded ` YYYY-MM-DD ` text, all parse |
| Percentages understood | `General`-format doubles, exact `repr`, 0–3 decimals |
| LEI confirmed | column 0, all 20-char valid |
| ISIN confirmed | column 1, valid after case normalization |
| Issuer/holder confirmed | columns 2/3 |
| Current semantics | latest-per-pair, ⊆ Series — verified 63/63 |
| Series semantics | complete series of currently-listed pairs |
| Previous semantics | archive incl. closed pairs; duplicated rows |
| ≥20 golden rows | `tests/golden/golden_rows.jsonl` (23 cases) |

## G1 — Reproducibility ✅

Raw SHA-256 addressed snapshots; deterministic parser
(`tests/unit/test_parser.py`); stable content ids (Hypothesis);
schema fingerprint `fb69b9f9…` recorded; second sync → `NO_CHANGE`;
manifest `data/snapshots.jsonl`; provenance chain to row level.

## G2 — Semantics ✅

Disclosure model, current + historical reconstruction, `--effective-at`,
`--known-at` with `INSUFFICIENT_KNOWLEDGE_HISTORY`, `NO_DATA`/`OPEN`/`ZERO`
states, below-threshold semantics documented (ADR 0003), Series→Current
reconciliation PASS.

## G3 — Product ✅

All 12 CLI commands; FastAPI `/api/v1` read-only with OpenAPI
(`/docs`); HTML explorer (search, issuer, holder, snapshots, snapshot,
disclosure, changes, methodology).

## G4 — QA ✅

77 tests offline (unit + golden + integration), determinism, temporal,
schema-drift, provenance, Hypothesis properties; live test marked and
excluded by default; separate `live-source` workflow.

## G5 — Release ✅

Wheel builds with web assets; `uv tool install` verified; Docker image
syncs + serves (verified); compose stack verified (web + sync job +
Caddy); docs complete; MIT license.
