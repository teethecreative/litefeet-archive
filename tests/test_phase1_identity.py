"""Regression checks for the Phase 1 public identity and editorial hierarchy."""
from dca_rebuild.models import BetaChangelog


def test_homepage_has_distinct_public_sections_and_real_destinations(website):
    client = website.test_client()
    response = client.get('/')
    assert response.status_code == 200
    html = response.get_data(as_text=True)
    positions = [
        html.index('id="vault-heading"'),
        html.index('id="whats-new"'),
        html.index('id="featured"'),
        html.index('id="explore"'),
        html.index('id="recognition"'),
        html.index('id="contribute"'),
    ]
    assert positions == sorted(positions)
    assert 'THE CULTURE DESERVES TO <span class="lfv1-headline-pair">BE REMEMBERED.</span>' in html
    assert 'class="lfv1-founder-greeting">Dear LiteFeet,</p>' in html
    assert 'lfv1-founder-excerpt' in html
    assert 'Read more' in html
    assert 'Read Dear LiteFeet' not in html
    assert 'href="/about#letter"' in html
    assert 'August 2023: on the record.' in html
    assert 'href="/awards/dancers-choice/2026"' in html
    assert 'href="/community#contribute"' in html
    assert 'lfv-identity-phase1.css' in html
    assert 'No stories found' not in html


def test_founders_letter_is_public_and_preserves_mission(website):
    client = website.test_client()
    response = client.get('/about')
    assert response.status_code == 200
    html = response.get_data(as_text=True)
    assert 'id="letter"' in html
    assert 'Dear LiteFeet,' in html
    assert 'LiteFeet is more than dance.' in html
    assert "Because LiteFeet's history belongs to the people who made it." in html
    assert 'Founder, The LiteFeet Vault' in html
    assert 'id="mission"' in html
    assert 'id="how-it-works"' in html
    assert 'lfv-identity-phase1.css' in html


def test_homepage_only_shows_public_published_updates(website, database):
    with database[1].begin() as db:
        db.add_all([
            BetaChangelog(title='Public archive update', details='Published and public', visibility='public', is_published=True),
            BetaChangelog(title='Private preview', details='Never show this', visibility='beta', is_published=True),
            BetaChangelog(title='Unpublished draft', details='Never publish this', visibility='public', is_published=False),
        ])
    client = website.test_client()
    html = client.get('/').get_data(as_text=True)
    assert 'Public archive update' in html
    assert 'Private preview' not in html
    assert 'Unpublished draft' not in html
    assert 'Never show this' not in html
    assert 'Never publish this' not in html


def test_phase1_keeps_archive_awards_and_community_routes(website):
    client = website.test_client()
    for route in ('/archive', '/awards', '/awards/dancers-choice/2026',
                  '/awards/dancers-choice/2023', '/community', '/about'):
        assert client.get(route).status_code == 200, route
