"""Rolling activity cloud: no evergreen nominations or historical popularity."""
from datetime import datetime, timedelta
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from dca_rebuild.models import (
    Base, DCAEdition, DCACategory, DCANominee, DCANominationSubmission,
    LedgerPageView, VaultAddedBattle, VaultBattleOutcome,
)
from dca_rebuild.profile_wall import VaultProfileWallPost
from dca_rebuild.people_activity import (
    VaultPeopleSearchHit, _match_search_profile, active_people_cloud,
)
from dca_rebuild.public_profiles import PublicProfileIndex


def _index():
    # Both profiles exist publicly via award nomination records, but neither
    # is active until a timestamped real-world or community event occurs.
    return PublicProfileIndex([], [], [
        {"name": "Best Team", "nominees": [{"name": "Team Demon"}]},
        {"name": "Most Improved", "nominees": [{"name": "XO Wavy"}]},
    ], [])


def _session_factory():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(bind=engine, tables=[
        DCAEdition.__table__, DCACategory.__table__, DCANominee.__table__,
        DCANominationSubmission.__table__, LedgerPageView.__table__,
        VaultAddedBattle.__table__, VaultBattleOutcome.__table__,
        VaultProfileWallPost.__table__, VaultPeopleSearchHit.__table__,
    ])
    return sessionmaker(bind=engine)


def test_search_attribution_requires_one_unambiguous_public_profile():
    index = _index()
    assert _match_search_profile(index, "Team Demon") == "/people/team-demon"
    assert _match_search_profile(index, "xo wavy") == "/people/xo-wavy"
    assert _match_search_profile(index, "team") is None
    assert _match_search_profile(index, "missing dancer") is None


def test_week_cloud_has_no_permanent_nominee_fallback(monkeypatch):
    from dca_rebuild import people_activity
    monkeypatch.setattr(people_activity, "all_records", lambda: [])
    factory = _session_factory()
    date = datetime(2035, 1, 15, 12, 0)
    assert active_people_cloud(_index(), factory, now=date) == []


def test_week_cloud_excludes_stale_hits_and_counts_recent_activity(monkeypatch):
    from dca_rebuild import people_activity
    monkeypatch.setattr(people_activity, "all_records", lambda: [])
    factory = _session_factory()
    now = datetime(2035, 1, 15, 12, 0)
    with factory.begin() as db:
        db.add(VaultPeopleSearchHit(
            profile_href="/people/team-demon", searched_at=now - timedelta(days=8)))
        db.add(VaultPeopleSearchHit(
            profile_href="/people/xo-wavy", searched_at=now - timedelta(days=1)))
        db.add(LedgerPageView(
            path="/people/xo-wavy", visitor_id="browser-one", traffic_type="human",
            viewed_at=now - timedelta(hours=1), is_new_visit=True))
        db.add(LedgerPageView(
            path="/people/team-demon", visitor_id="bot-one", traffic_type="bot",
            viewed_at=now - timedelta(hours=1), is_new_visit=True))
    active = active_people_cloud(_index(), factory, now=now)
    assert [item["href"] for item in active] == ["/people/xo-wavy"]
    assert "recent searches" in active[0]["reasons"]
    assert "profile visits" in active[0]["reasons"]
