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
    assert "Who&#39;s World Is This?!" not in page.get_data(as_text=True)
    assert "Anna Luv vs Chris Stylez" not in page.get_data(as_text=True)
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
                           data={"csrf_token": csrf, "outcome": "youtube_decide",
                                 "youtube_url": "https://youtu.be/abcdefghijk"})
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
    # Outcomes and footage now save independently; adding a result does not
    # silently attach or overwrite video in an old combined form.
    assert client.post(
        f"/hosts/workspace/{record['slug']}/{battle['key']}/video",
        data={"csrf_token": csrf, "expected_url": "",
              "youtube_url": "https://youtu.be/abcdefghijk"},
    ).status_code == 303
    from dca_rebuild.models import VaultBattleVideo
    with database[1]() as db:
        video = db.get(VaultBattleVideo, battle["key"])
        assert video.youtube_url == "https://www.youtube.com/watch?v=abcdefghijk"


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


def test_host_events_are_oldest_first_with_undated_events_last(database):
    for host in ("body-bag", "hypeituptv"):
        queue = host_queue(database[1], host)
        dates = [find_record(event["slug"])["date"] for event in queue["events"]]
        assert dates == sorted(dates, key=lambda value: (not bool(value), value or ""))
    body = host_queue(database[1], "body-bag")
    assert body["events"][0]["slug"] == "bodybag-body-bag-vol-2"
    assert body["events"][-1]["slug"] in ("bodybag-body-bag-vol-1", "bodybag-bodybag-5-outside-edition")


def test_host_workspaces_use_compact_inline_battle_rows(website, database):
    from dca_rebuild.models import VaultHostAccount
    from werkzeug.security import generate_password_hash
    with database[1].begin() as db:
        db.add(VaultHostAccount(
            host_key="hypeituptv", person_key="ty-shotz",
            display_name="Ty Shotz", email="ty-example@example.com",
            password_hash=generate_password_hash("test-secure-passphrase")))
    client = website.test_client()
    with client.session_transaction() as current:
        current["vault_host_account_id"] = 1
    response = client.get("/hosts/workspace")
    assert response.status_code == 200
    content = response.get_data(as_text=True)
    assert 'lfv-host-battle--inline' in content
    assert 'lfv-host-event--compact' in content
    assert content.index("Who&#39;s World Is This?!") < content.index("Class Is in Session")


def test_host_links_and_results_are_saved_independently(website, database):
    from dca_rebuild.models import VaultBattleVideo, VaultBattleVideoHistory
    record = find_record("whos-world-is-this-2025")
    battle = matchups(record)[0]["items"][0]
    client = website.test_client()
    with database[1].begin() as db:
        db.add(VaultHostAccount(host_key="hypeituptv", person_key="ty-shotz",
                               display_name="Ty Shotz", email="ty2@example.com",
                               password_hash=generate_password_hash("secure-passphrase-for-host")))
    with client.session_transaction() as state:
        state["vault_host_account_id"] = 1
    page = client.get("/hosts/workspace")
    assert page.status_code == 200
    assert page.get_data(as_text=True).count('lfv-host-row-controls') >= 8
    with client.session_transaction() as state:
        csrf = state["vault_host_claim_csrf"]
    result_path = f"/hosts/workspace/{record['slug']}/{battle['key']}/outcome"
    video_path = f"/hosts/workspace/{record['slug']}/{battle['key']}/video"
    # Host can enter an outcome before the administrator attaches footage.
    assert client.post(result_path, data={
        "csrf_token": csrf, "outcome": "a"}).status_code == 303
    with database[1]() as db:
        assert db.get(VaultBattleOutcome, battle["key"]).result == "a"
        assert db.get(VaultBattleVideo, battle["key"]) is None
    # Link save doesn't change the already recorded outcome.
    assert client.post(video_path, data={
        "csrf_token": csrf, "expected_url": "",
        "youtube_url": "https://example.org/watch?v=abcdefghijk"}).status_code == 400
    assert client.post(video_path, data={
        "csrf_token": csrf, "expected_url": "",
        "youtube_url": "https://youtu.be/abcdefghijk?t=95"}).status_code == 303
    normalized = "https://www.youtube.com/watch?v=abcdefghijk&t=95s"
    with database[1]() as db:
        assert db.get(VaultBattleVideo, battle["key"]).youtube_url == normalized
        assert db.get(VaultBattleOutcome, battle["key"]).result == "a"
        assert db.query(VaultBattleVideoHistory).count() == 1
    # An outdated form cannot erase a new link that another person saved.
    assert client.post(video_path, data={
        "csrf_token": csrf, "expected_url": "",
        "youtube_url": "https://youtu.be/lmnopqrstuv"}).status_code == 409
    assert client.post(result_path, data={"csrf_token": csrf, "outcome": "tie"}).status_code == 303
    with database[1]() as db:
        assert db.get(VaultBattleOutcome, battle["key"]).result == "tie"
        assert db.get(VaultBattleVideo, battle["key"]).youtube_url == normalized
        assert db.query(VaultBattleVideoHistory).count() == 1
    page = client.get("/hosts/workspace").get_data(as_text=True)
    assert normalized.replace("&", "&amp;") in page
    assert "Anna Luv vs Chris Stylez" in page
    archive = client.get("/archive/records/" + record["slug"]).get_data(as_text=True)
    assert "Watch battle on YouTube" in archive


