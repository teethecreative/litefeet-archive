"""Public Archive content, progressive browse, and moderated verification tests."""
from dca_rebuild.archive_catalog import all_records, browse, find_record, listing_payload
from dca_rebuild.models import VaultArchiveVerification, DCACategory, DCANominationSubmission


def test_catalog_has_real_source_rows_and_distinct_editions():
    entries = all_records()
    assert len(entries) >= 173  # Existing 43 records plus deduplicated published legacy-name records
    assert len({e['slug'] for e in entries}) == len(entries)
    assert len([e for e in entries if e['source_kind'] == 'flyers']) == 12
    assert len([e for e in entries if e['source_kind'] == 'legacy']) == 12
    assert len([e for e in entries if e['source_kind'] == 'research']) == 18
    first = find_record('litefeet-massacre-2025')
    second = find_record('litefeet-massacre-pt2-2026')
    assert first and second and first['slug'] != second['slug']
    assert first['date'] == '2025-10-25'
    assert second['date'] == '2026-10-24'
    impact = find_record('double-impact-2026')
    assert len(impact['battles']) == 3
    assert 'Initial advertised team roster' in impact['battles'][0]['section']
    assert 'under review' in impact['editorial_status'].lower()
    assert not find_record('not-a-record')
    assert not any('visitor_hash' in row for row in [listing_payload(entries[0])])


def test_public_archive_and_scroll_api_show_real_entries(website):
    client = website.test_client()
    assert client.get('/archive').status_code == 301
    page = client.get('/archive/timeline')
    assert page.status_code == 200
    html = page.get_data(as_text=True)
    for text in ('SEARCH THE TIMELINE','THE CULTURAL RECORD',
                 'HISTORY &amp; TIMELINE', 'PEOPLE &amp; TEAMS'):
        assert text in html
    assert 'More than a directory' not in html
    assert 'This is a ghost profile' not in html  # Never publish fabricated legacy biographies
    endpoint = client.get('/archive/api/records').get_json()
    assert endpoint['total'] == len(all_records())
    assert len(endpoint['records']) == 8
    assert endpoint['has_more']
    next_page = client.get('/archive/api/records?page=2').get_json()
    assert not set(x['slug'] for x in endpoint['records']).intersection(
        x['slug'] for x in next_page['records'])
    assert all('raw_details_json' not in x and 'explanation' not in x for x in endpoint['records'])


def test_search_filters_all_records_not_just_first_page(website):
    client = website.test_client()
    search = client.get('/archive/api/records?q=Clash+of+the+Lites').get_json()
    assert search['total'] == 1
    assert search['records'][0]['title'] == 'Clash of the Lites'
    musicians = client.get('/archive/api/records?collection=music').get_json()
    assert musicians['total'] >= 1
    assert 'music' in {r['collection'] for r in musicians['records']}
    awards = client.get('/archive/api/records?collection=awards').get_json()
    assert awards['total'] == 1
    timeline = client.get('/archive/timeline')
    assert timeline.status_code == 200
    timeline_json = client.get('/archive/api/records?timeline=1').get_json()
    assert timeline_json['total'] >= 20
    assert timeline_json['total'] > client.get('/archive/api/records').get_json()['total']
    assert all(r['kind'] in ('record', 'chapter', 'milestone', 'era') for r in timeline_json['records'])
    researched = client.get('/archive/api/records?timeline=1&collection=history&q=harlem').get_json()
    assert researched['total'] >= 2
    assert all(r['collection'] == 'history' for r in researched['records'])


def test_source_specific_event_and_research_pages(website):
    client = website.test_client()
    event = client.get('/archive/records/double-impact-2026')
    assert event.status_code == 200
    text = event.get_data(as_text=True)
    assert 'Money Mase &amp; Noah Shifty' in text
    assert 'Nauli &amp; Lexi' in text
    assert 'Intermission matchups' in text
    assert 'No verified results' not in text
    assert 'true' in text and 'debatable' in text
    assert client.get('/archive/records/does-not-exist').status_code == 404
    person = client.get('/archive/records/research-mr-youtube')
    assert person.status_code == 200
    assert 'Community verification' not in person.get_data(as_text=True)
    awards = client.get('/archive/records/dancers-choice-awards-august-2023')
    assert awards.status_code == 200
    assert 'nominee entries' in awards.get_data(as_text=True)


def test_verification_csrf_moderation_and_single_session_response(website, database):
    client = website.test_client()
    slug = 'research-the-real-harlem-shake-predates-litefeet'
    path = '/archive/records/' + slug
    assert client.get(path).status_code == 200
    with client.session_transaction() as saved:
        csrf = saved['vault_archive_csrf']
    assert client.post(path + '/verify', data={
        'choice':'debatable','csrf_token':'invalid','explanation':'UNPUBLISHED PRIVATE COMMENT'
    }).status_code == 400
    assert client.post(path + '/verify', data={
        'choice':'maybe','csrf_token':csrf
    }).status_code == 400
    with database[1]() as db:
        assert db.query(VaultArchiveVerification).count() == 0
        before = (db.query(DCACategory).count(), db.query(DCANominationSubmission).count())
    assert client.post(path + '/verify', data={
        'choice':'debatable','csrf_token':csrf,'explanation':'UNPUBLISHED PRIVATE COMMENT'
    }).status_code == 303
    with database[1]() as db:
        row = db.query(VaultArchiveVerification).one()
        assert row.record_slug == slug and row.vote == 'debatable'
        assert row.explanation == 'UNPUBLISHED PRIVATE COMMENT'
        assert row.moderation_status == 'pending'
        assert db.query(DCACategory).count() == before[0]
        assert db.query(DCANominationSubmission).count() == before[1]
    assert 'UNPUBLISHED PRIVATE COMMENT' not in client.get(path).get_data(as_text=True)
    assert client.post(path + '/verify', data={
        'choice':'false','csrf_token':csrf
    }).status_code == 429


def test_person_identity_is_not_subject_to_popularity_vote(website):
    client = website.test_client()
    person_slug = 'research-kid-the-wiz-randy-vargas'
    assert client.get('/archive/records/' + person_slug).status_code == 200
    assert client.post('/archive/records/' + person_slug + '/verify', data={
        'choice':'false','csrf_token':'anything',
    }).status_code == 404
