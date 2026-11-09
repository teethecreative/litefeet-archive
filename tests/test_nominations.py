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
    result = client.post(PATH, data=dict(csrf_token=token, category_id=1, name='Dancer One', reason='Attended LiteFeet sessions this season.', team='Crew'), follow_redirects=True)
    assert b'Nomination received.' in result.data
    category_page = client.get(PATH + '?category=1')
    assert b'Already nominated / cooldown active' in category_page.data
    assert b'Dancer One' in category_page.data  # pending suggestions appear immediately
    assert b'NOMINEE STANDINGS' in result.data
    assert b'Your nomination summary' not in result.data
    assert b'Return tomorrow' not in result.data
    assert b'Dancer One' in result.data
    assert client.get(PATH).data.count(b'data-category-id=') == 25
    assert client.post(PATH, data=dict(csrf_token=token, category_id=2, name='Dancer Two', reason='Contributed to LiteFeet events in 2026.')).status_code == 302
    assert client.post(PATH, data=dict(csrf_token=token, category_id=1, name='Other', reason='Participated in LiteFeet this year.')).status_code == 302
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
    assert response.status_code == 200
    assert b'Nominate for the 2026 Awards' in response.data
    assert b'Your nomination activity' not in response.data
    with client.session_transaction() as sess:
        assert 1 in sess['lf9e_skipped']
    monkeypatch.setenv('DCA_2026_NOMINATIONS_CLOSE_AT', '2020-01-01T00:00:00Z')
    assert client.post(PATH, data=dict(csrf_token=token, category_id=2, name='Dancer')).status_code == 403
    monkeypatch.setenv('DCA_2026_NOMINATIONS_ENABLED', 'false')
    assert b'NOMINATIONS ARE NOT OPEN YET' in client.get(PATH).data


def test_admin_moderation_counts_and_auth(website, database):
    client = website.test_client(); token = identify(client)
    client.post(PATH, data=dict(csrf_token=token, category_id=1, name='Dancer One', reason='Active at LiteFeet sessions this season.'))
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
    visitor.post(PATH, data=dict(csrf_token=token, category_id=1, name='Suggested Dancer', reason='Joined LiteFeet sessions this year.'))
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
    second.post(PATH, data=dict(csrf_token=token, category_id=1, name='Dancer Beta', reason='Active in LiteFeet community events.'))
    third = website.test_client(); token = identify(third, 'third@example.com')
    third.post(PATH, data=dict(csrf_token=token, category_id=1, name='Dancer Alpha', reason='Participated in several LiteFeet sessions.'))
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
    client.post(PATH, data=dict(csrf_token=token, category_id=1, name='Dancer One', reason='Active at LiteFeet sessions this season.'))
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
    assert 'Submit one nomination per category every rolling 24 hours.' in html
    assert 'become the finalists' in html
    assert 'Your previous nominations' not in html
    with client.session_transaction() as sess:
        token = sess['lf9e_nomination_csrf']
    assert client.post(PATH, data=dict(csrf_token=token, category_id=1, name='Dancer One', reason='Active at LiteFeet sessions this season.')).status_code == 400
    identify(client)
    assert b'Nominate for the 2026 Awards' in client.get(PATH).data


def test_category_grid_has_clear_invitation_without_activity_dashboard(website):
    client = website.test_client()
    identify(client)
    response = client.get(PATH)
    html = response.get_data(as_text=True)
    assert response.status_code == 200
    assert '<h1 class="lf9e-nomination-heading">Nominate for the 2026 Awards</h1>' in html
    assert 'Nominations are open for suggestions.' in html
    assert 'Suggest a new entry or support an existing nominee.' in html
    assert 'the top five eligible nominees in each category advance to the final vote.' in html
    assert 'You can submit one nomination per category every rolling 24 hours.' in html
    assert 'Your cooldown is shown on each category before you open it.' not in html
    assert 'Your nomination activity' not in html
    assert 'lf9e-summary-stats' not in html
    assert 'NOMINATIONS SUBMITTED' not in html
    assert 'SKIPPED THIS VISIT' not in html
    assert 'id="official-title"' in html
    assert html.count('data-category-id=') == 25
    assert 'WRITE-IN CATEGORIES' in html

