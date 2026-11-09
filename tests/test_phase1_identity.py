"""Regression checks for the Phase 1 public identity and editorial hierarchy."""
from dca_rebuild.models import BetaChangelog


def test_homepage_is_letter_then_current_awards_then_real_site_updates(website):
    client = website.test_client()
    response = client.get('/')
    assert response.status_code == 200
    html = response.get_data(as_text=True)
    positions = [
        html.index('id="vault-heading"'),
        html.index('id="recognition"'),
        html.index('id="whats-new"'),
    ]
    assert positions == sorted(positions)
    assert '<h1 id="vault-heading">Dear LiteFeet,</h1>' in html
    assert "But not everything has been documented." in html
    assert "That's part of why I created The LiteFeet Vault." in html
    assert 'Read more' in html
    assert 'href="/about/letter"' in html
    assert 'Dancer’s Choice Awards 2026' in html
    assert 'href="/awards/dancers-choice/2026"' in html
    assert 'THIS MONTH IN LITEFEET' in html
    assert 'lfv5-calendar-strip' in html
    assert 'LATEST UPDATES' not in html.upper()
    assert 'href="/archive/timeline"' in html
    assert 'lfv-home-v4.css' in html
    # No repeated large menu tiles, placeholder stories, backend changelog, or 2023 feature block.
    assert 'Find your way into the culture.' not in html
    assert 'August 2023: on the record.' not in html
    assert 'New stories and community updates are on the way' not in html
    assert 'Browse the Archive' not in html
    assert 'lfv1-feed-empty' not in html
    assert html.count('id="recognition"') == 1


def test_founders_letter_is_public_and_preserves_mission(website):
    client = website.test_client()
    response = client.get('/about')
    assert response.status_code == 200
    html = response.get_data(as_text=True)
    assert 'id="letter"' in html
    assert 'id="letter"' in html
    assert 'href="/about/letter"' in html
    letter = client.get('/about/letter').get_data(as_text=True)
    assert 'DEAR LITEFEET,' in letter
    assert 'LiteFeet is more than dance.' in letter
    assert "Because LiteFeet's history belongs to the people who made it." in letter
    assert 'Founder, The LiteFeet Vault' in letter
    assert 'id="mission"' in html
    assert 'id="how-it-works"' in html
    assert 'lfv-identity-phase1.css' in html


def test_homepage_news_is_real_public_site_releases_not_changelog(website, database):
    with database[1].begin() as db:
        db.add_all([
            BetaChangelog(title='Public archive update', details='Internal changelog entry', visibility='public', is_published=True),
            BetaChangelog(title='Private preview', details='Never show this', visibility='beta', is_published=True),
            BetaChangelog(title='Unpublished draft', details='Never publish this', visibility='public', is_published=False),
        ])
    client = website.test_client()
    home = client.get('/').get_data(as_text=True)
    community = client.get('/community').get_data(as_text=True)
    assert 'THIS MONTH IN LITEFEET' in home
    assert 'Internal changelog entry' not in home
    assert 'Public archive update' not in home
    assert 'Private preview' not in home
    assert 'Unpublished draft' not in home
    assert 'Never show this' not in home
    assert 'Never publish this' not in home
    assert 'Public archive update' in community  # Existing community activity left intact.


def test_phase1_keeps_archive_awards_and_community_routes(website):
    client = website.test_client()
    for route in ('/archive/timeline', '/awards', '/awards/dancers-choice/2026',
                  '/awards/dancers-choice/2023', '/community', '/about'):
        assert client.get(route).status_code == 200, route


def test_teen_nite_recurs_tuesday_thursday_with_closure_notice():
    from datetime import date
    from dca_rebuild.upcoming_calendar import upcoming_calendar
    calendar = upcoming_calendar(today=date(2026, 11, 9))
    sessions = [e for e in calendar['events'] if e['title'].startswith('Teen Nite')]
    assert len(sessions) == 9
    assert all(date.fromisoformat(e['date']).weekday() in (1, 3) for e in sessions)
    assert sessions[0]['date'] == '2026-11-10'
    assert all('6:00–9:00 PM' in e['description'] for e in sessions)
    assert all('237 East 104th Street' in e['description'] for e in sessions)
    assert all('Check @teennightnyc on Instagram for closure notifications' in e['description'] for e in sessions)
    assert all(e['href'] == 'https://www.instagram.com/teennightnyc/' for e in sessions)
