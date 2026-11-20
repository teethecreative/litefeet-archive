"""Website experience feedback stays private, contextual, and reviewable."""
from io import BytesIO

from PIL import Image

from dca_rebuild.models import VaultDevelopmentFeedback, VaultDevelopmentItem


def _admin(client):
    with client.session_transaction() as state:
        state["ledger_admin_authenticated"] = True
    assert client.get("/admin/development").status_code == 200
    with client.session_transaction() as state:
        return state["vault_admin_workspace_csrf"]


def _csrf(client, page="/archive/records/example"):
    response = client.get("/feedback/development", query_string={"page": page})
    assert response.status_code == 200
    assert 'name="page_path"' in response.get_data(as_text=True)
    with client.session_transaction() as state:
        return state["vault_development_feedback_csrf"]


def _image():
    output = BytesIO()
    Image.new("RGB", (48, 32), (220, 10, 30)).save(output, format="PNG")
    output.seek(0)
    return output


def test_footer_link_and_feedback_page_context(website):
    client = website.test_client()
    homepage = client.get("/").get_data(as_text=True)
    assert "Give Feedback" in homepage
    assert 'id="lfv-give-feedback"' in homepage
    page = client.get("/feedback/development?page=/archive/timeline").get_data(as_text=True)
    assert 'value="/archive/timeline"' in page
    assert "Design or layout" in page
    assert "Page helpfulness" in page
    assert "screenshot" in page
    hostile = client.get("/feedback/development?page=https://outside.example.com")
    assert 'value="https://outside.example.com"' not in hostile.get_data(as_text=True)


def test_submission_stores_private_page_context_and_screenshot(website, database):
    client = website.test_client()
    token = _csrf(client)
    data = {
        "csrf_token": token,
        "feedback_type": "bug",
        "title": "Broken archive card",
        "area": "archive",
        "details": "The archive card does not open on mobile.",
        "page_path": "/archive/records/example",
        "helpful": "no",
        "email": "visitor@example.org",
        "screenshot": (_image(), "issue.png"),
    }
    assert client.post("/feedback/development", data=data,
                       content_type="multipart/form-data").status_code == 200
    with database[1]() as db:
        entry = db.query(VaultDevelopmentFeedback).one()
        assert entry.feedback_type == "bug"
        assert entry.page_path == "/archive/records/example"
        assert entry.helpful is False
        assert entry.screenshot_mime == "image/jpeg"
        assert entry.screenshot_data[:2] == b"\\xff\\xd8"
        entry_id = entry.id
    assert client.get("/admin/website-feedback").status_code in (302, 303, 401, 403)
    assert client.get(f"/admin/website-feedback/{entry_id}/screenshot").status_code in (302, 303, 401, 403)
    admin_token = _admin(client)
    private_page = client.get("/admin/website-feedback?type=bug").get_data(as_text=True)
    assert "Broken archive card" in private_page
    assert "/archive/records/example" in private_page
    assert "visitor@example.org" in private_page
    assert client.get("/admin/website-feedback?type=not-a-type").status_code == 400
    screenshot = client.get(f"/admin/website-feedback/{entry_id}/screenshot")
    assert screenshot.status_code == 200
    assert screenshot.headers["Cache-Control"] == "private, no-store"
    assert screenshot.mimetype == "image/jpeg"
    assert client.post(f"/admin/website-feedback/{entry_id}/status",
                       data={"status": "resolved"}).status_code == 400
    assert client.post(f"/admin/website-feedback/{entry_id}/status",
                       data={"status": "reviewing", "csrf_token": admin_token}).status_code == 303
    with database[1]() as db:
        assert db.get(VaultDevelopmentFeedback, entry_id).status == "reviewing"
    assert client.post(f"/admin/website-feedback/{entry_id}/status",
                       data={"status": "converted", "csrf_token": admin_token}).status_code == 303
    with database[1]() as db:
        assert db.query(VaultDevelopmentItem).filter_by(source_feedback_id=entry_id).count() == 1
    assert client.post(f"/admin/website-feedback/{entry_id}/status",
                       data={"status": "converted", "csrf_token": admin_token}).status_code == 303
    with database[1]() as db:
        assert db.query(VaultDevelopmentItem).filter_by(source_feedback_id=entry_id).count() == 1


def test_bad_feedback_is_rejected(website):
    client = website.test_client()
    token = _csrf(client)
    data = {
        "csrf_token": token, "title": "Report", "details": "This button is broken.",
        "area": "site", "feedback_type": "bug", "page_path": "//outside.example",
    }
    assert client.post("/feedback/development", data=data).status_code == 400
    data["page_path"] = "/"
    data["feedback_type"] = "unsafe"
    assert client.post("/feedback/development", data=data).status_code == 400
    data["feedback_type"] = "bug"
    data["screenshot"] = (BytesIO(b"not an image"), "fake.png")
    assert client.post("/feedback/development", data=data,
                       content_type="multipart/form-data").status_code == 400
