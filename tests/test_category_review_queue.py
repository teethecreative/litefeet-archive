"""The moderation queue is not the old draft checkbox workflow."""
from dca_rebuild.models import (
    DCAEdition, DCACategory, DCACategorySuggestionSubmission,
    DCANewCategorySuggestion, DCAReturningCategoryReview,
)


def _admin(website):
    client = website.test_client()
    with client.session_transaction() as session:
        session["ledger_admin_authenticated"] = True
        session["dca_moderation_csrf"] = "test-token"
    return client


def _seed(database):
    with database[1].begin() as db:
        historical = DCAEdition(year=2023, title="Historical DCA",
                                phase="archived")
        db.add(historical)
        db.flush()
        returning = DCACategory(
            edition_id=historical.id,
            name="Battle Host of the Year",
            normalized_name="battle host of the year",
            description=None,
            source_type="new", status="official",
        )
        db.add(returning)
        current = db.query(DCAEdition).filter_by(year=2026).first()
        submission = DCACategorySuggestionSubmission(
            edition_id=current.id, email_hash="test-hash",
            category_count_preference="all",
        )
        db.add(submission)
        db.flush()
        suggestion = DCANewCategorySuggestion(
            submission_id=submission.id, category_name="Best Vibes",
            normalized_name="best vibes", description=None,
            moderation_status="pending",
        )
        db.add(suggestion)
        db.flush()
        return returning.id, suggestion.id


def test_moderation_page_has_no_draft_checkboxes(website, database):
    _seed(database)
    client = _admin(website)
    response = client.get("/admin/round1")
    assert response.status_code == 200
    html = response.get_data(as_text=True)
    assert "Category Moderation" in html
    assert "Battle Host of the Year" in html
    assert "Best Vibes" in html
    assert 'type="checkbox"' not in html
    assert "SAVE CATEGORY DRAFT" not in html
    assert "Description needed" in html
    assert "Historical Round 1 category survey" not in html
    assert client.get("/admin/round1/archive").status_code == 200


def test_approve_requires_description_and_leaves_pending_queue(website, database):
    _, suggestion_id = _seed(database)
    client = _admin(website)
    path = f"/admin/round1/review/new/{suggestion_id}"
    data = dict(
        csrf_token="test-token", category_name="Best Vibes",
        category_description="", decision="approved",
    )
    assert client.post(path, data=data).status_code == 400
    data["category_description"] = "Recognizes outstanding crowd energy."
    assert client.post(path, data=data).status_code == 303
    pending = client.get("/admin/round1").get_data(as_text=True)
    assert "Best Vibes" not in pending
    approved = client.get("/admin/round1?status=approved").get_data(as_text=True)
    assert "Best Vibes" in approved
    assert "Recognizes outstanding crowd energy." in approved


def test_reject_returning_category_preserves_historical_record(website, database):
    returning_id, _ = _seed(database)
    client = _admin(website)
    path = f"/admin/round1/review/returning/{returning_id}"
    response = client.post(path, data=dict(
        csrf_token="test-token", category_name="Battle Host of the Year",
        category_description="",
        decision="rejected",
    ))
    assert response.status_code == 303
    assert "Battle Host of the Year" not in client.get(
        "/admin/round1"
    ).get_data(as_text=True)
    assert "Battle Host of the Year" in client.get(
        "/admin/round1?status=rejected"
    ).get_data(as_text=True)
    with database[1]() as db:
        original = db.get(DCACategory, returning_id)
        assert original.description is None
        assert original.status == "official"
        assert db.query(DCAReturningCategoryReview).filter_by(
            category_id=returning_id, status="rejected").count() == 1


def test_reopen_from_completed_status_and_search(website, database):
    _, suggestion_id = _seed(database)
    client = _admin(website)
    path = f"/admin/round1/review/new/{suggestion_id}"
    item = dict(csrf_token="test-token", category_name="Best Vibes",
                category_description="", decision="rejected")
    assert client.post(path, data=item).status_code == 303
    item["decision"] = "pending"
    assert client.post(path, data=item).status_code == 303
    assert "Best Vibes" in client.get(
        "/admin/round1?q=Vibes&missing=1").get_data(as_text=True)
    assert "Battle Host of the Year" not in client.get(
        "/admin/round1?q=Vibes&missing=1").get_data(as_text=True)


def test_invalid_merge_and_csrf_are_rejected(website, database):
    _, suggestion_id = _seed(database)
    client = _admin(website)
    path = f"/admin/round1/review/new/{suggestion_id}"
    item = dict(csrf_token="wrong", category_name="Best Vibes",
                category_description="Test", decision="approved")
    assert client.post(path, data=item).status_code == 400
    item.update(csrf_token="test-token", decision="merged",
                merge_target_key=f"new:{suggestion_id}")
    assert client.post(path, data=item).status_code == 400
