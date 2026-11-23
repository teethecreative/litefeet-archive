"""Focused regressions for the minimal 2026 DCA category experience."""
from conftest import identify

PATH = "/awards/dancers-choice/nominations"


def test_verified_grid_has_three_column_markup_and_category_dialog(website):
    client = website.test_client()
    identify(client)
    html = client.get(PATH).get_data(as_text=True)
    assert html.count('data-dca-open-category="') == 25
    assert 'id="lfv-dca-category-dialog"' in html
    assert 'dca-2026-minimal.css' in html
    assert 'dca-2026-modal.js' in html
    assert 'class="lfv-dca-rules-aside"' in html
    assert 'data-dca-add-new' in html
    assert 'data-dca-select-nominee' not in html  # no seed nominations initially
    assert 'data-dca-nomination-form' in html


def test_category_detail_only_shows_name_description_and_nominations(website):
    client = website.test_client()
    identify(client)
    html = client.get(PATH + "?category=1").get_data(as_text=True)
    assert 'class="lfv-dca-category-only"' in html
    assert "Nominations</h2>" in html
    assert 'class="lf9e-nominate-first"' not in html
    assert 'data-dca-nomination-form' in html  # opens in a dialog, not inline on the page


def test_modal_submission_reuses_session_and_respects_cooldown(website):
    client = website.test_client()
    token = identify(client)
    form = {
        "csrf_token": token,
        "category_id": "1",
        "name": "Dancer One",
        "reason": "Contributed to LiteFeet community dance sessions this year.",
    }
    headers = {"X-DCA-Modal": "1", "Accept": "application/json"}
    response = client.post(PATH, data=form, headers=headers)
    assert response.status_code == 200
    assert response.is_json
    assert response.get_json()["success"] is True
    html = client.get(PATH).get_data(as_text=True)
    assert "Dancer One" in html
    assert 'data-dca-select-nominee="Dancer One"' not in html  # on cooldown
    second = client.post(PATH, data={**form, "name": "Another Dancer"}, headers=headers)
    assert second.status_code == 200
    assert second.get_json()["success"] is False


def test_main_nominations_restores_full_writeins_button(website):
    client = website.test_client()
    identify(client)
    html = client.get(PATH).get_data(as_text=True)
    assert html.count("Browse All Write-In Categories") == 1
    assert 'href="/write-ins"' in html
    assert html.count('data-dca-open-category="') == 25


def test_writeins_uses_same_category_card_and_modal(website):
    client = website.test_client()
    anonymous = client.get("/write-ins")
    assert anonymous.status_code == 200
    html = anonymous.get_data(as_text=True)
    assert 'class="lfv-writeins-grid"' in html
    assert 'class="lfv-dca-grid-card"' in html
    assert 'id="lfv-dca-category-dialog"' in html
    assert "data-dca-open-category=" in html
    assert "data-dca-add-new" in html
    assert "Verify email to nominate" in html
    identify(client)
    html = client.get("/write-ins").get_data(as_text=True)
    assert 'data-dca-nomination-form' in html


def test_unstaged_writein_can_activate_in_popup_then_nominate(website, database):
    from dca_rebuild.models import DCAEdition, DCACategory
    _, factory, _ = database
    with factory.begin() as db:
        historical = DCAEdition(year=2023, title="Previous awards", phase="closed")
        db.add(historical)
        db.flush()
        db.add(DCACategory(
            edition_id=historical.id,
            name="Best Workshop", normalized_name="best workshop",
            source_type="returning", status="official",
        ))
    client = website.test_client()
    csrf_nom = identify(client)
    page = client.get("/write-ins").get_data(as_text=True)
    assert 'name="activation_name" value="Best Workshop"' in page
    assert 'data-dca-open-category="pending-' in page
    with client.session_transaction() as sess:
        csrf_writein = sess["lf9e_writeins_csrf"]
    headers = {"X-DCA-Modal": "1", "Accept": "application/json"}
    activated = client.post("/awards/dancers-choice/write-ins/activate",
                            data={"csrf_token": csrf_writein, "category": "Best Workshop"},
                            headers=headers)
    assert activated.status_code == 200
    category_id = activated.get_json()["category_id"]
    assert activated.get_json()["success"] is True
    submission = client.post(PATH, data={
        "csrf_token": csrf_nom, "category_id": category_id, "name": "Workshop Host",
        "reason": "Organized LiteFeet training workshops throughout this year.",
    }, headers=headers)
    assert submission.status_code == 200
    assert submission.get_json()["success"] is True
    after = client.get("/write-ins").get_data(as_text=True)
    assert "Workshop Host" in after
