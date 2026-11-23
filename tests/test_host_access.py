"""Host affiliations and email-verified invite-only account access."""
from datetime import datetime, timedelta
import hashlib
import re

from dca_rebuild.archive_catalog import find_record
from dca_rebuild.battle_polls import matchups
from dca_rebuild.host_access import HOSTS, events_for_host, host_queue
from dca_rebuild.models import (
    VaultHostAccount, VaultHostInvitation, VaultHostClaimChallenge,
    VaultBattleOutcome, VaultHostBattleAudit,
)
from werkzeug.security import generate_password_hash


def test_two_host_workspaces_and_promo_roster_excluded(website, database):
    assert {host for host, _, _ in HOSTS} == {"hypeituptv", "body-bag"}
    hype = host_queue(database[1], "hypeituptv")
    body = host_queue(database[1], "body-bag")
    assert hype["event_count"] == 11
    assert body["event_count"] == 12
    assert hype["pending"] > 0
    assert body["pending"] > 0
    double = next(row for row in hype["events"] if row["slug"] == "double-impact-2026")
    assert double["roster_count"] == 7
    assert sum(len(section["rows"]) for section in double["sections"]) == 7
    assert website.test_client().get("/admin/hosts").status_code in (302, 303)
    assert website.test_client().get("/hosts/workspace").status_code in (302, 303)


def test_invites_are_hashed_private_single_use_and_claim_requires_code(website, database):
    client = website.test_client()
    with database[1].begin() as db:
        token = "a" * 48
        db.add(VaultHostInvitation(
            host_key="body-bag", person_key="chris-gz",
            token_hash=hashlib.sha256(token.encode()).hexdigest(),
            expires_at=datetime.utcnow() + timedelta(days=1),
        ))
    path = "/hosts/claim/" + token
    page = client.get(path)
    assert page.status_code == 200
    html = page.get_data(as_text=True)
    assert "Chris Gz" in html and "Body Bag" in html
    assert "Ty Shotz" in html
    with client.session_transaction() as saved:
        csrf = saved["vault_host_claim_csrf"]
    assert client.post(path, data={
        "csrf_token": csrf, "action": "send",
        "host_key": "hypeituptv", "person_key": "chris-gz",
        "email": "fake@example.com"
    }).status_code == 403
    assert client.post(path, data={
        "csrf_token": csrf, "action": "create",
        "display_name": "Chris", "password": "secure-larger-password"
    }).status_code == 403
    with database[1]() as db:
        assert db.query(VaultHostAccount).count() == 0
    assert client.get("/hosts/claim/" + "z"*48).status_code in (404, 410)


def test_host_login_is_scoped_and_cannot_edit_other_hosts_battles(website, database):
    with database[1].begin() as db:
        account = VaultHostAccount(
            host_key="body-bag", person_key="chris-gz", display_name="Chris Gz",
            email="chris@example.com", password_hash=generate_password_hash("long-secure-password"))
        db.add(account)
        db.flush()
        account_id = account.id
    client = website.test_client()
    client.get("/hosts/login")
    with client.session_transaction() as saved:
        csrf = saved["vault_host_claim_csrf"]
    response = client.post("/hosts/login", data={
        "csrf_token": csrf, "email": "chris@example.com",
        "password": "long-secure-password", "timezone": "America/New_York",
    })
    assert response.status_code == 303
    with client.session_transaction() as saved:
        csrf = saved["vault_host_claim_csrf"] if "vault_host_claim_csrf" in saved else None
    # Page establishes a new CSRF after the session is rotated at sign-in.
    page = client.get("/hosts/workspace")
    assert page.status_code == 200
    assert "Body Bag" in page.get_data(as_text=True)
    assert "HypeItUpTV" not in page.get_data(as_text=True)
    with client.session_transaction() as saved:
        csrf = saved["vault_host_claim_csrf"]
    record = find_record("whos-world-is-this-2025")
    first = matchups(record)[0]["items"][0]
    other_host = client.post(
        f"/hosts/workspace/{record['slug']}/{first['key']}/outcome",
        data={"csrf_token": csrf, "outcome": "a"})
    assert other_host.status_code == 403
    with database[1]() as db:
        assert db.query(VaultBattleOutcome).count() == 0
        db.get(VaultHostAccount, account_id).is_active = False
        db.commit()
    assert client.get("/hosts/workspace").status_code in (302, 303)


