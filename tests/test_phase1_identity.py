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
    assert 'href="/about#letter"' in html
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
    section_ids = ['letter', 'mission', 'about', 'how-it-works', 'contact']
    positions = [html.index(f'id="{key}"') for key in section_ids]
    assert positions == sorted(positions)
    for title in ["Founder's Letter", 'Our Mission', 'About', 'How It Works', 'Contact']:
        assert title in html
    assert 'LiteFeet is more than dance.' in html
    assert "Because LiteFeet's history belongs to the people who made it." in html
    assert 'Founder, The LiteFeet Vault' in html
    assert 'lfv-about-one-page.css' in html
    for old, anchor in [('letter','letter'), ('mission','mission'), ('archive','about'),
                        ('how-it-works','how-it-works'), ('contact','contact')]:
        redirect_response = client.get('/about/' + old)
        assert redirect_response.status_code == 301
        assert redirect_response.headers['Location'] == '/about#' + anchor
    assert 'href="/about/letter"' not in html



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
    # Timing, location and closure notices are structured fields, not repeated in descriptions.
    assert all(e['start_time'] == '18:00' and e['end_time'] == '21:00' for e in sessions)
    assert all('237 East 104th Street' in e['address'] for e in sessions)
    assert all('Check @teennightnyc on Instagram for closure notifications' in e['notice'] for e in sessions)
    assert all(not e['description'] for e in sessions)
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
    needed = {"Dancer", "Arena", "Song", "Move", "Trick"}
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
    assert "See what your opponent throws, then put together your response." in html



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
    assert '<h2>Build a Sample Deck</h2>' in html
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


def test_lock_in_catalog_contains_archive_dancers_and_music_tracks_without_producer_cards(website):
    from dca_rebuild.lock_in import public_card_catalog, public_sample_decks
    from dca_rebuild.archive_catalog import all_records
    from dca_rebuild.music_batch_catalog import batch_catalog
    catalog = public_card_catalog()
    dancers = {card["name"] for card in catalog if card["type"] == "Dancer"}
    songs = [card for card in catalog if card["type"] == "Song"]
    assert len(dancers) > 100
    assert len(songs) > 30
    assert "Producer" not in {card["type"] for card in catalog}
    assert all("Producer" not in {g["type"] for g in d["categories"]} for d in public_sample_decks())
    assert [d["total"] for d in public_sample_decks()] == [25, 35]
    assert {x["name"] for x in songs} >= {x["title"] for x in batch_catalog() if x["kind"] == "track"}
    html = website.test_client().get("/archive/lock-in").get_data(as_text=True)
    assert "Producer cards" not in html
    assert "id=\"lock-producer\"" not in html
    assert "Producers are credited on Song Cards" in html


def test_song_dropdown_alphabetical_and_producer_metadata(website):
    from dca_rebuild.lock_in import public_card_catalog
    catalog = public_card_catalog(extra_songs=(
        dict(title="Zebra Beat", producer_credit="Producer One"),
        dict(title="Alpha Beat", producer_credit="Producer Two"),
    ))
    songs = [card for card in catalog if card["type"] == "Song"]
    assert [card["name"] for card in songs] == sorted(
        (card["name"] for card in songs), key=str.casefold)
    assert next(card for card in songs if card["name"] == "Alpha Beat")["producer"] == "Producer Two"
    from pathlib import Path
    js = (Path(__file__).resolve().parents[1] /
          "dca_rebuild/static/js/lock-in-game.js").read_text()
    assert 'a.name.localeCompare(b.name' in js
    assert 'Prod. ' in js
    assert 'id="lock-producer"' not in js


def test_lock_in_has_one_game_testing_area_with_two_modes(website):
    html = website.test_client().get('/archive/lock-in').get_data(as_text=True)
    assert '<h2>Build a Sample Deck</h2>' in html
    assert html.count('id="practice"') == 1
    assert html.count('id="lock-workbench"') == 1
    assert 'name="lock-game-mode" value="battle"' in html
    assert 'name="lock-game-mode" value="moves"' in html
    assert 'id="lock-battle-mode" hidden' in html
    assert 'id="lock-moves-mode" hidden' in html
    assert html.index('id="practice"') > html.index('id="lock-moves-mode"')
    assert html.index('id="practice"') < html.index('id="lock-samples"')
    assert '>Lock In</button>' in html
    assert 'Start 1v1' in html
    assert html.count('Practice the move-set phase') == 0

    from pathlib import Path
    js = (Path(__file__).resolve().parents[1] /
          'dca_rebuild/static/js/lock-in-game.js').read_text()
    assert 'function setGameMode(mode)' in js
    assert 'setGameMode("moves")' in js
    assert 'e.target.name==="lock-game-mode"' in js
    assert 'search.has("play")' in js