def test_qualification_reason_required_and_missing_list(website, database):
    from dca_rebuild.models import DCANominee, DCANominationSubmission
    from dca_rebuild.phase9e import nominees_missing_reasons
    client = website.test_client()
    token = identify(client)
    assert client.post(PATH, data=dict(csrf_token=token, category_id=1,
                name='No Explanation')).status_code == 400
    assert client.post(PATH, data=dict(csrf_token=token, category_id=1,
                name='Qualified Dancer', reason='Attended community battles in 2026.')).status_code == 302
    with database[1]() as db:
        assert db.query(DCANominationSubmission).count() == 1
        assert nominees_missing_reasons(db, db.get(
            __import__('dca_rebuild.models', fromlist=['DCAEdition']).DCAEdition,
            database[2])) == []
    anonymous = website.test_client()
    page = anonymous.get('/awards/dancers-choice/nomination-reasons')
    assert page.status_code == 200
    assert b'November 2025' in page.data
    assert b'Nominees needing qualification details' in page.data


def test_old_nominee_can_receive_moderated_reason_without_nomination(website, database):
    from dca_rebuild.models import DCANominee, DCANominationSubmission
    from dca_rebuild.phase9e import NomineeQualificationReason9E, nominees_missing_reasons
    _, factory, edition_id = database
    with factory.begin() as db:
        nominee = DCANominee(edition_id=edition_id, category_id=1,
                            name='Historical Nominee', normalized_name='historical nominee',
                            moderation_status='approved')
        db.add(nominee); db.flush()
        nominee_id = nominee.id
        db.add(DCANominationSubmission(edition_id=edition_id, nominee_id=nominee_id,
                                       submitter_hash='old-submitter', submitted_at=NOW))
    client = website.test_client()
    page = client.get('/awards/dancers-choice/nomination-reasons')
    assert b'Historical Nominee' in page.data
    with client.session_transaction() as session:
        token = session['lf9e_nomination_csrf']
    result = client.post('/awards/dancers-choice/nomination-reasons', data=dict(
        csrf_token=token, nominee_id=nominee_id, email='test@example.com',
        reason='Attended recorded LiteFeet events during 2026.'))
    assert result.status_code == 303
    with factory() as db:
        assert db.query(DCANominationSubmission).count() == 1
        assert db.query(NomineeQualificationReason9E).one().moderation_status == 'pending'
        assert len(nominees_missing_reasons(db, db.get(
            __import__('dca_rebuild.models', fromlist=['DCAEdition']).DCAEdition, edition_id))) == 1
        db.query(NomineeQualificationReason9E).one().moderation_status = 'verified'
        db.commit()
    with factory() as db:
        assert not nominees_missing_reasons(db, db.get(
            __import__('dca_rebuild.models', fromlist=['DCAEdition']).DCAEdition, edition_id))


def test_all_existing_writein_categories_show_support_actions(website):
    client = website.test_client()
    html = client.get('/write-ins').get_data(as_text=True)
    assert html.count('SUPPORT CATEGORY') >= 2
    assert 'OPEN FOR SUPPORT' in html
    assert 'NOMINATIONS CLOSED' not in html


def test_unstaged_historical_writein_can_be_supported_after_email(website, database):
    from dca_rebuild.models import DCAEdition, DCACategory
    _, factory, _ = database
    with factory.begin() as db:
        previous = DCAEdition(year=2023, title='Previous awards', phase='closed')
        db.add(previous); db.flush()
        db.add(DCACategory(edition_id=previous.id, name='Best Workshop',
                           normalized_name='best workshop', source_type='returning',
                           status='official'))
    client = website.test_client()
    page = client.get('/write-ins')
    html = page.get_data(as_text=True)
    assert 'Best Workshop' in html
    assert 'SUPPORT CATEGORY' in html
    with client.session_transaction() as sess:
        token = sess['lf9e_writeins_csrf']
    result = client.post('/awards/dancers-choice/write-ins/activate',
                         data=dict(csrf_token=token, category='Best Workshop'))
    assert result.status_code == 302
    import urllib.parse
    loc = urllib.parse.urlparse(result.headers['Location'])
    assert loc.path == PATH and 'category=' in loc.query
    landing = client.get(result.headers['Location']).get_data(as_text=True)
    assert 'name="return_category"' in landing
    token = identify(client)
    with client.session_transaction() as sess:
        target = db_id = None
    from urllib.parse import parse_qs
    target = parse_qs(loc.query)['category'][0]
    continuation = client.post(PATH, data=dict(action='identify', email='user2@example.com',
                                                csrf_token=token, return_category=target))
    assert continuation.status_code == 302
    assert 'category=' + target in continuation.headers['Location']


def test_category_grid_does_not_prompt_for_email_to_show_cooldown(website):
    """Unauthenticated visitors get email entry, not 25 repeated cooldown prompts."""
    client = website.test_client()
    anonymous = client.get(PATH).get_data(as_text=True)
    assert 'name="email"' in anonymous
    assert 'IDENTIFY TO SEE COOLDOWN' not in anonymous.upper()
    assert 'data-category-id=' not in anonymous

    identify(client)
    grid = client.get(PATH).get_data(as_text=True)
    assert grid.count('data-category-id=') == 25
    assert 'IDENTIFY TO SEE COOLDOWN' not in grid.upper()
    assert 'AVAILABLE NOW' in grid

    standings = website.test_client().get(PATH + '?view=results').get_data(as_text=True)
    assert 'IDENTIFY TO SEE COOLDOWN' not in standings.upper()


