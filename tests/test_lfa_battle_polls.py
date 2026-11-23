"""Regression coverage for 2026 LFA Battle Day community verdicts."""
import pytest

from dca_rebuild.models import LFABattlePoll, VaultBattleVote
from dca_rebuild.lfa_battle_polls import list_battle_polls, youtube_link


def _make_battle(database):
    key = "f" * 64
    with database[1].begin() as db:
        db.add(LFABattlePoll(battle_key=key, year=2026, side_a="Dancer A",
                             side_b="Dancer B", youtube_url="https://youtu.be/abcdefghijk",
                             published=True))
    return key


def _csrf(client):
    client.get("/awards/litefeet-awards")
    with client.session_transaction() as sess:
        return sess["lfv_lfa_battle_csrf"]


def test_youtube_link_rejects_unrelated_urls():
    assert youtube_link("https://youtu.be/abcdefghijk")
    assert youtube_link("https://www.youtube.com/watch?v=abcdefghijk")
    assert youtube_link("https://youtube.com/shorts/abcdefghijk")
    for bad in ["https://evil.com/watch?v=abcdefghijk",
                "http://youtube.com/watch?v=abcdefghijk",
                "https://youtube.com.evil.com/watch?v=abcdefghijk",
                "https://youtube.com/watch?v=short",
                "https://instagram.com/post/123"]:
        assert youtube_link(bad) is None


def test_public_awards_page_shows_community_vote_and_tie(website, database):
    key = _make_battle(database)
    client = website.test_client()
    html = client.get("/awards/litefeet-awards").get_data(as_text=True)
    assert "Who won the battles?" in html
    assert "Dancer A" in html and "Dancer B" in html
    assert "Tie" in html and "Verify your email to vote" in html
    assert "Watch on YouTube" in html
    assert "Add a battle (admin)" not in html
    with database[1]() as db:
        assert db.get(LFABattlePoll, key).published is True


def test_email_verified_vote_once_and_percentage_tie(website, database):
    key = _make_battle(database)
    client = website.test_client()
    csrf = _csrf(client)
    url = f"/awards/litefeet-awards/2026/battles/{key}/vote"
    assert client.post(url, data={"csrf_token": csrf, "choice": "a"}).status_code == 403
    with client.session_transaction() as sess:
        sess["lf9e_verified_hash"] = "b" * 64
        sess["lf9e_verified_at"] = 100
    response = client.post(url, data={"csrf_token": csrf, "choice": "t"})
    assert response.status_code == 303
    assert client.post(url, data={"csrf_token": csrf, "choice": "a"}).status_code == 409
    rows = list_battle_polls(database[1], "b" * 64)
    assert rows[0]["already_voted"]
    assert rows[0]["votes_tie"] == 1 and rows[0]["percent_tie"] == 100
    assert rows[0]["total_votes"] == 1
    with database[1]() as db:
        assert db.query(VaultBattleVote).filter_by(battle_key=key).count() == 1


def test_hidden_matchup_cannot_be_voted_on(website, database):
    key = _make_battle(database)
    with database[1].begin() as db:
        db.get(LFABattlePoll, key).published = False
    client = website.test_client()
    csrf = _csrf(client)
    html = client.get("/awards/litefeet-awards").get_data(as_text=True)
    assert "Dancer A" not in html
    with client.session_transaction() as sess:
        sess["lf9e_verified_hash"] = "c" * 64
        sess["lf9e_verified_at"] = 100
    response = client.post(f"/awards/litefeet-awards/2026/battles/{key}/vote",
                           data={"csrf_token": csrf, "choice": "t"})
    assert response.status_code == 404


def test_only_admin_can_create_edit_battles(website, database):
    client = website.test_client()
    csrf = _csrf(client)
    create = "/admin/awards/litefeet-awards/2026/battles"
    payload = {"csrf_token": csrf, "side_a": "A", "side_b": "B",
               "youtube_url": "https://youtu.be/abcdefghijk"}
    assert client.post(create, data=payload).status_code in (302, 401, 403)
    with database[1]() as db:
        assert db.query(LFABattlePoll).count() == 0
    with client.session_transaction() as sess:
        sess["ledger_admin_authenticated"] = True
    assert client.post(create, data=payload).status_code == 303
    with database[1]() as db:
        rows = db.query(LFABattlePoll).all()
        assert len(rows) == 1
        key = rows[0].battle_key
    edit = f"/admin/awards/litefeet-awards/2026/battles/{key}/edit"
    assert client.post(edit, data=dict(payload, visibility="hidden")).status_code == 303
    assert not list_battle_polls(database[1])
    assert len(list_battle_polls(database[1], is_admin=True)) == 1


def test_existing_votes_not_reassigned_to_different_people(website, database):
    key = _make_battle(database)
    with database[1].begin() as db:
        db.add(VaultBattleVote(battle_key=key, voter_hash="d" * 64, choice="a"))
    client = website.test_client()
    csrf = _csrf(client)
    with client.session_transaction() as sess:
        sess["ledger_admin_authenticated"] = True
    response = client.post(
        f"/admin/awards/litefeet-awards/2026/battles/{key}/edit",
        data={"csrf_token": csrf, "side_a": "Wrong Name", "side_b": "Dancer B",
              "youtube_url": "https://youtu.be/abcdefghijk", "visibility": "published"})
    assert response.status_code == 409
    with database[1]() as db:
        assert db.get(LFABattlePoll, key).side_a == "Dancer A"
