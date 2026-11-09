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
    assert all(e['href'].startswith('/calendar/events/') for e in sessions)
    assert all(e['source_href'] == 'https://www.instagram.com/teennightnyc/' for e in sessions)


def test_lock_in_sample_decks_are_neutral_and_practice_does_not_spotlight_two_submitters(website):
    client = website.test_client()
    page = client.get('/archive/lock-in')
    assert page.status_code == 200
    html = page.get_data(as_text=True)
    assert 'Sample deck 1' in html and 'Sample deck 2' in html
    assert 'Sample deck featuring DC' not in html
    assert 'Sample deck featuring K Cosmic' not in html
    assert 'DC submitted Performance' not in html
    assert 'K Cosmic chose Spank' not in html
    assert 'DC and K Cosmic' not in html
    assert 'Airman' in html
    from dca_rebuild.lock_in import ROUNDS, practice_view
    assert 'performance' not in ROUNDS and 'spank' not in ROUNDS
    from werkzeug.datastructures import MultiDict
    assert practice_view(MultiDict())['round_key'] == 'greklite'


def test_lock_in_sample_decks_follow_rulebook_card_categories(website):
    from dca_rebuild.lock_in import public_sample_decks
    decks = public_sample_decks()
    assert len(decks) == 2
    needed = {"Dancer", "Arena", "Producer", "Song", "Move", "Trick"}
    assert [deck["total"] for deck in decks] == [25, 35]
    for deck in decks:
        assert sum(group["count"] for group in deck["categories"]) == deck["total"]
        assert needed.issubset({group["type"] for group in deck["categories"]})
        assert next(g["count"] for g in deck["categories"] if g["type"] == "Dancer") < deck["total"]

    response = website.test_client().get("/archive/lock-in")
    assert response.status_code == 200
    html = response.get_data(as_text=True)
    assert "25 cards" in html and "35 cards" in html
    assert "25 dancer cards" not in html
    assert "25 different dancers" not in html
    assert "Move (7)" in html
    assert "Arena (2)" in html
    assert "Choose a challenge and put together your three-move set." in html



def test_lock_in_rulebook_and_mixed_deck_builder_present(website):
    html = website.test_client().get('/archive/lock-in').get_data(as_text=True)
    assert 'How to battle' in html
    assert 'Winning a round' in html
    assert 'Battle conditions' in html.lower() or 'Battle conditions' in html
    assert 'Draw seven cards' in html
    assert 'Round of Fire' in html
    assert 'Final BP and TKO targets will be announced.' in html
    assert 'id="lock-workbench"' in html
    assert 'id="lock-count"' in html
    assert 'id="lock-deck-list"' in html
    assert 'id="lock-battle"' in html
    assert 'js/lock-in-game.js' in html
    from pathlib import Path
    js = (Path(__file__).resolve().parents[1] /
          'dca_rebuild/static/js/lock-in-game.js').read_text()
    assert 'deck.length<25||deck.length>50' in js
    assert 'amount(c.id)<=limit(c.id)' in js
    assert 'slice(0,7)' in js
    assert 'selected.filter' in js
    assert 'Missed Lock In' in js
    assert 'Incorrect card-validity challenge' in js
    assert 'Battle victory thresholds are still blank' in js
    assert 'lock-save' in html and 'lock-load' in html
    assert 'id="lock-restrictions"' in html
    assert 'lockin-draft-deck-v1' in js
    assert 'limit(c.id)' in js
    assert 'restrictions[id]' in js


def test_lock_in_has_compact_different_size_samples_and_search(website):
    from dca_rebuild.lock_in import public_sample_decks
    assert [d['total'] for d in public_sample_decks()] == [25, 35]
    response = website.test_client().get('/archive/lock-in')
    assert response.status_code == 200
    html = response.get_data(as_text=True)
    assert 'Build A Deck &amp; Test The Game' in html
    assert 'id="lock-search"' in html
    assert 'id="lock-catalog"' in html
    assert 'id="lock-request-panel"' in html
    assert 'data-deck-sample="0"' in html
    assert 'data-deck-sample="1"' in html
    assert 'Adapted directly from the' not in html
    assert 'Use the mixed-card examples to build' not in html
    from pathlib import Path
    js = (Path(__file__).resolve().parents[1] / 'dca_rebuild/static/js/lock-in-game.js').read_text()
    assert 'el("#lock-search").addEventListener("input",renderCatalog)' in js
    assert 'lock-request-form' in js
    assert 'pool[id].name' in js


def test_lock_in_card_request_is_csrf_protected_and_moderated(website, database):
    from dca_rebuild.models import LockInCardRequest
    client = website.test_client()
    rejected = client.post('/archive/lock-in/card-requests',
                           data=dict(card_type='Song', card_name='My Song', email='x@example.org', producer='Example'))
    assert rejected.status_code == 400
    client.get('/archive/lock-in')
    with client.session_transaction() as session:
        token = session['lock_card_csrf']
    missing_producer = client.post('/archive/lock-in/card-requests',
                                   data=dict(csrf_token=token, card_type='Song',
                                             card_name='Example Song',email='x@example.org'))
    assert missing_producer.status_code == 400
    accepted = client.post('/archive/lock-in/card-requests',
                           data=dict(csrf_token=token,card_type='Song',card_name='Example Song',
                                     email='x@example.org',producer='Example Producer',
                                     gameplay='A beat for battles'))
    assert accepted.status_code == 201
    assert accepted.get_json()['ok']
    with database[1]() as db:
        entry = db.query(LockInCardRequest).filter_by(card_name='Example Song').one()
        assert entry.card_type == 'Song'
        assert entry.status == 'pending'
        assert 'Example Producer' in entry.details_json
    repeat = client.post('/archive/lock-in/card-requests',
                         data=dict(csrf_token=token,card_type='Song',card_name='Another Song',
                                   email='x@example.org',producer='Example Producer'))
    assert repeat.status_code == 429
