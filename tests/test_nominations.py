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
    assert grid.data.count(b'data-category-id=') == 25
    assert b'WRITE-IN CATEGORIES' in grid.data
    assert b'person@example.com' not in grid.data
    assert 'no-store' in grid.headers['Cache-Control']
    result = client.post(PATH, data=dict(csrf_token=token, category_id=1, name='Dancer One', team='Crew'), follow_redirects=True)
    assert b'Nomination received.' in result.data
    category_page = client.get(PATH + '?category=1')
    assert b'Already nominated / cooldown active' in category_page.data
    assert b'Dancer One' in category_page.data  # pending suggestions appear immediately
    assert b'NOMINEE STANDINGS' in result.data
    assert b'Your nomination summary' not in result.data
    assert b'Return tomorrow' not in result.data
    assert b'Dancer One' in result.data
    assert client.get(PATH).data.count(b'data-category-id=') == 25
    assert client.post(PATH, data=dict(csrf_token=token, category_id=2, name='Dancer Two')).status_code == 302
    assert client.post(PATH, data=dict(csrf_token=token, category_id=1, name='Other')).status_code == 302
    with database[1]() as db:
        assert db.query(DCANominationSubmission).count() == 2
    # Returning with the same normalized email retrieves history on a new browser.
    other = website.test_client(); identify(other)
    assert b'Already nominated / cooldown active' in other.get(PATH + '?category=1').data
    with client.session_transaction() as sess:
        assert 'person@example.com' not in repr(dict(sess))


def test_validation_gates_and_skips(website, monkeypatch):
    client = website.test_client(); token = identify(client)
    assert client.post(PATH, data=dict(csrf_token=token, category_id=999, name='Dancer')).status_code == 400
    assert client.post(PATH, data=dict(csrf_token=token, category_id=1, name='!')).status_code == 400
    response = client.post(PATH, data=dict(csrf_token=token, category_id=1, action='skip'), follow_redirects=True)
    assert b'<strong>1</strong><span>SKIPPED THIS VISIT' in response.data
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


def test_category_names_then_suggestions_and_private_details(website, database):
    client = website.test_client(); token = identify(client)
    grid = client.get(PATH).get_data(as_text=True)
    assert 'USE A DIFFERENT EMAIL' not in grid
    # Categories are compact disclosures: the name and eligibility are visible
    # before opening, with nominees nested inside the expandable panel.
    assert 'data-category-id="1"' in grid
    assert '<summary>' in grid
    assert 'Category 1' in grid
    assert 'AVAILABLE NOW' in grid
    assert 'lfv5-category-panel' in grid
    client.post(PATH, data=dict(csrf_token=token, category_id=1, name='Suggested Dancer',
                team='Original Crew', location='Harlem', instagram='dancer.one',
                reason='A thoughtful nomination.'))
    # Pending is immediately public; classification and qualification stay separate.
    visitor = website.test_client(); identify(visitor, 'another@example.com')
    category = visitor.get(PATH + '?category=1').get_data(as_text=True)
    assert 'Suggested Dancer' in category
    assert 'approved' not in category.lower()
    assert 'name="name"' not in category  # form comes after the Nominate action
    with database[1]() as db:
        nominee = db.query(DCANominee).one()
        nominee_id = nominee.id
        assert nominee.moderation_status == 'pending'
        private_hash = db.query(DCANominationSubmission).one().submitter_hash
    details = visitor.get(PATH + f'?category=1&suggestion={nominee_id}').get_data(as_text=True)
    for value in ['Original Crew', 'Harlem', '@dancer.one', 'A thoughtful nomination.']:
        assert value in details
    assert 'person@example.com' not in details and 'another@example.com' not in details
    assert private_hash not in details
    form = visitor.get(PATH + f'?category=1&suggestion={nominee_id}&nominate=1').get_data(as_text=True)
    assert 'value="Suggested Dancer"' in form
    assert visitor.get(PATH + f'?category=2&suggestion={nominee_id}').status_code == 404
    assert visitor.get(PATH + '?category=1&suggestion=99999').status_code == 404
    assert visitor.get(PATH + '?category=99999').status_code == 404
    # A second visitor supports the existing suggestion without a duplicate nominee.
    with visitor.session_transaction() as sess:
        token = sess['lf9e_nomination_csrf']
    visitor.post(PATH, data=dict(csrf_token=token, category_id=1, name='Suggested Dancer'))
    with database[1]() as db:
        assert db.query(DCANominee).count() == 1
        assert db.query(DCANominationSubmission).count() == 2