def test_interrupted_battles_require_reason_and_remain_visible(website, database):
    from dca_rebuild.models import (
        VaultBattleInterruptionReason, VaultBattleInterruptionReasonHistory,
    )
    event = find_record("whos-world-is-this-2025")
    battle = matchups(event)[0]["items"][0]
    with database[1].begin() as db:
        db.add(VaultHostAccount(host_key="hypeituptv", person_key="ty-shotz",
            display_name="Ty Shotz", email="reason@example.com",
            password_hash=generate_password_hash("a-long-test-passphrase")))
    client = website.test_client()
    with client.session_transaction() as state:
        state["vault_host_account_id"] = 1
    client.get("/hosts/workspace")
    with client.session_transaction() as state:
        csrf = state["vault_host_claim_csrf"]
    path = f"/hosts/workspace/{event['slug']}/{battle['key']}/outcome"
    assert client.post(path, data={"csrf_token": csrf, "outcome": "postponed"}).status_code == 400
    assert client.post(path, data={
        "csrf_token": csrf, "outcome": "did_not_happen", "reason": "No"}).status_code == 400
    assert client.post(path, data={
        "csrf_token": csrf, "outcome": "postponed",
        "reason": "The venue closed unexpectedly"}).status_code == 303
    queue = host_queue(database[1], "hypeituptv")
    row = next(x for evt in queue["events"] if evt["slug"] == event["slug"]
               for section in evt["sections"] for x in section["rows"]
               if x["key"] == battle["key"])
    assert row["resolved"] and row["reason"] == "The venue closed unexpectedly"
    html = client.get("/hosts/workspace").get_data(as_text=True)
    assert "Anna Luv vs Chris Stylez" in html
    assert "The venue closed unexpectedly" in html
    archive = client.get("/archive/records/" + event["slug"]).get_data(as_text=True)
    assert "Reason: The venue closed unexpectedly" in archive
    with database[1]() as db:
        assert db.get(VaultBattleInterruptionReason, battle["key"]).occurrence == "postponed"
        assert db.query(VaultBattleInterruptionReasonHistory).count() == 1
    assert client.post(path, data={
        "csrf_token": csrf, "outcome": "did_not_happen"}).status_code == 400
    assert client.post(path, data={
        "csrf_token": csrf, "outcome": "did_not_happen",
        "reason": "Organizers could not proceed"}).status_code == 303
    with database[1]() as db:
        assert db.query(VaultBattleInterruptionReasonHistory).count() == 2
    # Changing to a completed battle clears the current interruption reason,
    # retaining its historical revisions.
    assert client.post(path, data={
        "csrf_token": csrf, "outcome": "a"}).status_code == 303
    with database[1]() as db:
        assert db.get(VaultBattleInterruptionReason, battle["key"]) is None
        assert db.query(VaultBattleInterruptionReasonHistory).count() == 3


