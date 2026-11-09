"""DCA 2026 administrative organization and archive separation regressions."""
from datetime import datetime
from dca_rebuild.models import (
    DCAEdition, DCACategory, DCANominee, DCANominationSubmission,
    DCACategorySuggestionSubmission,
)


def _admin_client(website):
    client = website.test_client()
    with client.session_transaction() as session:
        session["ledger_admin_authenticated"] = True
    return client


def test_dca_admin_sections_are_private_and_separate(website, database):
    guest = website.test_client()
    for path in ("/admin/awards", "/admin/awards/categories", "/admin/awards/activity",
                 "/admin/awards/results", "/admin/awards/history"):
        assert guest.get(path).status_code in (302,303,401,403)
    client = _admin_client(website)
    for path, heading in (
        ("/admin/awards", "Awards Management"),
        ("/admin/awards/categories", "2026 Categories"),
        ("/admin/awards/activity", "Nomination Activity"),
        ("/admin/awards/results", "Nomination Standings"),
        ("/admin/awards/history", "Round 1 Survey Archive"),
    ):
        result = client.get(path)
        assert result.status_code == 200, path
        html = result.get_data(as_text=True)
        assert heading in html
        assert 'href="/admin/awards/history"' in html
    assert client.get("/admin/awards/nonsense").status_code == 404
    assert client.get("/admin/awards/categories?page=0").status_code == 400
    html = client.get("/admin").get_data(as_text=True)
    assert 'href="/admin/awards"' in html
    # The historical Round 1 route expects its 2023 reference edition.
    # Seed it explicitly in this isolated test database; production already
    # carries the archived edition and its survey data.
    with database[1].begin() as db:
        if not db.query(DCAEdition).filter_by(year=2023).first():
            db.add(DCAEdition(year=2023, title="DCA 2023", phase="archived"))
    archive = client.get("/admin/round1").get_data(as_text=True)
    assert "Historical Round 1 category survey" in archive
    assert 'href="/admin/awards"' in archive
    nominee = client.get("/admin/dca/nominations").get_data(as_text=True)
    assert "NOMINEE REVIEW" in nominee
    assert "2026 Categories" in nominee


def test_2026_categories_are_not_survey_rows_and_activity_has_no_private_email(website, database):
    with database[1].begin() as db:
        edition = db.query(DCAEdition).filter_by(year=2026).first()
        assert edition is not None
        category = DCACategory(edition_id=edition.id,
                               name="Test Current Category",
                               normalized_name="test current category",
                               description="Official 2026 category description",
                               source_type="new", status="official")
        db.add(category)
        db.flush()
        nominee = DCANominee(edition_id=edition.id, category_id=category.id,
                             name="Nominee Example", normalized_name="nominee example",
                             moderation_status="approved")
        db.add(nominee)
        db.flush()
        db.add(DCANominationSubmission(edition_id=edition.id, nominee_id=nominee.id,
                                       submitter_hash="test-secret-hash-234",
                                       submitter_email="private@example.com",
                                       submitted_at=datetime(2026,11,9,14,0)))
    client = _admin_client(website)
    cat = client.get("/admin/awards/categories?q=Test+Current").get_data(as_text=True)
    assert "Test Current Category" in cat
    assert "Official 2026 category description" in cat
    assert "YES %" not in cat
    activity = client.get("/admin/awards/activity?q=Nominee+Example").get_data(as_text=True)
    assert "Nominee Example" in activity and "Test Current Category" in activity
    assert "private@example.com" not in activity
    assert "test-secret-hash-234" not in activity
    standings = client.get("/admin/awards/results?q=Nominee+Example").get_data(as_text=True)
    assert "Nominee Example" in standings
    assert "Nominations" in standings
    assert "not final votes" in standings.lower() or "not final" in standings.lower()


def test_status_filters_include_rejected_and_preserve_search(website, database):
    with database[1].begin() as db:
        edition = db.query(DCAEdition).filter_by(year=2026).first()
        category = DCACategory(edition_id=edition.id, name="Review Category",
                               normalized_name="review category", source_type="new", status="rejected")
        db.add(category)
        db.flush()
        db.add(DCANominee(edition_id=edition.id, category_id=category.id,
                          name="Rejected Nominee", normalized_name="rejected nominee",
                          moderation_status="rejected"))
        db.add(DCANominee(edition_id=edition.id, category_id=category.id,
                          name="Pending Nominee", normalized_name="pending nominee",
                          moderation_status="pending"))
    client = _admin_client(website)
    categories = client.get("/admin/awards/categories?status=rejected")
    assert categories.status_code == 200
    assert b"Review Category" in categories.data
    results = client.get("/admin/awards/results?status=rejected&q=Nominee")
    assert results.status_code == 200
    html = results.get_data(as_text=True)
    assert "Rejected Nominee" in html
    assert "Pending Nominee" not in html
    assert 'value="rejected" selected' in html
    empty = client.get("/admin/awards/results?status=rejected&q=NothingMatches")
    assert empty.status_code == 200
    assert 'value="rejected" selected' in empty.get_data(as_text=True)
