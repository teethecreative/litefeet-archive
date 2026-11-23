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
    assert 'data-dca-nomination-form' not in html


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
