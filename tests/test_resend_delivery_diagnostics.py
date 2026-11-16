"""Nonsecret Resend diagnostics must explain failures without leaking personal data."""
import logging

from dca_rebuild.email_verification import delivery_config_status


def test_delivery_config_checks_bare_and_named_resend_senders(monkeypatch):
    monkeypatch.setenv("RESEND_API_KEY", "re_mock_private_key")
    monkeypatch.setenv("RESEND_FROM_EMAIL", "no-reply@thelitefeetvault.com")
    result = delivery_config_status()
    assert result == {
        "api_key_present": True,
        "sender_present": True,
        "sender_format_valid": True,
    }
    monkeypatch.setenv(
        "RESEND_FROM_EMAIL", "The LiteFeet Vault <no-reply@thelitefeetvault.com>"
    )
    assert delivery_config_status()["sender_format_valid"] is True
    monkeypatch.setenv("RESEND_FROM_EMAIL", "not-an-email")
    assert delivery_config_status()["sender_format_valid"] is False
    monkeypatch.delenv("RESEND_FROM_EMAIL")
    assert delivery_config_status()["sender_present"] is False


def test_resend_http_failure_is_safely_classified(website, monkeypatch, caplog):
    monkeypatch.setenv("DCA_2026_VERIFIED_EMAIL_ENABLED", "true")
    monkeypatch.setenv("RESEND_API_KEY", "re_sensitive_value_do_not_log")
    monkeypatch.setenv("RESEND_FROM_EMAIL", "The LiteFeet Vault <no-reply@thelitefeetvault.com>")

    class ProviderResponse:
        status_code = 403
        text = "Sensitive provider message should never be logged"

    def provider_request(url, **kwargs):
        assert url == "https://api.resend.com/emails"
        assert kwargs["json"]["to"] == ["person@example.com"]
        return ProviderResponse()

    monkeypatch.setattr("dca_rebuild.email_verification.requests.post", provider_request)
    client = website.test_client()
    page = client.get("/awards/dancers-choice/nominations")
    assert page.status_code == 200
    with client.session_transaction() as sess:
        csrf = sess["lf9e_nomination_csrf"]
    with caplog.at_level(logging.ERROR):
        response = client.post("/awards/dancers-choice/nominations", data={
            "csrf_token": csrf,
            "action": "identify",
            "email": "person@example.com",
        })
    assert response.status_code == 303
    assert "category=provider_http_403" in caplog.text
    assert "person@example.com" not in caplog.text
    assert "re_sensitive_value_do_not_log" not in caplog.text
    assert "Sensitive provider message" not in caplog.text
    with client.session_transaction() as sess:
        assert "lf9e_verified_hash" not in sess
        assert "lf9e_recent_hash" not in sess
