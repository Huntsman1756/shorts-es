# Reconstruction

How shorts-es turns published rows into answers. Every rule here is
verified against the real workbook (see `docs/source-format.md`).

## Units

- **Disclosure**: one published notification — `(LEI, ISIN, issuer, holder,
  position_date, position_pct)`. Canonical identity is the SHA-256 of its
  canonical JSON; identical content is identical regardless of where or
  when it appeared.
- **Pair**: `(LEI, ISIN, holder)` — a holder's disclosed position history
  on one security. ISIN is normalized to upper case because the source
  contains case-typo variants of the same security.

## The single rule

> Within a pair, the disclosure with the greatest `position_date` defines
> the published state.

No thresholds, no inference. Verified properties of the source:

- No `(pair, position_date)` carries two different values — ties do not
  occur in practice.
- `Última_-_Current` is exactly *latest-per-pair* over `Serie_-_Series`;
  reconstruction reproduces it 63/63 in the reference snapshot.
- `0.00` values only ever appear as a pair's latest row (closing
  notification).

## Derived states

| Latest published value / membership | State |
|-------------------------------------|-------|
| `pct > 0` and in Current sheet | `PUBLIC_POSITION_OPEN` |
| `pct = 0` (explicit closing notification) | `PUBLIC_POSITION_CLOSED_EXPLICITLY` |
| `pct > 0` but absent from Current sheet | `PUBLIC_POSITION_NO_LONGER_CURRENT` |
| no disclosure for the identifier | `NO_DATA` |

`above_public_threshold = pct >= 0.5` is reported separately and is *not*
part of the state — CNMV publishes sub-0.5 % values and they are real,
published positions. See `methodology` for why.

Pairs with history but no Current-sheet entry are "no longer published":
we show their last published value and never claim they are closed.

## Verification (`shorts-es verify`)

The executable check:

```
Series rows
  → group by (lei, isin, holder)
  → latest by position_date
  → compare against Current sheet rows
  → matched / missing / unexpected / conflicts
```

- **missing**: pair in Current but absent from Series.
- **unexpected**: pair in Series but absent from Current.
- **conflict**: same pair, different latest (date or value).

Reference snapshot: 63 pairs checked, 63 exact matches, PASS.

## Diff between snapshots

Two levels, reported separately:

- **Source diff**: disclosure rows added/removed between the snapshots
  (physical difference in published content).
- **State diff**: for each pair, `(old latest) -> (new latest)`,
  classified `ADDED` / `REMOVED` / `CHANGED` with direction
  `INCREASED` / `DECREASED` / `SAME_VALUE`. These are factual comparisons
  of published values, not regulatory event labels — a publication of a
  new value is not proof of when the trade happened.

## Worked example (real data, snapshot 6d9ea43b)

`AQR Capital Management, LLC` / `ES0118594417`:

- Series contains 66 notifications (descending): `2026-10-02 1.49`,
  `2026-09-25 1.58`, … `2015-01-06 0.61`, gap, `2014-12-23 0.55`
  (published under the typo'd `eS0118594417`), `2014-12-17 0.60`, …
- Latest = `2026-10-02 1.49` → equals the Current row. Pair state:
  `PUBLIC_POSITION_OPEN`, `above_public_threshold = true`.

`Marshall Wace LLP` / `ES0125220311` (hypothetical, matching the AKO
pattern in real data): latest = `2021-02-19 0.00` → `PUBLIC_POSITION_CLOSED_EXPLICITLY`
— an explicit closing notification, distinct from a pair that merely
disappeared (`PUBLIC_POSITION_NO_LONGER_CURRENT`).
