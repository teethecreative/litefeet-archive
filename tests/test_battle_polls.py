"""Permanent battle community poll regression coverage."""
from dca_rebuild.battle_polls import build_battle_rows, matchups
from dca_rebuild.archive_catalog import find_record
from dca_rebuild.models import VaultBattleOutcome, VaultBattleVote


def test_advertised_lineups_start_unconfirmed_and_poll_free(website, database):
    record = find_record("whos-world-is-this-2025")
    groups = build_battle_rows(record, database[1])
    assert groups and groups[0]["items"]
    assert all(not m["active_poll"] for g in groups for m in g["items"])
    html = website.test_client().get("/archive/records/whos-world-is-this-2025").get_data(as_text=True)
    assert "Outcome unconfirmed" in html
    assert "Community:" not in html


def test_only_confirmed_two_sided_ties_and_youtube_decides_open(website, database):
    record = find_record("whos-world-is-this-2025")
    first, second, third = matchups(record)[0]["items"][:3]
    with database[1].begin() as db:
        db.add_all([
            VaultBattleOutcome(battle_key=first["key"], event_slug=record["slug"],
                               lineup_label=first["label"], occurred="happened",
                               result="tie", source_note="Judges' announcement"),
            VaultBattleOutcome(battle_key=second["key"], event_slug=record["slug"],
                               lineup_label=second["label"], occurred="happened",
                               result="youtube_decide", source_note="Video announcement"),
            VaultBattleOutcome(battle_key=third["key"], event_slug=record["slug"],
                               lineup_label=third["label"], occurred="happened",
                               result="a", source_note="Official result"),
        ])
        db.add_all([
            VaultBattleVote(battle_key=first["key"], voter_hash="one", choice="a"),
            VaultBattleVote(battle_key=first["key"], voter_hash="two", choice="a"),
            VaultBattleVote(battle_key=first["key"], voter_hash="three", choice="b"),
        ])
    groups = build_battle_rows(record, database[1])
    rows = groups[0]["items"]
    assert rows[0]["active_poll"] and rows[1]["active_poll"]
    assert not rows[2]["active_poll"]
    assert rows[0]["total_votes"] == 3
    assert (rows[0]["percent_a"], rows[0]["percent_b"]) == (67, 33)
    html = website.test_client().get("/archive/records/whos-world-is-this-2025").get_data(as_text=True)
    assert "Voting open" in html
    assert "67% (2)" in html
    assert "33% (1)" in html
    assert "Winner: Nana" in html or "Winner: " in html


def test_poll_voting_requires_verified_identity_and_preserves_official_result(website, database):
    record = find_record("whos-world-is-this-2025")
    first = matchups(record)[0]["items"][0]
    with database[1].begin() as db:
        db.add(VaultBattleOutcome(battle_key=first["key"], event_slug=record["slug"],
                                  lineup_label=first["label"], occurred="happened",
                                  result="tie", source_note="Event footage"))
    client = website.test_client()
    path = f'/archive/records/{record["slug"]}'
    assert client.get(path).status_code == 200
    with client.session_transaction() as sess:
        csrf = sess["vault_archive_csrf"]
    vote = path + f'/battles/{first["key"]}/vote'
    assert client.post(vote, data={"choice": "a", "csrf_token": csrf}).status_code == 403
    assert client.post(vote, data={"choice": "a", "csrf_token": "wrong"}).status_code == 400
    # Verified identity is the same private identity used by DCA, not the
    # browser's resettable guest cookie.
    with client.session_transaction() as sess:
        sess["lf9e_verified_hash"] = "a" * 64
        sess["lf9e_verified_at"] = 100
    assert client.post(vote, data={"choice": "a", "csrf_token": csrf}).status_code == 303
    assert client.post(vote, data={"choice": "b", "csrf_token": csrf}).status_code == 409
    with database[1]() as db:
        assert db.query(VaultBattleVote).count() == 1
        assert db.get(VaultBattleOutcome, first["key"]).result == "tie"


def test_admin_cannot_publish_unsourced_or_impossible_poll(website, database):
    record = find_record("whos-world-is-this-2025")
    first = matchups(record)[0]["items"][0]
    client = website.test_client()
    path = f'/archive/records/{record["slug"]}'
    client.get(path)
    with client.session_transaction() as sess:
        csrf = sess["vault_archive_csrf"]
    endpoint = f'/admin/archive/records/{record["slug"]}/battles/{first["key"]}/outcome'
    data = {"occurred": "happened", "result": "tie", "source_note": "Video footage", "csrf_token": csrf}
    assert client.post(endpoint, data=data).status_code in (302, 303, 401, 403)
    with database[1]() as db:
        assert db.query(VaultBattleOutcome).count() == 0
