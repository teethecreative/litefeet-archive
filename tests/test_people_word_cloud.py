"""People & Crews cloud links to existing archival profiles, not invented placeholders."""
from dca_rebuild.archive_catalog import PEOPLE_CLOUD_LIMIT, all_records, people_crew_cloud


def test_people_cloud_uses_real_profiles_and_consistent_weights():
    people = {r['slug'] for r in all_records() if r['collection'] == 'people'}
    cloud = people_crew_cloud()
    assert cloud
    assert {p['slug'] for p in cloud}.issubset(people)
    assert len(cloud) == min(PEOPLE_CLOUD_LIMIT, len(people))
    assert len(cloud) <= 20
    assert all(p['weight'] == p['mentions'] + 1 for p in cloud)
    assert all(p['weight'] >= 1 for p in cloud)
    assert len({p['slug'] for p in cloud}) == len(cloud)
    assert [p['weight'] for p in cloud] == sorted((p['weight'] for p in cloud), reverse=True)


def test_people_collection_has_profile_links_and_word_cloud(website):
    response = website.test_client().get('/archive?collection=people')
    assert response.status_code == 200
    page = response.get_data(as_text=True)
    assert 'lfv-people-wordcloud' in page
    assert 'FEATURED PEOPLE' in page
    assert page.index('lfv-people-wordcloud') < page.index('SEARCH PEOPLE')
    assert 'SEARCH ARCHIVE RECORDS' in page
    for entry in people_crew_cloud():
        assert '/archive/records/' + entry['slug'] in page


def test_other_collections_do_not_include_people_cloud(website):
    client = website.test_client()
    assert 'lfv-people-wordcloud' not in client.get('/archive?collection=events').get_data(as_text=True)
