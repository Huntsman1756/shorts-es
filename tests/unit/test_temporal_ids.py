"""Temporal parsing + identifier resolution tests."""

from datetime import UTC, date, datetime

import pytest

from shorts_es.domain import identifiers, temporal
from shorts_es.exceptions import (
    AmbiguousIdentifierError,
    NotFoundError,
    ParseError,
)


def test_parse_effective_date():
    assert temporal.parse_effective_date("2026-06-30") == date(2026, 6, 30)
    with pytest.raises(ParseError):
        temporal.parse_effective_date("30/06/2026")
    with pytest.raises(ParseError):
        temporal.parse_effective_date("2026-6-3")


def test_parse_known_at_naive_is_utc():
    dt = temporal.parse_known_at("2026-10-05T12:00:00")
    assert dt.tzinfo == UTC


def test_parse_known_at_offset_normalized():
    dt = temporal.parse_known_at("2026-10-05T12:00:00+02:00")
    assert dt == datetime(2026, 10, 5, 10, 0, tzinfo=UTC)


def test_resolve_isin_exact(conn):
    refs = identifiers.resolve_issuers(conn, "es0125220311")  # case-insensitive
    assert len(refs) == 1
    assert refs[0].isin == "ES0125220311"


def test_resolve_lei_expands_isins(conn):
    refs = identifiers.resolve_issuers(conn, "959800R7QMXKF0NFMT29")
    assert {r.isin for r in refs} == {"ES0105046017", "ES0105046009"}


def test_resolve_name_exact(conn):
    refs = identifiers.resolve_issuers(conn, "acciona, s.a.")
    assert refs[0].isin == "ES0125220311"


def test_resolve_name_substring_unique(conn):
    refs = identifiers.resolve_issuers(conn, "FERROVIAL")
    assert refs[0].isin == "ES0118594417"


def test_resolve_name_ambiguous(conn):
    with pytest.raises(AmbiguousIdentifierError) as exc:
        identifiers.resolve_issuers(conn, "A")
    assert exc.value.candidates


def test_resolve_unknown_raises_not_found(conn):
    with pytest.raises(NotFoundError):
        identifiers.resolve_issuers(conn, "ZZZZZZZZZZZ9")


def test_resolve_holder_ambiguous(conn):
    # fixture has single AQR; craft ambiguity by querying a shared substring
    name = identifiers.resolve_holder(conn, "qube research")
    assert name == "Qube Research & Technologies Ltd"


def test_resolve_holder_not_found(conn):
    with pytest.raises(NotFoundError):
        identifiers.resolve_holder(conn, "Nonexistent Fund XYZ")
