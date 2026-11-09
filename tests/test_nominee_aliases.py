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


def test_owner_confirmed_names_and_role_scoped_aye_jae():
    assert canonical_nominee_name('DSKI') == ('D Ski', 'd ski')
    assert canonical_nominee_name('D ski') == ('D Ski', 'd ski')
    assert canonical_nominee_name('BSN') == ('BSNYEA', 'bsnyea')
    assert canonical_nominee_name('D rillz') == ('D Rillz', 'd rillz')
    assert canonical_nominee_name('Ty Shots') == ('Ty Shotz', 'ty shotz')
    assert canonical_nominee_name('Noah lot') == ('Noahlot', 'noahlot')
    assert canonical_nominee_name('Noahalot') == ('Noahlot', 'noahlot')
    assert canonical_nominee_name('Aye Jae', category_name='Producer of The Year') == ('Aye Jae Beats', 'aye jae beats')
    assert canonical_nominee_name('Aye Jae Beats', category_name='Best Dancer') == ('Aye Jae', 'aye jae')


def test_owner_confirmed_name_aliases_sum_counts_without_deleting(database):
    _, factory, edition_id = database
    with factory.begin() as db:
        for name, count in (('DSKI', 1), ('D ski', 4)):
            row = DCANominee(edition_id=edition_id, category_id=1, name=name,
                             normalized_name=name.casefold(), moderation_status='pending')
            db.add(row); db.flush()
            for i in range(count):
                db.add(DCANominationSubmission(edition_id=edition_id, nominee_id=row.id,
                                                submitter_hash=f'{name}-{i}'))
    with factory() as db:
        nominees, _ = get_counts(db, db.get(DCAEdition, edition_id), include_pending=True)
        d_ski = [n for n in nominees[1] if n['name'] == 'D Ski']
        assert len(d_ski) == 1
        assert d_ski[0]['count'] == 5
        assert len(d_ski[0]['ids']) == 2
        assert db.query(DCANominee).count() == 2
        assert db.query(DCANominationSubmission).count() == 5


def test_producer_writein_aliases_roll_up_counts_and_block_cross_category_cooldown(database):
    from dca_rebuild.phase9e import stages_for, writein_category_key, writein_category_label
    _, factory, edition_id = database
    with factory.begin() as db:
        canonical = db.get(DCACategory, 26)
        alias = db.get(DCACategory, 27)
        canonical.name = 'Producer of the Year'
        canonical.normalized_name = 'producer of the year'
        alias.name = 'Producer Of The Year Award'
        alias.normalized_name = 'producer of the year award'
    assert writein_category_key('Producer Of The Year Award') == 'producer of the year'
    assert writein_category_label('Producer of the Year') == 'Producer of The Year'
    with factory.begin() as db:
        row = DCANominee(edition_id=edition_id, category_id=27,
                         name='Aye Jae', normalized_name='aye jae', moderation_status='pending')
        db.add(row); db.flush()
        db.add(DCANominationSubmission(edition_id=edition_id, nominee_id=row.id,
                                        submitter_hash='prior', submitted_at=__import__('datetime').datetime.utcnow()))
    with factory() as db:
        edition = db.get(DCAEdition, edition_id)
        stages = stages_for(db, edition)
        assert sum(1 for _, cat in stages if 'producer of' in cat.name.casefold()) == 1
        nominees, support = get_counts(db, edition, include_pending=True)
        assert nominees[26][0]['name'] == 'Aye Jae Beats'
        assert nominees[26][0]['count'] == 1
        assert 27 not in nominees
        assert support[26] == 1
        assert db.query(DCANominee).count() == 1
    nominee, created = None, None
    with factory.begin() as db:
        nominee, created = add_nomination(db, edition_id=edition_id, category_id=26,
                                          name='Aye Jae Beats', submitter_hash='new')
        assert created
    with factory() as db:
        counts, _ = get_counts(db, db.get(DCAEdition, edition_id), include_pending=True)
        assert counts[26][0]['count'] == 2
    with factory() as db:
        _, again = add_nomination(db, edition_id=edition_id, category_id=27,
                                   name='Aye Jae', submitter_hash='new')
        assert not again
        db.rollback()
    with factory() as db:
        assert db.query(DCANominee).count() == 1
        assert db.query(DCANominationSubmission).count() == 2
