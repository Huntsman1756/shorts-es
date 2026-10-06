"""Derived-state vocabulary.

These are projections over published facts, never inferences beyond the
data. Termination of a public position has *two* observable mechanisms in
the source, and they are reported separately:

- explicit closing notification: a `0.00` row ends the pair's series
  (verified: every `0.00` in the archive is its pair's latest row);
- silent exit: the pair simply stops appearing in the Current sheet
  (hundreds of real cases) — we report "no longer current", never
  "closed".

States:

- ``PUBLIC_POSITION_OPEN``: the latest known disclosure for the pair
  published a non-zero net short position AND the pair appears in the
  source's Current sheet. CNMV publishes all notified values, so open does
  NOT imply >= 0.5%.
- ``PUBLIC_POSITION_CLOSED_EXPLICITLY``: the latest known disclosure
  published 0.00% (an explicit closing notification).
- ``PUBLIC_POSITION_NO_LONGER_CURRENT``: the pair has published history
  (last known value > 0) but no entry in the snapshot's Current sheet.
  Absence of a disclosure is not evidence the position is zero.
- ``NO_PUBLIC_DISCLOSURE``: the issuer exists in the dataset but the pair /
  context has no published disclosure.
- ``NO_DATA``: the identifier does not resolve to anything observed.
"""

from __future__ import annotations

from enum import StrEnum


class DisclosureState(StrEnum):
    PUBLIC_POSITION_OPEN = "PUBLIC_POSITION_OPEN"
    PUBLIC_POSITION_CLOSED_EXPLICITLY = "PUBLIC_POSITION_CLOSED_EXPLICITLY"
    PUBLIC_POSITION_NO_LONGER_CURRENT = "PUBLIC_POSITION_NO_LONGER_CURRENT"
    NO_PUBLIC_DISCLOSURE = "NO_PUBLIC_DISCLOSURE"
    NO_DATA = "NO_DATA"


class HistoryClass(StrEnum):
    """Why a disclosure is in the ledger.

    ``OBSERVED_CURRENT``: first seen in a snapshot after our first sync.
    ``RECONSTRUCTED_HISTORICAL``: already present in the first snapshot we
    ever took; its position_date predates our observation and we make no
    claim about when CNMV first published it.
    """

    OBSERVED_CURRENT = "OBSERVED_CURRENT"
    RECONSTRUCTED_HISTORICAL = "RECONSTRUCTED_HISTORICAL"
