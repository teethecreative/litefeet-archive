from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from threading import Barrier
import pytest
from sqlalchemy import inspect
from dca_rebuild.models import DCANominee, DCANominationSubmission, LegacyNominationSubmission, NominationCooldown
from dca_rebuild.nomination_service import add_nomination, remaining_seconds
from dca_rebuild.nomination_migration import migrate_nomination_history
from dca_rebuild.phase9e import LegacyNominationDetail9E, NominationDetail9E, get_counts, qualification
from conftest import identify

NOW = datetime(2026, 11, 5, 14, 30)
PATH = '/awards/dancers-choice/nominations'


def nominate(factory, edition_id, category=1, who='hash-one', name='Dancer One', now=NOW):
    with factory() as db:
        nominee, created = add_nomination(db, edition_id=edition_id, category_id=category,
                                          name=name, submitter_hash=who, now=now)
        if created:
            db.commit()
        else:
            db.rollback()
        return created


def test_per_category_rolling_limits(database):
    _, factory, edition = database
    assert nominate(factory, edition)
    assert nominate(factory, edition, category=2)
    assert not nominate(factory, edition, name='Someone Else')
    assert not nominate(factory, edition, now=NOW + timedelta(hours=24, microseconds=-1))
    assert nominate(factory, edition, now=NOW + timedelta(hours=24))
    assert not nominate(factory, edition, now=NOW + timedelta(hours=24, minutes=1))
    assert nominate(factory, edition, who='hash-two', now=NOW + timedelta(minutes=1))
    with factory() as db:
        assert db.query(DCANominationSubmission).count() == 4
        assert db.query(DCANominee).count() == 2


def test_writeins_have_independent_cooldowns(database):
    _, factory, edition = database
    assert nominate(factory, edition, category=26)
    assert nominate(factory, edition, category=27)
    assert nominate(factory, edition)
    assert not nominate(factory, edition, category=26)
    assert nominate(factory, edition, category=26, now=NOW + timedelta(days=1))


def test_concurrent_same_category(database):
    _, factory, edition = database
    barrier = Barrier(4)
    def send(index):
        barrier.wait()
        return nominate(factory, edition, name=f'Dancer {index}')
    with ThreadPoolExecutor(max_workers=4) as pool:
        assert sorted(pool.map(send, range(4))) == [False, False, False, True]
    with factory() as db:
        assert db.query(DCANominationSubmission).count() == 1
        assert db.query(NominationCooldown).count() == 1


def test_concurrent_different_emails_same_nominee(database):
    _, factory, edition = database
    barrier = Barrier(3)
    def send(index):
        barrier.wait()
        return nominate(factory, edition, who=f'hash-{index}')
    with ThreadPoolExecutor(max_workers=3) as pool:
        assert all(pool.map(send, range(3)))
    with factory() as db:
        assert db.query(DCANominee).count() == 1
        assert db.query(DCANominationSubmission).count() == 3


def test_failed_transaction_does_not_spend_category(database):
    _, factory, edition = database
    with factory() as db:
        _, created = add_nomination(db, edition_id=edition, category_id=1, name='Dancer One', submitter_hash='hash-one', now=NOW)
        assert created
        db.rollback()
    assert nominate(factory, edition)


