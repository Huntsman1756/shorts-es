"""Property-based invariants (Hypothesis) for the canonical model."""

from datetime import date
from decimal import Decimal

from hypothesis import given, settings
from hypothesis import strategies as st

from shorts_es.parser.models import Disclosure

names = (
    st.text(
        alphabet=st.characters(whitelist_categories=("L", "N", "P", "Z")),
        min_size=1,
        max_size=60,
    )
    .map(str.strip)
    .filter(bool)
)


@settings(max_examples=200)
@given(
    lei=st.from_regex(r"[A-Z0-9]{20}", fullmatch=True),
    isin=st.from_regex(r"[A-Z]{2}[A-Z0-9]{9}[0-9]", fullmatch=True),
    issuer=names,
    holder=names,
    pct=st.decimals(min_value=0, max_value=99, places=3),
    d=st.dates(min_value=date(2000, 1, 1), max_value=date(2030, 12, 31)),
)
def test_disclosure_id_is_deterministic(lei, isin, issuer, holder, pct, d):
    a = Disclosure(lei, isin, issuer, holder, d, pct)
    b = Disclosure(lei, isin, issuer, holder, d, pct)
    assert a.disclosure_id == b.disclosure_id
    assert a.canonical_json() == b.canonical_json()
    assert len(a.disclosure_id) == 64


@settings(max_examples=200)
@given(pct=st.decimals(min_value=0, max_value=99, places=3))
def test_pct_roundtrip_is_exact(pct):
    d = Disclosure("A" * 20, "ES0000000000", "X", "Y", date(2020, 1, 1), pct)
    # canonical string round-trips to the same Decimal
    assert Decimal(d.pct_str) == pct


@settings(max_examples=100)
@given(
    isin=st.from_regex(r"[a-zA-Z]{2}[a-zA-Z0-9]{9}[0-9]", fullmatch=True),
    pct=st.decimals(min_value=0, max_value=99, places=2),
)
def test_isin_case_does_not_change_identity(isin, pct):
    a = Disclosure("A" * 20, isin.upper(), "X", "Y", date(2020, 1, 1), pct)
    b = Disclosure("A" * 20, isin.lower().upper(), "X", "Y", date(2020, 1, 1), pct)
    assert a.disclosure_id == b.disclosure_id