def test_event_of_2023_category_renamed_only_for_2026(database):
    from dca_rebuild.models import DCAEdition, DCACategory
    from dca_rebuild.phase9e import correct_2026_event_category_title
    _, factory, edition_id = database
    with factory.begin() as db:
        event = DCACategory(edition_id=edition_id, name='Best Event of 2023',
                            normalized_name='best event of 2023',
                            source_type='returning', status='official')
        db.add(event)
        db.flush()
        original_id = event.id
    assert correct_2026_event_category_title(factory)
    assert not correct_2026_event_category_title(factory)
    with factory() as db:
        renamed = db.get(DCACategory, original_id)
        assert renamed.name == 'Best Event of the Year'
        assert renamed.normalized_name == 'best event of the year'
        assert renamed.id == original_id



def test_writein_directory_shows_same_nominee_totals_as_standings(website, database):
    """Published write-ins expose expandable nominee names and matching totals."""
    _, factory, edition_id = database
    assert nominate(factory, edition_id, category=26, who='first-supporter',
                    name='Write In Dancer')
    assert nominate(factory, edition_id, category=26, who='second-supporter',
                    name='Write In Dancer')
    client = website.test_client()
    html = client.get('/write-ins').get_data(as_text=True)
    assert 'View nominees (1)' in html
    assert 'Write In Dancer' in html
    assert 'view=results' in html and 'suggestion=' in html
    assert '<td>2</td>' in html
    standings = client.get(PATH + '?view=results').get_data(as_text=True)
    assert 'Write In Dancer' in standings
    assert '<td>2</td>' in standings


def test_done_from_grid_clears_email_and_keeps_nomination_cooldown(website, database):
    """Done changes browser identity, not permanent nomination rules."""
    client = website.test_client()
    token = identify(client, 'first@example.com')
    nomination = client.post(PATH, data={
        'csrf_token': token, 'category_id': 1, 'name': 'Dancer One',
        'reason': 'Participated in documented LiteFeet events during 2026.'
    })
    assert nomination.status_code == 302
    with database[1]() as db:
        assert db.query(DCANominationSubmission).count() == 1
    grid = client.get(PATH).get_data(as_text=True)
    assert 'DONE / VIEW NOMINEE STANDINGS' in grid
    assert 'name="action" value="done"' in grid
    bad_token = client.post(PATH, data={
        'csrf_token': 'invalid', 'action': 'done', 'next': 'standings'
    })
    assert bad_token.status_code == 400
    with client.session_transaction() as sess:
        assert sess.get('lf9e_recent_hash')

    done = client.post(PATH, data={
        'csrf_token': token, 'action': 'done', 'next': 'standings'
    })
    assert done.status_code == 303
    assert done.headers['Location'].endswith('?view=results')
    standings = client.get(done.headers['Location']).get_data(as_text=True)
    assert 'NOMINEE STANDINGS' in standings
    assert 'class="lf9e-done-form"' not in standings
    with client.session_transaction() as sess:
        assert 'lf9e_recent_hash' not in sess
        assert 'lf9e_skipped' not in sess
    entry = client.get(PATH).get_data(as_text=True)
    assert 'name="email"' in entry
    assert 'data-category-id=' not in entry
    with database[1]() as db:
        assert db.query(DCANominationSubmission).count() == 1

    # Same email still has the same rolling 24-hour category cooldown.
    identify(client, 'first@example.com')
    assert 'Already nominated / cooldown active' in client.get(
        PATH + '?category=1').get_data(as_text=True)
    client.post(PATH, data={'csrf_token': token, 'action': 'done'})
    # Different email gets its own independent category availability.
    identify(client, 'second@example.com')
    grid = client.get(PATH).get_data(as_text=True)
    assert 'AVAILABLE NOW' in grid


def test_done_on_standings_returns_to_email_entry(website):
    client = website.test_client()
    token = identify(client, 'first@example.com')
    page = client.get(PATH + '?view=results').get_data(as_text=True)
    assert '>Done</button>' in page
    assert 'Reset email' not in page
    response = client.post(PATH, data={
        'csrf_token': token, 'action': 'done'
    }, follow_redirects=True)
    assert response.status_code == 200
    assert b'name="email"' in response.data
    assert b'data-category-id=' not in response.data
    with client.session_transaction() as sess:
        assert 'lf9e_recent_hash' not in sess
