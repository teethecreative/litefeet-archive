"""Confirmed alias rollup and ambiguous-name pre-submit safeguards."""
from dca_rebuild.models import DCACategory, DCAEdition, DCANominee, DCANominationSubmission
from dca_rebuild.nomination_service import candidate_matches, canonical_nominee_name, add_nomination
from dca_rebuild.phase9e import get_counts
from conftest import identify

PATH = '/awards/dancers-choice/nominations'


def seed_astro_history(database):
    _, factory, edition_id = database
    with factory.begin() as db:
        canonical = DCANominee(
            edition_id=edition_id, category_id=1,
            name='D Astro', normalized_name='d astro', moderation_status='pending'
        )
        alternate = DCANominee(
            edition_id=edition_id, category_id=1,
            name='A astro', normalized_name='a astro', moderation_status='pending'
        )
        db.add_all([canonical, alternate])
        db.flush()
        canonical_id, alias_id = canonical.id, alternate.id
        for number in range(9):
            db.add(DCANominationSubmission(
                edition_id=edition_id, nominee_id=canonical_id,
                submitter_hash='original-d-'+str(number),
            ))
        db.add(DCANominationSubmission(
            edition_id=edition_id, nominee_id=alias_id,
            submitter_hash='original-a-0',
        ))
    return canonical_id, alias_id


def test_explicit_alias_is_recognized_and_existing_records_are_preserved(database):
    _, factory, edition_id = database
    canonical_id, alias_id = seed_astro_history(database)
    assert canonical_nominee_name('  A ASTRO ') == ('D Astro', 'd astro')
    with factory() as db:
        edition = db.get(DCAEdition, edition_id)
        nominees, support = get_counts(db, edition, include_pending=True)
        matches = [x for x in nominees[1] if x['name'] == 'D Astro']
        assert len(matches) == 1
        assert matches[0]['id'] == canonical_id
        assert set(matches[0]['ids']) == {canonical_id, alias_id}
        assert matches[0]['count'] == 10
        assert support[1] == 10
        assert db.query(DCANominee).count() == 2
        assert db.query(DCANominationSubmission).count() == 10
        hints = candidate_matches(db, category_id=1, name='A Astro')
        assert hints and hints[0]['name'] == 'D Astro'
        assert hints[0]['type'] == 'existing'


def test_form_checks_alias_before_submission_and_adds_to_canonical_person(website, database):
    canonical_id, alias_id = seed_astro_history(database)
    client = website.test_client()
    token = identify(client, 'new-supporter@example.com')
    response = client.get('/awards/dancers-choice/nominee-name-check',
                          query_string={'category_id':1,'name':'A Astro'})
    assert response.status_code == 200
    data = response.get_json()
    assert data['already_listed'] is True
    assert data['canonical_name'] == 'D Astro'
    category = client.get(PATH+'?category=1').get_data(as_text=True)
    assert 'NOMINATE SOMEONE' in category
    assert category.index('NOMINATE SOMEONE') < category.index('SUGGESTIONS')
    assert '10 NOMINATIONS' in category
    assert 'A astro' not in category
    assert client.post(PATH, data={
        'csrf_token':token,'category_id':1,'name':'A Astro',
        'reason':'Participated in documented LiteFeet events during 2026.'
    }).status_code == 302
    with database[1]() as db:
        assert db.query(DCANominee).count() == 2
        assert db.query(DCANominationSubmission).count() == 11
        last = db.query(DCANominationSubmission).order_by(
            DCANominationSubmission.id.desc()).first()
        assert last.nominee_id == canonical_id


def test_close_names_need_confirmation_and_are_not_auto_merged(website, database):
    seed_astro_history(database)
    client = website.test_client()
    token = identify(client, 'different-supporter@example.com')
    check = client.get('/awards/dancers-choice/nominee-name-check',
                       query_string={'category_id':1,'name':'D Astr0'})
    assert check.status_code == 200
    hint = check.get_json()
    assert hint['requires_confirmation'] is True
    assert hint['already_listed'] is False
    posted = client.post(PATH, data={
        'csrf_token':token,'category_id':1,'name':'D Astr0',
        'reason':'Participated in documented LiteFeet events during 2026.'
    })
    assert posted.status_code == 303
    with database[1]() as db:
        assert db.query(DCANominationSubmission).count() == 10
    posted = client.post(PATH, data={
        'csrf_token':token,'category_id':1,'name':'D Astr0','confirm_distinct':'1',
        'reason':'Participated in documented LiteFeet events during 2026.'
    })
    assert posted.status_code == 302
    with database[1]() as db:
        assert db.query(DCANominee).count() == 3
        assert db.query(DCANominationSubmission).count() == 11
