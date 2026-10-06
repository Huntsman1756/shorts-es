"""Derived-state vocabulary.

These are projections over published facts, never inferences beyond the data:

- ``PUBLIC_POSITION_OPEN``: the latest known disclosure for the pair
  published a non-zero net short position. CNMV publishes all notified
  values, so an open state does NOT imply the position is above the 0.5%
  mandatory public-disclosure threshold.
- ``PUBLIC_POSITION_ZERO``: the latest known disclosure published 0.00%.
- ``NO_PUBLIC_DISCLOSURE``: the issuer exists in the dataset but the pair /
  context has no published disclosure.
- ``NO_DATA``: the identifier does not resolve to anything observed.
"""

from __future__ import annotations

from enum import StrEnum


class DisclosureState(StrEnum):
    PUBLIC_POSITION_OPEN = "PUBLIC_POSITION_OPEN"
    PUBLIC_POSITION_ZERO = "PUBLIC_POSITION_ZERO"
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
