# Roadmap

Ideas explicitly **out of scope for v0.1** — recorded so they are not lost,
not so they get built now.

- Watchlists / alerting on position changes.
- Holder-position history chart on issuer pages.
- Other competent-authority sources (BaFin, AFM, CONSOB, FCA…) — each one
  is a distinct source contract deserving the same treatment; only
  consider after v0.1 has proven itself on CNMV.
- Publication-time inference from multi-snapshot observation (estimating
  when CNMV first published a row as our observation history grows).
- Data export formats (CSV/Parquet) of the canonical disclosure set.
- Per-pair "publication presence" timelines once enough snapshots have
  accumulated.
- Packaged Docker image publishing to a registry.