def test_historical_import_preserves_legacy_and_details(database):
    engine, factory, edition_id = database
    with factory.begin() as db:
        nominee = DCANominee(edition_id=edition_id, category_id=1, name='Historical Dancer', normalized_name='historical dancer', moderation_status='approved')
        db.add(nominee); db.flush()
        legacy = LegacyNominationSubmission(edition_id=edition_id, nominee_id=nominee.id, submitter_hash='hash-one', submitted_at=NOW)
        db.add(legacy); db.flush()
        db.add(LegacyNominationDetail9E(submission_id=legacy.id, team='Original crew', justification='Original reason'))
    migrate_nomination_history(engine)
    migrate_nomination_history(engine)
    assert not nominate(factory, edition_id, now=NOW + timedelta(hours=23))
    assert nominate(factory, edition_id, now=NOW + timedelta(hours=24), name='Historical Dancer')
    with factory() as db:
        assert db.query(LegacyNominationSubmission).count() == 1
        assert db.query(LegacyNominationDetail9E).one().team == 'Original crew'
        assert db.query(NominationDetail9E).one().justification == 'Original reason'
        assert db.query(DCANominationSubmission).count() == 2
        edition = db.get(__import__('dca_rebuild.models', fromlist=['DCAEdition']).DCAEdition, edition_id)
        nominees, support = get_counts(db, edition)
        assert nominees[1][0]['count'] == 2
        assert support[1] == 1  # repeat support never inflates write-in qualification
    assert inspect(engine).get_unique_constraints('ledger_dca_nomination_submissions')[0]['name'] == 'ledger_uq_dca_nomination_submitter_nominee'


def test_utc_and_exact_boundary():
    assert remaining_seconds(NOW.replace(tzinfo=timezone.utc), NOW + timedelta(hours=23)) == 3600
    assert remaining_seconds(NOW, NOW + timedelta(hours=24)) == 0


def test_email_first_history_and_return_to_grid(website, database):
    client = website.test_client()
    first = client.get(PATH)
    assert b'name="email"' in first.data
    assert b'data-category-id' not in first.data
    assert client.post(PATH, data={'category_id': 1, 'name': 'Dancer'}).status_code == 400
    token = identify(client, ' PERSON@example.com ')
    grid = client.get(PATH)
    assert grid.data.count(b'data-category-id=') == 27
    assert b'person@example.com' not in grid.data
    assert 'no-store' in grid.headers['Cache-Control']
    result = client.post(PATH, data=dict(csrf_token=token, category_id=1, name='Dancer One', team='Crew'), follow_redirects=True)
    assert b'Nomination received for moderation' in result.data
    assert b'Already nominated / cooldown active' in result.data
    assert b'Dancer One' in result.data  # own pending history
    assert b'CATEGORIES AVAILABLE' in result.data
    assert b'Return tomorrow' not in result.data
    assert result.data.count(b'data-category-id=') == 27
    assert client.post(PATH, data=dict(csrf_token=token, category_id=2, name='Dancer Two')).status_code == 302
    assert client.post(PATH, data=dict(csrf_token=token, category_id=1, name='Other')).status_code == 302
    with database[1]() as db:
        assert db.query(DCANominationSubmission).count() == 2
    # Returning with the same normalized email retrieves history on a new browser.
    other = website.test_client(); identify(other)
    assert b'Already nominated / cooldown active' in other.get(PATH).data
    with client.session_transaction() as sess:
        assert 'person@example.com' not in repr(dict(sess))


def test_validation_gates_and_skips(website, monkeypatch):
    client = website.test_client(); token = identify(client)
    assert client.post(PATH, data=dict(csrf_token=token, category_id=999, name='Dancer')).status_code == 400
    assert client.post(PATH, data=dict(csrf_token=token, category_id=1, name='!')).status_code == 400
    response = client.post(PATH, data=dict(csrf_token=token, category_id=1, action='skip'), follow_redirects=True)
    assert b'Skipped this visit' in response.data
    monkeypatch.setenv('DCA_2026_NOMINATIONS_CLOSE_AT', '2020-01-01T00:00:00Z')
    assert client.post(PATH, data=dict(csrf_token=token, category_id=2, name='Dancer')).status_code == 403
    monkeypatch.setenv('DCA_2026_NOMINATIONS_ENABLED', 'false')
    assert b'NOMINATIONS ARE NOT OPEN YET' in client.get(PATH).data


