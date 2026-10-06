# Source changelog

Human-audited log of every observed change in the CNMV source workbook
structure or semantics. Automated schema drift is detected by the schema
fingerprint and fails closed; entries here record what changed, its impact
and the parser version that handles it.

## 2026-10-06

**Snapshot:** `6d9ea43b460bca3cb321018bd4da6b5e0708105a8e1d5505bac5fb8435cba5e9`
(1 690 624 bytes, retrieved 2026-10-06)

**Observed change:** Initial known schema. Established by byte-level
inspection (G0).

**Sheets:** `Fecha_-_Date`, `Última_-_Current`, `Serie_-_Series`,
`Anteriores_-_Previous`, plus empty `Hoja2`–`Hoja7`.

**Columns (data sheets):** `LEI`, `ISIN`, `Emisor / Issuer`,
`Tenedor de la Posición / Position holder`,
`Fecha posición / Position date`, `Posición corta (%) / Net short position (%)`

**Rows:** Current 63, Series 1 586, Previous 13 094 (12 252 unique canonical
disclosures; Previous contains duplicated physical rows).

**Action:** Parser `cnmv-nsp-parser/2` established (v2 adds the
percentage-format contract and semantic/physical fingerprint split after
the percentage-unit audit). Semantic schema fingerprint:
`69f30558cf65a7d29ef5b95870ba9642d3ad0eebc618936798dd3448b44da6ef`.
Physical fingerprint:
`c800aecbea27d44279f502596372528f079476e0995b9dba018b167239facef1`.
