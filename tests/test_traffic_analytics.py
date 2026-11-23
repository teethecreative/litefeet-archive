"""Regression tests: distinguish audience from crawlers without losing activity."""

from datetime import datetime

from dca_rebuild.models import LedgerPageView
from dca_rebuild.traffic_classification import classify_traffic


def test_agent_classification_is_explicit_and_conservative():
    assert classify_traffic("meta-externalagent/1.1") == ("bot", "Meta ExternalAgent")
    assert classify_traffic("facebookexternalhit/1.1") == ("bot", "Meta link preview")
    assert classify_traffic("Googlebot/2.1") == ("bot", "Googlebot")
    assert classify_traffic("python-requests/2.32") == ("bot", "Other automated")
    assert classify_traffic("Mozilla/5.0 (Macintosh) Chrome/145") == (
        "human", "Likely human browser"
    )
    assert classify_traffic("") == ("unclassified", "Missing user agent")
    assert classify_traffic("Mozilla/5.0", is_admin=True) == (
        "internal", "Authenticated admin"
    )


def test_all_traffic_is_recorded_but_humans_are_counted_separately(website, database):
    from dca_rebuild.app import record_ledger_page_view

    website.after_request(record_ledger_page_view)
    client = website.test_client()
    human_agent = {"User-Agent": "Mozilla/5.0 (Macintosh) Chrome/145"}
    meta_agent = {"User-Agent": "meta-externalagent/1.1"}

    assert client.get("/", headers=human_agent).status_code == 200
    assert client.get("/", headers=meta_agent).status_code == 200
    assert client.get("/", headers=meta_agent).status_code == 200

    with client.session_transaction() as state:
        state["ledger_admin_authenticated"] = True
    assert client.get("/", headers=human_agent).status_code == 200

    with database[1]() as db:
        views = db.query(LedgerPageView).order_by(LedgerPageView.id).all()
        assert [row.traffic_type for row in views] == [
            "human", "bot", "bot", "internal"
        ]
        assert views[1].traffic_source == "Meta ExternalAgent"
        assert views[1].visitor_id == views[2].visitor_id
        assert views[1].visitor_id != views[0].visitor_id
        assert views[3].visitor_id == views[0].visitor_id

    human = client.get("/admin/analytics?traffic=human")
    assert human.status_code == 200
    assert "Page views" in human.get_data(as_text=True)
    assert "Traffic quality and technical breakdown" in human.get_data(as_text=True)
    assert "Meta ExternalAgent" in human.get_data(as_text=True)

    for kind in ("bot", "internal", "all"):
        assert client.get("/admin/analytics?traffic=" + kind).status_code == 200
        assert client.get("/admin/analytics/visitors?traffic=" + kind).status_code == 200


def test_legacy_records_remain_unclassified(website, database):
    with database[1].begin() as db:
        db.add(LedgerPageView(
            visitor_id="a" * 32,
            path="/",
            viewed_at=datetime.utcnow(),
            is_new_visit=True,
        ))
    client = website.test_client()
    with client.session_transaction() as state:
        state["ledger_admin_authenticated"] = True
    with database[1]() as db:
        row = db.query(LedgerPageView).one()
        assert row.traffic_type == "unclassified"
    html = client.get("/admin/analytics?traffic=unclassified").get_data(as_text=True)
    assert "Historical / Unknown" in html or "Historical / unknown" in html
    assert "Historical / unknown" in html
