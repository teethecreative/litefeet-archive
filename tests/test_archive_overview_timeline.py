"""Unified Archive Overview behavior and public metadata regression checks."""
from dca_rebuild.archive_catalog import find_record
from dca_rebuild.timeline_catalog import all_timeline_entries, record_metadata


def test_overview_is_timeline_and_uses_timeline_script(website):
    client = website.test_client()
    html = client.get('/archive').get_data(as_text=True)
    assert 'THE ARCHIVE TIMELINE' in html
    assert 'SEARCH THE TIMELINE' in html
    assert 'data-unified-timeline' in html
    assert 'timeline-v2.js' in html
    assert 'archive-v1.js' not in html
    assert 'BROWSE RECORDS' not in html


def test_people_browser_keeps_weighted_profile_cloud(website):
    client = website.test_client()
    html = client.get('/archive?view=people&collection=people').get_data(as_text=True)
    assert 'lfv-people-wordcloud' in html
    assert 'archive-v1.js' in html
    assert 'timeline-v2.js' not in html
    assert 'SEARCH PEOPLE' in html


def test_timeline_filter_and_pagination_use_full_catalog(website):
    client = website.test_client()
    html = client.get('/archive?collection=people').get_data(as_text=True)
    assert 'data-unified-timeline' in html
    payload = client.get('/archive/api/records?timeline=1&collection=events').get_json()
    assert payload['total'] >= 24
    assert payload['records']
    assert all(row['collection'] == 'events' for row in payload['records'])
    assert all(len(row['meta_parts']) == 5 for row in payload['records'])


def test_timeline_metadata_and_original_event_reclassification():
    event = find_record('litefeet-massacre-pt2-2026')
    assert event is not None
    assert 'Tok City vs Gotham City' not in event['battles'][0]['items']
    assert 'Groove Fam vs Lyve Fam' not in event['battles'][0]['items']
    twos = next(group for group in event['battles'] if group['section'] == 'Advertised 2-on-2 battles')
    assert 'Tok City vs Gotham City' in twos['items']
    assert 'Groove Fam vs Lyve Fam' in twos['items']
    assert record_metadata(event)['meta_parts'] == ('2026', '10', '24', 'EVENTS', 'HypeItUpTV')
    unknown = next(row for row in all_timeline_entries()
                   if row['kind'] == 'record' and row['collection'] == 'people')
    assert unknown['meta_parts'][0] == 'YEAR UNKNOWN'
    assert len(unknown['meta_parts']) == 4