def test_admin_queue_defaults_to_all_battles_and_saves_link_only(website, database):
    from dca_rebuild.models import VaultBattleVideo
    client = website.test_client()
    with client.session_transaction() as state:
        state["ledger_admin_authenticated"] = True
    record = find_record("whos-world-is-this-2025")
    battle = matchups(record)[0]["items"][0]
    response = client.get("/admin/hosts/hypeituptv/battles")
    assert response.status_code == 200
    assert 'Save link' in response.get_data(as_text=True)
    assert 'Save result' in response.get_data(as_text=True)
    assert 'Anna Luv vs Chris Stylez' in response.get_data(as_text=True)
    with client.session_transaction() as state:
        csrf = state["vault_host_admin_csrf"]
    path = f"/admin/hosts/hypeituptv/battles/{record['slug']}/{battle['key']}/video"
    assert client.post(path, data={
        "csrf_token": csrf, "expected_url": "",
        "youtube_url": "https://youtu.be/abcdefghijk"}).status_code == 303
    with database[1]() as db:
        assert db.get(VaultBattleVideo, battle["key"]).youtube_url.endswith("abcdefghijk")
        assert db.get(VaultBattleOutcome, battle["key"]) is None
    result_path = f"/admin/hosts/hypeituptv/battles/{record['slug']}/{battle['key']}/outcome"
    assert client.post(result_path, data={"csrf_token": csrf, "outcome": "a"}).status_code == 303
    with database[1]() as db:
        assert db.get(VaultBattleOutcome, battle["key"]).result == "a"
    assert "Anna Luv vs Chris Stylez" in client.get("/admin/hosts/hypeituptv/battles").get_data(as_text=True)


def test_massacre_teams_are_not_separate_battles(database):
    from dca_rebuild.host_access import host_queue
    event = find_record("litefeet-massacre-pt2-2026")
    all_matches = [b["label"] for group in matchups(event) for b in group["items"]]
    assert "Tok City vs Gotham City" not in all_matches
    assert "Groove Fam vs Lyve Fam" not in all_matches
    assert "Money Mase & Noah Shifty vs Lyght House & A Handro" in all_matches
    assert "BBQ & Tre Buckz vs Lil Live & Be Lyve" in all_matches
    queue = host_queue(database[1], "hypeituptv")
    massacre = next(event for event in queue["events"] if event["slug"] == "litefeet-massacre-pt2-2026")
    assert massacre["pending"] == 9


def test_host_can_add_unadvertised_battle_without_altering_flyer(website, database):
    from dca_rebuild.models import VaultAddedBattle, VaultBattleVideo
    client = website.test_client()
    with database[1].begin() as db:
        db.add(VaultHostAccount(
            host_key="hypeituptv", person_key="ty-shotz",
            display_name="Ty Shotz", email="eventhost@example.com",
            password_hash=generate_password_hash("a-long-test-password")))
    with client.session_transaction() as state:
        state["vault_host_account_id"] = 1
    assert client.get("/hosts/workspace").status_code == 200
    with client.session_transaction() as state:
        csrf = state["vault_host_claim_csrf"]
    slug = "whos-world-is-this-2025"
    path = f"/hosts/workspace/{slug}/battles/add"
    data = {
        "csrf_token": csrf, "side_a": "Surprise Dancer", "side_b": "Another Dancer",
        "outcome": "youtube_decide",
        "youtube_url": "https://youtu.be/abcdefghijk",
    }
    assert client.post(path, data=data).status_code == 303
    with database[1]() as db:
        added = db.query(VaultAddedBattle).one()
        assert added.event_slug == slug
        assert added.host_key == "hypeituptv"
        assert added.created_by == "Ty Shotz"
        assert db.get(VaultBattleOutcome, added.battle_key).result == "youtube_decide"
        assert db.get(VaultBattleVideo, added.battle_key).youtube_url.endswith("abcdefghijk")
        added_key = added.battle_key
    queue = host_queue(database[1], "hypeituptv")
    event = next(entry for entry in queue["events"] if entry["slug"] == slug)
    extra_group = next(section for section in event["sections"] if section["name"] == "Added at the event")
    assert any(row["key"] == added_key for row in extra_group["rows"])
    public = client.get("/archive/records/" + slug).get_data(as_text=True)
    assert "Surprise Dancer vs Another Dancer" in public
    assert "Added at the event" in public
    assert "Watch battle on YouTube" in public
    assert "Voting open" in public
    assert all(row["label"] != "Surprise Dancer vs Another Dancer"
               for group in matchups(find_record(slug)) for row in group["items"])
    assert client.post(path, data=data).status_code == 409


