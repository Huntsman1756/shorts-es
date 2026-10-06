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

**Action:** Parser `cnmv-nsp-parser/1` established. Schema fingerprint:
`fb69b9f9c83be275e9cf6df215b44adf732383a3e400b1687f6f3a1b86302d2c`.