def test_move_set_practice_generates_opponent_move_song_and_arena(website):
    page = website.test_client().get("/archive/lock-in")
    assert page.status_code == 200
    html = page.get_data(as_text=True)
    assert 'Choose a move-set challenge' not in html
    assert 'id="round-picker"' not in html
    assert 'id="lock-generate-situation"' in html
    assert 'id="lock-opponent-move"' in html
    assert 'id="lock-opponent-song"' in html
    assert 'id="lock-opponent-arena"' in html
    assert 'id="lock-response-moves"' in html
    assert 'id="lock-score-response"' in html
    assert 'id="lock-selected-moves"' in html
    assert 'id="lock-response-count"' in html
    assert 'id="lock-generate-situation"' in html
    assert 'id="lock-first-situation"' in html
    assert 'class="lock-game-card lock-opponent-card"' in html
    from pathlib import Path
    js = (Path(__file__).resolve().parents[1] /
          "dca_rebuild/static/js/lock-in-game.js").read_text()
    assert 'function generateSituation()' in js
    assert 'practiceCandidates("Move")' in js
    assert 'practiceCandidates("Song")' in js
    assert 'practiceCandidates("Arena")' in js
    assert 'practiceScenario.rev' in js
    assert 'practiceScenario.main' in js
    assert 'function scoreSituation()' in js
    assert 'function renderPracticeSelection()' in js
    assert 'data-practice-phase' in js
    assert 'data-card-id' in js
    assert 'lock-change-main' in js and 'lock-change-rev' in js
    assert 'lock-no-trick' in js
    assert 'Generate Another Round' in html
    assert 'finalized card rules' in js
    assert '→ Lock In' in js
    assert 'function generateSituation()' in js
    assert 'Special card effects and counters are not automatically scored' not in js


def test_lock_in_move_families_preserve_individual_moves(website):
    from dca_rebuild.lock_in import public_card_catalog
    moves = {card["name"]:card for card in public_card_catalog() if card["type"] == "Move"}
    assert moves["Stutter Step"]["move_family"] == "Footwork"
    assert moves["Rev Up"]["move_family"] == "Rev Ups"
    assert moves["Tone Whop"]["move_family"] == "Wops"
    assert "Footwork" not in moves
    assert moves["Knee Drop"]["move_family"] == "Combo"
    from pathlib import Path
    js = (Path(__file__).resolve().parents[1] /
          "dca_rebuild/static/js/lock-in-game.js").read_text()
    assert '["Rev Ups","Wops"].includes(card.move_family)' in js
    assert 'card.move_family==="Footwork"' in js
    assert 'practiceScenario.trick' in js


def test_lock_in_practice_follows_required_move_phases(website):
    html=website.test_client().get('/archive/lock-in').get_data(as_text=True)
    assert 'Rev Up or Tone Wop → Footwork / Combo / Trick → Optional Frib Card → Lock In' in html
    assert 'Choose a Rev Up or Tone Wop first' in html
    from pathlib import Path
    js=(Path(__file__).resolve().parents[1]/'dca_rebuild/static/js/lock-in-game.js').read_text()
    assert 'stage=!sc.rev?"rev":!sc.main?"main":"frib"' in js
    assert 'var ready=!!sc.rev&&!!sc.main' in js
    assert 'el("#lock-score-response").disabled=!ready' in js
    assert 'if(stage==="main") eligible=sc.moves' in js
    assert 'card.type==="Trick"' in js
    assert 'stage==="frib"' in js
    assert 'No Frib Card' in js
    assert 'practiceScenario.trick' in js
    assert 'picks.length*2' not in js


