"""The history form must not submit to the calendar or publish without review."""
from dca_rebuild.models import VaultArchiveContribution, VaultArchiveContributionReview


def test_archive_contribution_modal_is_not_calendar_form(website):
    client = website.test_client()
    page = client.get("/community")
    assert page.status_code == 200
    html = page.get_data(as_text=True)
    assert 'data-open-archive-contribution' in html
    assert 'id="lfv-archive-modal"' in html
    assert 'action="/archive/contribute"' in html
    assert 'name="contribution_type"' in html
    assert 'name="source_description"' in html
    fallback = client.get("/archive/contribute")
    assert fallback.status_code == 200
    assert 'action="/archive/contribute"' in fallback.get_data(as_text=True)
    archive = client.get("/archive")
    assert 'data-open-archive-contribution' in archive.get_data(as_text=True)


def test_archive_contribution_private_review_and_decision(website, database):
    client = website.test_client()
    client.get("/community")
    with client.session_transaction() as state:
        token = state["vault_archive_contribution_csrf"]
    data = dict(csrf_token=token, contribution_type="history",
                title="Early LiteFeet gathering",
                description="Community history with dates and witnesses to investigate.",
                historical_period="2000s", source_description="Firsthand account from a dancer",
                contributor_name="Contributor", contact_email="research@example.org")
    assert client.post("/archive/contribute", data=dict(data, csrf_token="invalid")).status_code == 400
    assert client.post("/archive/contribute", data=dict(data, source_description="")).status_code == 400
    ok = client.post("/archive/contribute", data=data, headers={"Accept": "application/json"})
    assert ok.status_code == 201 and ok.json["ok"]
    with database[1]() as db:
        record = db.query(VaultArchiveContribution).one()
        assert record.title == data["title"]
        assert record.status == "pending"
        record_id = record.id
    assert client.get("/admin/archive/contributions").status_code in (302, 303, 401, 403)
    with client.session_transaction() as state:
        state["ledger_admin_authenticated"] = True
    review = client.get("/admin/archive/contributions")
    assert review.status_code == 200
    assert "Early LiteFeet gathering" in review.get_data(as_text=True)
    assert "research@example.org" in review.get_data(as_text=True)
    with client.session_transaction() as state:
        admin_token = state["vault_archive_contribution_admin_csrf"]
    assert client.post(f"/admin/archive/contributions/{record_id}/decision",
                       data={"decision": "approved"}).status_code == 400
    decided = client.post(f"/admin/archive/contributions/{record_id}/decision",
                          data={"csrf_token": admin_token, "decision": "approved",
                                "note": "Retain as a research lead, not verified."})
    assert decided.status_code == 303
    with database[1]() as db:
        record = db.get(VaultArchiveContribution, record_id)
        assert record.status == "approved"
        assert db.query(VaultArchiveContributionReview).count() == 1
    assert client.post(f"/admin/archive/contributions/{record_id}/decision",
                       data={"csrf_token":admin_token,"decision":"rejected"}).status_code == 409


def test_awards_not_a_submission_type(website):
    client = website.test_client()
    client.get("/community")
    with client.session_transaction() as state:
        token = state["vault_archive_contribution_csrf"]
    response = client.post("/archive/contribute", data={
        "csrf_token": token, "contribution_type": "awards",
        "title": "My award", "description": "I deserve an award for what I do",
        "source_description": "Self nomination", "contact_email": "me@example.org",
    }, headers={"Accept": "application/json"})
    assert response.status_code == 400
