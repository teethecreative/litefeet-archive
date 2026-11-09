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
    assert '--word-size:' in page
    assert 'Names that appear more often in documented records are larger.' in page
    assert 'FEATURED PEOPLE' in page
    assert page.index('lfv-people-wordcloud') < page.index('SEARCH PEOPLE')
    assert 'SEARCH ARCHIVE RECORDS' in page
    for entry in people_crew_cloud():
        assert '/archive/records/' + entry['slug'] in page


def test_other_collections_do_not_include_people_cloud(website):
    client = website.test_client()
    assert 'lfv-people-wordcloud' not in client.get('/archive?collection=events').get_data(as_text=True)


def test_people_cloud_is_just_clickable_words_not_gold_buttons():
    """Protect the typographic cloud from sitewide CTA styles."""
    from pathlib import Path
    style = (Path(__file__).resolve().parents[1] /
             'dca_rebuild/static/css/lfv-consistency-v5.css').read_text()
    cloud_css = style.split('/* People & Crews: typography-only word cloud', 1)[1]
    assert 'background:transparent!important;' in cloud_css
    assert 'border:0!important;' in cloud_css
    assert 'font-size:var(--word-size,1.25rem)!important;' in cloud_css
    assert 'text-decoration:underline!important;' in cloud_css
    assert 'background:#c9a52b' not in cloud_css


def test_historical_candidate_review_preserves_source_id_without_publishing():
    from dca_rebuild.archive_catalog import reconcile_historical_profile_rows
    source = [
        {"id": "29", "dance_name": "Venom", "profile_slug": "venom-older",
         "bio": "This is a ghost profile", "team_affiliation": "Team Demon",
         "role_tags": "Dancer", "status": "Active"},
        {"id": "112", "dance_name": "Venom", "profile_slug": "venom-other",
         "bio": "unverified", "status": "Active"},
        {"id": "12", "dance_name": "PRockz", "profile_slug": "prockz",
         "status": "Active"},
        {"id": "135", "dance_name": "P Rockz", "profile_slug": "p-rockz",
         "status": "Active"},
    ]
    candidates = reconcile_historical_profile_rows(source)
    assert len(candidates) == 4
    assert {c["source_id"] for c in candidates} == {"29", "112", "12", "135"}
    assert all(c["publishable"] is False for c in candidates)
    assert all(c["review_status"] == "possible_duplicate_review_required" for c in candidates)
    assert candidates[0]["duplicate_source_ids"] == ["112"]
    assert candidates[2]["duplicate_source_ids"] == ["135"]
    assert candidates[0]["original_affiliation"] == "Team Demon"
    assert all("bio" not in c for c in candidates)
    assert all("email" not in c for c in candidates)


def test_historical_review_does_not_change_public_cloud():
    from dca_rebuild.archive_catalog import reconcile_historical_profile_rows, people_crew_cloud
    before = people_crew_cloud()
    reconcile_historical_profile_rows([
        {"id": "999", "dance_name": "Review Only", "status": "Active"}
    ])
    assert people_crew_cloud() == before


def test_people_collection_query_opens_people_browser_not_timeline(website):
    response = website.test_client().get('/archive?collection=people')
    assert response.status_code == 200
    page = response.get_data(as_text=True)
    assert 'lfv-people-wordcloud' in page
    assert 'SEARCH PEOPLE &amp; CREWS' in page
    assert 'CHRONOLOGICAL TIMELINE' not in page