def test_public_suggestions_preserve_moderation_and_qualification(website, database):
    from dca_rebuild.models import DCAEdition
    _, factory, edition_id = database
    with factory.begin() as db:
        for index, status in enumerate(['pending', 'approved', 'rejected']):
            nominee = DCANominee(edition_id=edition_id, category_id=26,
                name=f'{status.title()} Dancer', normalized_name=f'{status} dancer', moderation_status=status)
            db.add(nominee); db.flush()
            db.add(DCANominationSubmission(edition_id=edition_id, nominee_id=nominee.id, submitter_hash=f'private-{index}', submitted_at=NOW))
            if status == 'rejected': rejected_id = nominee.id
        db.flush()
    with factory() as db:
        edition = db.get(DCAEdition, edition_id)
        public, _ = get_counts(db, edition, include_pending=True)
        assert {x['name'] for x in public[26]} == {'Pending Dancer', 'Approved Dancer'}
        moderated, _ = get_counts(db, edition)
        assert {x['name'] for x in moderated[26]} == {'Approved Dancer'}
        rules, _, _ = qualification(db, edition)
        assert rules[26]['eligible_nominees'] == 1
    client = website.test_client(); identify(client)
    response = client.get(PATH + '?category=26').get_data(as_text=True)
    assert 'Pending Dancer' in response and 'Approved Dancer' in response
    assert 'Rejected Dancer' not in response
    assert client.get(PATH + f'?category=26&suggestion={rejected_id}').status_code == 404
    with factory() as db:
        assert db.query(DCANominationSubmission).count() == 3


def test_submission_opens_community_standings_not_personal_summary(website, database):
    first = website.test_client(); token = identify(first, 'first@example.com')
    response = first.post(PATH, data=dict(csrf_token=token, category_id=1, name='Dancer Alpha', reason='Great community work.'))
    assert response.status_code == 302 and 'view=results' in response.headers['Location']
    second = website.test_client(); token = identify(second, 'second@example.com')
    second.post(PATH, data=dict(csrf_token=token, category_id=1, name='Dancer Beta'))
    third = website.test_client(); token = identify(third, 'third@example.com')
    third.post(PATH, data=dict(csrf_token=token, category_id=1, name='Dancer Alpha'))
    # A visitor without an email sees the same combined totals.
    visitor = website.test_client()
    page = visitor.get(PATH + '?view=results')
    assert page.status_code == 200
    main = page.get_data(as_text=True).split('<main', 1)[1].split('</main>', 1)[0]
    assert 'NOMINEE STANDINGS' in main
    assert main.index('Dancer Alpha') < main.index('Dancer Beta')
    assert '</a></th><td>2</td>' in main and '</a></th><td>1</td>' in main
    for private_label in ['Your nomination summary', 'Your previous nominations', 'ON COOLDOWN', 'first@example.com', 'second@example.com', 'third@example.com']:
        assert private_label not in main
    assert 'name="email"' not in main
    with database[1]() as db:
        nominee_id = db.query(DCANominee).filter_by(name='Dancer Alpha').one().id
        assert db.query(DCANominationSubmission).count() == 3
    detail = visitor.get(PATH + f'?view=results&category=1&suggestion={nominee_id}').get_data(as_text=True)
    assert 'Great community work.' in detail
    assert 'Back to standings' in detail
    assert 'cooldown active' not in detail


def test_standings_show_all_categories_even_without_nominations(website):
    client = website.test_client()
    before = client.get(PATH + '?view=results').get_data(as_text=True)
    assert before.count('class="lf9e-standings-category lfv5-category-disclosure"') == 27
    assert before.count('NO NOMINATIONS YET.') == 27
    assert 'id="standings-25"' in before and 'id="standings-27"' in before
    token = identify(client)
    client.post(PATH, data=dict(csrf_token=token, category_id=1, name='Dancer One'))
    after = client.get(PATH + '?view=results').get_data(as_text=True)
    assert after.count('class="lf9e-standings-category lfv5-category-disclosure"') == 27
    assert after.count('NO NOMINATIONS YET.') == 26
    assert 'Dancer One' in after and '</a></th><td>1</td>' in after


def test_introduction_lists_process_and_categories_before_email(website):
    client = website.test_client()
    response = client.get(PATH)
    assert response.status_code == 200
    html = response.get_data(as_text=True)
    assert html.index('id="intro-title"') < html.index('id="lf9e-intro-categories"') < html.index('id="lf9e-email-start"')
    assert 'Category 25' in html
    assert 'WRITE-IN CATEGORIES' in html
    # Community write-ins have their own searchable page rather than appearing in the Top 25 preview.
    assert 'Category 26' not in html and 'Category 27' not in html
    assert 'One nomination per category every 24 hours.' in html
    assert 'advance to final voting' in html
    assert 'Your previous nominations' not in html
    with client.session_transaction() as sess:
        token = sess['lf9e_nomination_csrf']
    assert client.post(PATH, data=dict(csrf_token=token, category_id=1, name='Dancer One')).status_code == 400
    identify(client)
    assert b'CHOOSE YOUR CATEGORY' in client.get(PATH).data