def test_admin_moderation_counts_and_auth(website, database):
    client = website.test_client(); token = identify(client)
    client.post(PATH, data=dict(csrf_token=token, category_id=1, name='Dancer One'))
    assert client.get('/admin/dca/nominations').status_code == 302
    with client.session_transaction() as sess:
        sess['ledger_admin_authenticated'] = True
        sess['dca_moderation_csrf'] = 'admin-token'
    response = client.get('/admin/dca/nominations')
    assert response.status_code == 200 and b'Dancer One' in response.data
    with database[1]() as db:
        nominee_id = db.query(DCANominee).one().id
    admin_path = '/admin/dca/nominations'
    data = dict(action='review', nominee_id=nominee_id, decision='approved')
    assert client.post(admin_path, data=data).status_code == 400
    data['csrf_token'] = 'admin-token'
    assert client.post(admin_path, data=data).status_code == 302
    assert b'Dancer One' in client.get(PATH + '?category=1').data
    data['decision'] = 'rejected'
    assert client.post(admin_path, data=data).status_code == 302
    with database[1]() as db:
        assert db.query(DCANominationSubmission).count() == 1
        assert db.query(DCANominee).one().moderation_status == 'rejected'


def test_writein_qualification_and_top25_preserved(website, database, monkeypatch):
    from dca_rebuild.models import DCAEdition
    from dca_rebuild.phase9e import CategoryStage9E
    _, factory, edition_id = database
    with factory.begin() as db:
        for index in range(5):
            nominee = DCANominee(edition_id=edition_id, category_id=26, name=f'Nominee {index}', normalized_name=f'nominee {index}', moderation_status='approved')
            db.add(nominee); db.flush()
            for support in range(4):
                db.add(DCANominationSubmission(edition_id=edition_id, nominee_id=nominee.id, submitter_hash=f'hash-{index}-{support}', submitted_at=NOW))
    with factory() as db:
        rules, _, _ = qualification(db, db.get(DCAEdition, edition_id))
        assert rules[26]['met'] and rules[26]['required'] == 20
    client = website.test_client()
    with client.session_transaction() as sess:
        sess['ledger_admin_authenticated'] = True
        sess['dca_moderation_csrf'] = 'admin-token'
    path = '/admin/dca/phase9e/confirm-qualified'
    data = dict(category_id=26, csrf_token='admin-token')
    assert client.post(path, data=data).status_code == 409  # must close first
    monkeypatch.setenv('DCA_2026_NOMINATIONS_CLOSE_AT', '2020-01-01T00:00:00Z')
    assert client.post(path, data=data).status_code == 302
    with factory() as db:
        assert db.query(CategoryStage9E).filter_by(stage='top25').count() == 25
        assert db.query(CategoryStage9E).filter_by(category_id=26).one().stage == 'qualified'
        assert db.query(DCANominationSubmission).count() == 20


def test_invalid_email_and_change_identity(website):
    client = website.test_client()
    client.get(PATH)
    with client.session_transaction() as sess:
        token = sess['lf9e_nomination_csrf']
    assert client.post(PATH, data=dict(csrf_token=token, action='identify', email='invalid')).status_code == 400
    identify(client)
    response = client.post(PATH, data=dict(csrf_token=token, action='change-email'), follow_redirects=True)
    assert b'data-category-id' not in response.data


def test_concurrent_historical_import(database):
    engine, factory, edition = database
    with factory.begin() as db:
        nominee = DCANominee(edition_id=edition, category_id=1, name='Legacy Dancer', normalized_name='legacy dancer', moderation_status='pending')
        db.add(nominee); db.flush()
        db.add(LegacyNominationSubmission(edition_id=edition, nominee_id=nominee.id, submitter_hash='hash-one', submitted_at=NOW))
    barrier = Barrier(2)
    def migrate(_):
        barrier.wait(); migrate_nomination_history(engine)
    with ThreadPoolExecutor(max_workers=2) as pool:
        list(pool.map(migrate, range(2)))
    with factory() as db:
        assert db.query(DCANominationSubmission).count() == 1
        assert db.query(LegacyNominationSubmission).count() == 1