def test_spontaneous_battles_reject_wrong_host_invalid_links_and_missing_sides(website, database):
    from dca_rebuild.models import VaultAddedBattle
    client = website.test_client()
    with database[1].begin() as db:
        db.add(VaultHostAccount(
            host_key="body-bag", person_key="sns",
            display_name="SNS", email="sns-new@example.com",
            password_hash=generate_password_hash("test-strong-password")))
    with client.session_transaction() as state:
        state["vault_host_account_id"] = 1
    client.get("/hosts/workspace")
    with client.session_transaction() as state:
        csrf = state["vault_host_claim_csrf"]
    data = {
        "csrf_token": csrf, "side_a": "Spontaneous A", "side_b": "Spontaneous B",
        "outcome": "a", "youtube_url": "https://youtu.be/abcdefghijk",
    }
    assert client.post("/hosts/workspace/whos-world-is-this-2025/battles/add",
                       data=data).status_code == 403
    slug = "bodybag-body-bag-vol-2"
    url = f"/hosts/workspace/{slug}/battles/add"
    assert client.post(url, data={**data, "youtube_url": ""}).status_code == 400
    assert client.post(url, data={**data, "youtube_url": "https://example.com/not-youtube"}).status_code == 400
    assert client.post(url, data={**data, "side_b": "Spontaneous A"}).status_code == 400
    assert client.post(url, data={**data, "side_a": "Kid Smoove", "side_b": "Flii Boogie"}).status_code == 409
    with database[1]() as db:
        assert db.query(VaultAddedBattle).count() == 0


def test_admin_can_add_battle_to_existing_event_even_without_advertised_lineup(website, database):
    from dca_rebuild.models import VaultAddedBattle
    client = website.test_client()
    assert client.post("/admin/hosts/hypeituptv/events/whos-world-is-this-2025/battles/add",
                       data={"side_a": "A", "side_b": "B"}).status_code in (302, 303)
    with client.session_transaction() as state:
        state["ledger_admin_authenticated"] = True
    page = client.get("/admin/hosts/hypeituptv/battles?view=all")
    assert page.status_code == 200
    assert "+ Add battle that happened at this event" in page.get_data(as_text=True)
    with client.session_transaction() as state:
        csrf = state["vault_host_admin_csrf"]
    data = {
        "csrf_token": csrf, "side_a": "Late Entry A", "side_b": "Late Entry B",
        "outcome": "unknown", "youtube_url": "https://www.youtube.com/watch?v=abcdefghijk",
    }
    path = "/admin/hosts/hypeituptv/events/whos-world-is-this-2025/battles/add"
    assert client.post(path, data=data).status_code == 303
    with database[1]() as db:
        battle = db.query(VaultAddedBattle).one()
        assert battle.created_by == "Vault administrator"
        assert db.get(VaultBattleOutcome, battle.battle_key).result == "unknown"
    # A result can be filled in later without losing the video link.
    page = client.get("/admin/hosts/hypeituptv/battles?view=all")
    assert "Late Entry A vs Late Entry B" in page.get_data(as_text=True)
    path = f"/admin/hosts/hypeituptv/battles/whos-world-is-this-2025/{battle.battle_key}/outcome"
    assert client.post(path, data={"csrf_token": csrf, "outcome": "a"}).status_code == 303
