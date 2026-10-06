# ADR 0003 — State model: two distinct termination mechanisms

## Status

Accepted (2026-10-06, revised after the percentage/termination audit).

## Context

CNMV publishes all notified values, including sub-0.5 % (which appear even
in the Current sheet) and explicit 0.00 % closings. **661 pairs leave
publication without any closing notification** — silent exits are at least
as common as explicit closes.

## Decision

- `PUBLIC_POSITION_OPEN` = latest published pct > 0 and the pair appears
  in the snapshot's Current sheet. The 0.5 % threshold is reported
  separately as `above_public_threshold`, never used to filter.
- `PUBLIC_POSITION_CLOSED_EXPLICITLY` = latest published pct = 0
  (verified: every `0.00` in the archive terminates its pair's series —
  an explicit closing notification).
- `PUBLIC_POSITION_NO_LONGER_CURRENT` = the pair has published history
  (last known value > 0) but no entry in the snapshot's Current sheet.
  Absence of disclosure is **not** evidence the position is zero.
- `NO_PUBLIC_DISCLOSURE` / `NO_DATA` as before.

`PUBLIC_POSITION_BELOW_THRESHOLD` was dropped: nothing in the source lets
us claim a below-threshold *state*; a published <0.5 % position is simply
a published position, and `above_public_threshold` records the fact.

## Consequences

- The two termination mechanisms are never conflated: `0.00` closes, and
  silent exits stay visibly unresolved.
- We never convert absence into a position claim. These rules cannot be
  "improved" by heuristics later without a spec change.
