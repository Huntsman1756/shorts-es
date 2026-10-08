"""Web layer tests: API + HTML over the synced fixture dataset."""

import pytest
from fastapi.testclient import TestClient

from shorts_es.web.app import create_app


@pytest.fixture()
def client(synced):
    return TestClient(create_app(synced[0]))


def test_health(client):
    r = client.get("/api/v1/health")
    assert r.status_code == 200
    assert r.json()["status"] == "ok"


def test_dataset(client):
    r = client.get("/api/v1/dataset")
    d = r.json()
    assert d["parser_version"] == "cnmv-nsp-parser/2"
    assert d["stats"]["disclosures"] > 0
    assert d["latest_snapshot"]["snapshot_sha256"]


def test_current_by_isin(client):
    r = client.get("/api/v1/current/ES0125220311")
    assert r.status_code == 200
    d = r.json()
    assert d["issuers"][0]["isin"] == "ES0125220311"
    current = [p for p in d["issuers"][0]["positions"] if p["in_current_sheet"]]
    assert len(current) == 2


def test_current_unknown_identifier_404(client):
    r = client.get("/api/v1/current/ZZZZZZZZZZZ9")
    assert r.status_code == 404
    assert r.json()["error"] == "NOT_FOUND"


def test_holder_positions(client):
    r = client.get("/api/v1/holders/AQR Capital Management, LLC")
    assert r.status_code == 200
    positions = r.json()["positions"]
    assert any(p["in_current_sheet"] for p in positions)


def test_verify_endpoint(client):
    d = client.get("/api/v1/verify").json()
    assert d["result"] == "PASS"
    assert d["matched"] == d["pairs_checked"]


def test_snapshots_endpoint(client):
    snaps = client.get("/api/v1/snapshots").json()["snapshots"]
    assert len(snaps) == 1
    assert snaps[0]["parser_version"] == "cnmv-nsp-parser/2"


def test_disclosure_provenance_endpoint(client):
    cur = client.get("/api/v1/current/ES0125220311").json()
    did = cur["issuers"][0]["positions"][0]["disclosure_id"]
    d = client.get(f"/api/v1/disclosures/{did}").json()
    assert d["disclosure_id"] == did
    assert {loc["sheet_name"] for loc in d["locations"]} >= {"Serie_-_Series"}
    assert d["source"]["authority"] == "CNMV"


def test_changes_endpoint(client):
    d = client.get("/api/v1/changes?since=2026-01-01").json()
    assert d["count"] > 0


def test_html_pages(client):
    for path in ["/", "/snapshots", "/methodology"]:
        r = client.get(path)
        assert r.status_code == 200
        assert "shorts-es" in r.text


def test_html_issuer_page(client):
    r = client.get("/issuer/ES0125220311")
    assert r.status_code == 200
    assert "ACCIONA" in r.text
    assert "no es el interés corto total del mercado" in r.text


def test_search_redirects_to_issuer(client):
    r = client.get("/search?q=ES0125220311", follow_redirects=False)
    assert r.status_code == 303
    assert r.headers["location"] == "/issuer/ES0125220311"


def test_ambiguous_search_lists_candidates(client):
    r = client.get("/search?q=a")
    assert r.status_code == 200
    assert "mbiguous" in r.text or "S.A." in r.text


def test_no_write_endpoints(client):
    r = client.post("/api/v1/health")
    assert r.status_code == 405


def test_issuers_and_holders_pages(client):
    r = client.get("/issuers")
    assert r.status_code == 200 and "ACCIONA" in r.text
    r = client.get("/holders")
    assert r.status_code == 200 and "BlackRock" in r.text
    api_i = client.get("/api/v1/issuers").json()
    acciona = next(i for i in api_i["issuers"] if i["isin"] == "ES0125220311")
    # Current sheet rows for ACCIONA: 0.62 + 0.49 = 1.11
    assert acciona["disclosed_total"] == "1.11" and acciona["funds"] == 2
    api_h = client.get("/api/v1/holders").json()
    br = next(
        h
        for h in api_h["holders"]
        if h["holder_name"] == "BlackRock Investment Management (UK) Limited"
    )
    assert br["positions"] == 2


def test_index_shows_rankings(client):
    r = client.get("/")
    assert "Emisores más divulgados" in r.text
    assert "Últimas posiciones publicadas" in r.text