def test_frib_optional_and_community_move_suggestions(website, database):
    from dca_rebuild.models import LockInCardRequest
    client=website.test_client()
    page=client.get('/archive/lock-in').get_data(as_text=True)
    assert 'Optional Frib Card' in page
    assert 'id="lock-suggest-move"' in page
    assert 'name="move_category"' in page
    from pathlib import Path
    js=(Path(__file__).resolve().parents[1]/'dca_rebuild/static/js/lock-in-game.js').read_text()
    assert 'practiceCandidates("Frib")' in js
    assert 'phase==="frib"&&card.type==="Frib"' in js
    assert 'No Frib Card' in js
    with client.session_transaction() as session:
        token=session['lock_card_csrf']
    missing=client.post('/archive/lock-in/card-requests',data={
        'csrf_token':token,'card_type':'Move','card_name':'Community Variation',
        'email':'dancer@example.org','move_category':''
    })
    assert missing.status_code==400
    submitted=client.post('/archive/lock-in/card-requests',data={
        'csrf_token':token,'card_type':'Move','card_name':'Community Variation',
        'email':'dancer@example.org','move_category':'Footwork',
        'move_style':'Variation suggested by community'
    })
    assert submitted.status_code==201
    with database[1]() as db:
        item=db.query(LockInCardRequest).filter_by(card_name='Community Variation').one()
        assert item.status=='pending'
        assert '"move_category": "Footwork"' in item.details_json


def test_move_set_accepts_rev_up_or_tone_wop_opening(website):
    html=website.test_client().get('/archive/lock-in').get_data(as_text=True)
    assert 'Rev Up or Tone Wop → Footwork / Combo / Trick' in html
    from pathlib import Path
    js=(Path(__file__).resolve().parents[1]/'dca_rebuild/static/js/lock-in-game.js').read_text()
    assert 'if(phase==="rev"&&card.type==="Move"&&["Rev Ups","Wops"].includes(card.move_family))' in js
    assert 'card.move_family==="Wops"?"TONE WOP":"REV UP"' in js


def test_source_grounded_lock_in_move_taxonomy_and_sample_readiness(website):
    from dca_rebuild.lock_in import (
        MOVE_FAMILIES, OPENING_FAMILIES, MAIN_MOVE_FAMILIES,
        public_card_catalog, public_sample_decks, sample_deck_readiness
    )
    footwork = ("Butterfly", "Tweak", "Around The World", "Gangsta Lean", "Stutter Step")
    combos = ("Knee Drop", "Swiss Drop", "Coin Drop", "Kiss Of Death",
              "Needle & Thread", "Villain Swoop", "Streetfighter Walk",
              "No Gwop", "Slatter Gwop")
    assert all(MOVE_FAMILIES[name.casefold()] == "Footwork" for name in footwork)
    assert all(MOVE_FAMILIES[name.casefold()] == "Combo" for name in combos)
    assert MOVE_FAMILIES["bad one"] == "Legacy setup — review"
    assert OPENING_FAMILIES == {"Rev Ups", "Wops"}
    assert MAIN_MOVE_FAMILIES == {"Footwork", "Combo"}
    catalog = public_card_catalog()
    by_id = {card["id"]: card for card in catalog}
    assert by_id["Move::Bad One"]["review_status"] == "source-draft"
    assert by_id["Move::Knee Drop"]["move_family"] == "Combo"
    assert by_id["Trick::Shoe Trick"]["type"] == "Trick"
    assert by_id["Frib::No Hype"]["type"] == "Frib"
    assert all(card["review_status"] in ("source-draft", "reference-only")
               for card in catalog)
    decks = public_sample_decks()
    assert [d["total"] for d in decks] == [25, 35]
    assert all(d["readiness"]["playable"] for d in decks)
    assert all(d["readiness"]["opening_count"] >= 1 for d in decks)
    assert all(d["readiness"]["main_count"] >= 1 for d in decks)
    missing = sample_deck_readiness((
        ("Dancer", ("Example Dancer",)),
        ("Song", ("Example Song",)),
        ("Arena", ("Example Arena",)),
        ("Move", ("Bad One",)),
    ))
    assert not missing["playable"]
    assert missing["opening_count"] == 0
    assert missing["main_count"] == 0
    html = website.test_client().get("/archive/lock-in").get_data(as_text=True)
    assert "Producer Cards are reserved for a separate future producer-battle format." in html
    assert "Historical names and planning entries are not all approved playable cards." in html
    from pathlib import Path
    js = (Path(__file__).resolve().parents[1] /
          "dca_rebuild/static/js/lock-in-game.js").read_text()
    assert "Add a Rev Up or Tone Wop opening card." in js
    assert "Add at least one Footwork, Combo, or Trick main-move card." in js
    assert '["Footwork","Combo"].includes(card.move_family)' in js
