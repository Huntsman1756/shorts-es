# Audit — percentage unit semantics (2026-10-06)

**Question audited:** could the stored values like `0.007`, `0.49` or
`4.49` be a different *displayed* percentage due to an Excel number
format (e.g. a `0.00%` format that displays `0.007` as `0,70 %`)?

**Method:** opened the reference snapshot with `formatting_info=True`
(xlrd) and enumerated, for *every* data cell in all three data sheets,
the cell type and the effective Excel number format. Then traced a
hand-picked set of cells through `raw value → number format → displayed
value → canonical Decimal`.

## Result: all 14 743 rows × 6 columns use format `General`

| Sheet | pct cells checked | ctypes | formats |
|-------|------------------|--------|---------|
| `Última_-_Current` | 63 | all numeric | `General` only |
| `Serie_-_Series` | 1 586 | all numeric | `General` only |
| `Anteriores_-_Previous` | 13 094 | all numeric | `General` only |

`General` displays the stored IEEE-754 double as-is (shortest
representation). There is **no scaling, no percent format, no hidden
unit** anywhere in the workbook: the stored number *is* the published
percentage (`0.007` = 0,007 %, `4.49` = 4,49 %).

## Cell-level audit table

| Sheet | Row | Raw value | ctype | Format | Displayed | Canonical | Match |
|---|---|---|---|---|---|---|---|
| Última_-_Current | 5 | 0.62 | number | General | 0.62 | 0.62 | YES |
| Última_-_Current | 6 | 0.49 | number | General | 0.49 | 0.49 | YES |
| Última_-_Current | 7 | 0.51 | number | General | 0.51 | 0.51 | YES |
| Última_-_Current | 48 | 0.46 | number | General | 0.46 | 0.46 | YES |
| Última_-_Current | 60 | 0.49 | number | General | 0.49 | 0.49 | YES |
| Última_-_Current | 9 | 0.6 | number | General | 0.6 | 0.6 | YES |
| Última_-_Current | 11 | 0.5 | number | General | 0.5 | 0.5 | YES |
| Última_-_Current | 12 | 0.92 | number | General | 0.92 | 0.92 | YES |
| Serie_-_Series | 9 | 1.0 | number | General | 1.0 | 1 | YES |
| Serie_-_Series | 111 | 1.49 | number | General | 1.49 | 1.49 | YES |
| Serie_-_Series | 979 | 0.599 | number | General | 0.599 | 0.599 | YES |
| Anteriores_-_Previous | 5 | 0.0 | number | General | 0.0 | 0 | YES |
| Anteriores_-_Previous | 6 | 0.55 | number | General | 0.55 | 0.55 | YES |
| Anteriores_-_Previous | 143 | 0.492 | number | General | 0.492 | 0.492 | YES |
| Anteriores_-_Previous | 2698 | 0.01 | number | General | 0.01 | 0.01 | YES |
| Anteriores_-_Previous | 5773 | 0.02 | number | General | 0.02 | 0.02 | YES |
| Anteriores_-_Previous | 11039 | 4.49 | number | General | 4.49 | 4.49 | YES |
| Anteriores_-_Previous | 9890 | 0.007 | number | General | 0.007 | 0.007 | YES |
| Anteriores_-_Previous | 385 | 0.237 | number | General | 0.237 | 0.237 | YES |

**19/19 sampled cells: `displayed CNMV value == canonical shorts-es value`.**

## Conclusion

Sub-0.5 % values (incl. `0.007` and `0.46/0.49` in the Current sheet) are
*real published percentages*, not artifacts of a percent number format.
CNMV publishes all notified net short positions, not only those above the
0.5 % public-disclosure trigger.

## Contract enforcement (parser v2)

To make this audit a permanent invariant rather than a one-off check:

- `inspect_workbook` collects the set of number formats used by the
  percentage column of each data sheet (requires `formatting_info=True`).
- `validate_schema` requires **exactly `("General",)`**; any other
  format → `SCHEMA_DRIFT` (fail closed), because a non-General format
  could decouple stored value from displayed semantics.
- The pct-format set is part of the *semantic* schema fingerprint.