def test_same_host_result_is_recorded_with_audit_and_source(website, database):
    with database[1].begin() as db:
        account = VaultHostAccount(
            host_key="body-bag", person_key="sns", display_name="SNS",
            email="sns@example.com", password_hash=generate_password_hash("another-long-secure-password"))
        db.add(account)
        db.flush()
        account_id = account.id
    client = website.test_client()
    client.get("/hosts/login")
    with client.session_transaction() as saved:
        csrf = saved["vault_host_claim_csrf"]
    assert client.post("/hosts/login", data={
        "csrf_token": csrf, "email": "sns@example.com",
        "password": "another-long-secure-password",
        "timezone": "America/New_York",
    }).status_code == 303
    client.get("/hosts/workspace")
    with client.session_transaction() as saved:
        csrf = saved["vault_host_claim_csrf"]
    record = find_record("bodybag-body-bag-vol-2")
    battle = matchups(record)[0]["items"][0]
    response = client.post(f"/hosts/workspace/{record['slug']}/{battle['key']}/outcome",
                           data={"csrf_token": csrf, "outcome": "youtube_decide", "source_note": "Official upload"})
    assert response.status_code == 303
    with database[1]() as db:
        outcome = db.get(VaultBattleOutcome, battle["key"])
        assert outcome.occurred == "happened"
        assert outcome.result == "youtube_decide"
        assert "SNS" in outcome.source_note
        entry = db.query(VaultHostBattleAudit).one()
        assert entry.actor_account_id == account_id
        assert entry.event_slug == record["slug"]
    assert host_queue(database[1], "body-bag")["complete"] == 1


def test_verified_email_claim_creates_scoped_password_account(website, database, monkeypatch):
    from dca_rebuild import host_access
    token = "X" * 48
    with database[1].begin() as db:
        db.add(VaultHostInvitation(
            host_key="hypeituptv", person_key="ty-shotz",
            token_hash=hashlib.sha256(token.encode()).hexdigest(),
            expires_at=datetime.utcnow() + timedelta(days=2),
        ))
    captured = []
    monkeypatch.setattr(host_access.secrets, "randbelow", lambda upper: 123456)
    monkeypatch.setattr(host_access, "_send_email", lambda email, code: captured.append((email, code)))
    client = website.test_client()
    path = "/hosts/claim/" + token
    assert client.get(path).status_code == 200
    with client.session_transaction() as sess:
        csrf = sess["vault_host_claim_csrf"]
    result = client.post(path, data={
        "csrf_token": csrf, "action": "send", "host_key": "hypeituptv",
        "person_key": "ty-shotz", "email": "ty@example.com",
    })
    assert result.status_code == 200
    assert captured == [("ty@example.com", "123456")]
    result = client.post(path, data={
        "csrf_token": csrf, "action": "verify", "code": "123456",
    })
    assert result.status_code == 200
    assert "Display name" in result.get_data(as_text=True)
    result = client.post(path, data={
        "csrf_token": csrf, "action": "create",
        "display_name": "Ty Shotz", "password": "long-passphrase-for-host-access",
        "timezone": "America/New_York",
    })
    assert result.status_code == 303
    assert client.get(path).status_code == 410
    workspace = client.get("/hosts/workspace")
    assert workspace.status_code == 200
    assert "HypeItUpTV" in workspace.get_data(as_text=True)
    with database[1]() as db:
        account = db.query(VaultHostAccount).one()
        assert account.host_key == "hypeituptv"
        assert account.person_key == "ty-shotz"
        assert account.email == "ty@example.com"
        assert account.password_hash != "long-passphrase-for-host-access"
        assert db.query(VaultHostInvitation).one().status == "claimed"
