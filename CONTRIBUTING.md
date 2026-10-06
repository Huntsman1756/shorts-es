# Contributing

## Ground rules

1. **Source prevails.** No derived feature may weaken provenance,
   reproducibility or temporal semantics.
2. **Determinism.** Same bytes → same result. No clocks, randomness or
   network in parser/domain code.
3. **Fail closed.** Unexpected source structure is `SCHEMA_DRIFT`, never
   a best-effort parse.
4. **`Decimal`, never `float`, for percentages.**
5. **Deterministic correctness path.** Parsing, canonicalization and
   state reconstruction must remain deterministic; probabilistic
   inference is not permitted anywhere in
   `source → parse → canonical → reconstruction`.
6. Keep it small: SQLite, stdlib-first, no new dependencies without an
   articulated reason in docs/.

## Setup

```bash
uv sync
uv run pytest          # offline suite (synthetic fixtures, no network)
uv run ruff check src tests
uv run ruff format --check src tests
```

## Testing philosophy

- Invariants over coverage: determinism, identity stability, idempotent
  ingestion, temporal honesty, provenance completeness.
- Synthetic workbooks are built with `xlwt` in `tests/fixtures/builder.py`
  mirroring the CNMV layout — no binary fixtures in the repo.
- Golden cases (`tests/golden/golden_rows.jsonl`) are hand-verified
  canonical rows from the real publication.
- Live-source checks are marked `@pytest.mark.live` and never run by
  default or in CI's main job.

## Source changes

If CNMV changes the workbook, `sync` fails with `SCHEMA_DRIFT`. The
process is: inspect the new file, document the change in
`docs/source-changelog.md`, update `source/schema.py` + parser, bump
`PARSER_VERSION`, add regression tests.

## Commits

Small, semantic commits — `feat:`, `fix:`, `docs:`, `test:`,
`refactor:`, `ci:`, `chore:`. The why, not the what.
