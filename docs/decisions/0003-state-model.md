# ADR 0003 — State model: no threshold inference, no closure inference

## Status

Accepted (2026-10-06).

## Context

CNMV publishes all notified values, including sub-0.5 % (which appear even
in the Current sheet) and explicit 0.00 % closings. 661 pairs leave
publication without any closing notification.

## Decision

- `PUBLIC_POSITION_OPEN` = latest published pct > 0 — regardless of the
  0.5 % threshold, which is reported separately as
  `above_public_threshold`.
- `PUBLIC_POSITION_ZERO` = latest published pct = 0 (explicit closing).
- A pair that disappears without a closing row is "no longer published" —
  we report its last published value and never infer closure.
- `NO_DATA` when an identifier resolves to nothing.

## Consequences

- The 0.5 % regulatory trigger is documented context, not a data filter.
- We never convert absence into a position claim. These rules cannot be
  "improved" by heuristics later without a spec change.
