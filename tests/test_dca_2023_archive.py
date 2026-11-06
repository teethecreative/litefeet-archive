import csv
from html.parser import HTMLParser
import json
import os
from pathlib import Path
from threading import Thread
import pytest
from werkzeug.serving import make_server
from dca_rebuild.archive_2023 import load_archive_2023
from dca_rebuild.models import DCAEdition, DCACategory, DCANominee, DCANominationSubmission, LFAArchiveSubmission

ROOT = Path(__file__).resolve().parents[1]
PATH = '/awards/dancers-choice/2023'


class ArchiveParser(HTMLParser):
    def __init__(self):
        super().__init__(); self.categories = {}; self.current = None; self.target = None
    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag == 'details' and 'data-category-name' in attrs:
            self.current = {'winners': [], 'others': []}
            self.categories[attrs['data-category-name']] = self.current
        if self.current is not None:
            if 'data-winner' in attrs: self.target = 'winners'
            if 'data-other-nominee' in attrs: self.target = 'others'
    def handle_data(self, text):
        if self.current is not None and self.target and text.strip():
            self.current[self.target].append(text.strip())
    def handle_endtag(self, tag):
        if tag in ('strong', 'li'): self.target = None
        if tag == 'details': self.current = None; self.target = None


def test_complete_dataset_matches_historical_names_and_winners():
    categories = load_archive_2023()
    assert len(categories) == 31
    assert sum(len(c.nominees) for c in categories) == 152
    assert sum(len(c.winners) for c in categories) == 32
    assert sum(len(c.winners) > 1 for c in categories) == 1
    expected_sizes = [5,5,5,7,5,5,5,6,5,5,5,5,5,6,5,5,5,5,5,5,5,5,6,5,5,4,5,4,3,3,3]
    assert [len(c.nominees) for c in categories] == expected_sizes
    # Compare every label and winner flag against the existing archived source;
    # deliberately ignore its counts and Rank column.
    with (ROOT / 'data/imports/dancers_choice_august_2023_all_nominee_fixed_votes.csv').open(newline='',encoding='utf-8') as f:
        source = list(csv.DictReader(f))
    expected = [(r['Category'],r['Nominee'],r['Official Result'] in ('official_winner','official_co_winner')) for r in source]
    actual = [(c.name,n.name,n.is_winner) for c in categories for n in c.nominees]
    assert actual == expected
    # Independently check all winning entries against the existing winner source.
    winner_source = json.loads((ROOT / 'data/imports/dancers_choice_august_2023_official_results.json').read_text())
    assert {(c.name,n.name) for c in categories for n in c.winners} == {(r['category'],r['winner']) for r in winner_source}
    by_name = {c.name:c for c in categories}
    assert {n.name for n in by_name['Best Team Video'].winners} == {'2Crafty','Bombsquad'}
    assert 'Esolo' in [n.name for n in by_name['Best Content Creator'].nominees]
    assert 'SoundCloud' in [n.name for n in by_name['Most Versatile'].nominees]
    assert 'Sound Cloud' in [n.name for n in by_name['Best Musicality'].nominees]
    assert 'Speightsrawkid (Buckwheat)' in [n.name for n in by_name['Most Consistent Producer'].nominees]
    assert 'Lucky luck' in [n.name for n in by_name['Best Entertainer'].nominees]
    assert 'Best “Lite” Feet Energy' in by_name


def test_source_caveats_are_preserved_without_publishing_vote_data():
    data = json.loads((ROOT / 'dca_rebuild/data/dca_2023_archive.json').read_text())
    assert data['source']['underlying_pdf_independently_rechecked'] is False
    assert data['source']['winner_designation_in_spreadsheet'] == 'official PDF results'
    assert data['source']['adjusted_count_categories'] == ['Best Shoe Tricker','Most Fearless','Best Combo Dancer']
    for category in data['categories']:
        assert set(category) == {'id','name','nominees'}
        assert all(set(n) == {'name','is_winner'} for n in category['nominees'])


def test_public_archive_renders_every_entry_without_duplicate_winners(website):
    response = website.test_client().get(PATH)
    assert response.status_code == 200
    html = response.get_data(as_text=True)
    parser = ArchiveParser(); parser.feed(html)
    assert len(parser.categories) == 31
    assert sum(len(c['winners']) for c in parser.categories.values()) == 32
    assert sum(len(c['others']) for c in parser.categories.values()) == 120
    for category in load_archive_2023():
        rendered = parser.categories[category.name]
        assert rendered['winners'] == [n.name for n in category.winners]
        assert rendered['others'] == [n.name for n in category.other_nominees]
        assert set(rendered['winners']).isdisjoint(rendered['others'])
    main = html.split('<main',1)[1].split('</main>',1)[0]
    assert 'still being collected' not in main
    assert 'nominees, and winners' not in main
    for private_source in ['Fixed Public Votes','Original Vote Option','PDF Page','adjusted_count_categories','underlying_pdf_independently_rechecked','all_nominee_fixed_votes.csv']:
        assert private_source not in html
    assert 'votes' not in main.lower() and 'ranking' not in main.lower()
    assert 'Help Preserve LiteFeet History' in main
    assert 'href="/awards/litefeet-awards#contribute"' in main
    assert 'August 2023' in main and 'HISTORICAL AWARDS ARCHIVE' in main


def test_archive_is_read_only_and_contribution_workflow_still_works(website, database):
    factory = database[1]
    models = [DCAEdition,DCACategory,DCANominee,DCANominationSubmission]
    with factory() as db:
        before = [db.query(model).count() for model in models]
    client = website.test_client()
    assert client.get(PATH).status_code == 200
    with factory() as db:
        assert [db.query(model).count() for model in models] == before
    form = client.get('/awards/litefeet-awards').get_data(as_text=True)
    assert 'id="contribute"' in form
    assert 'action="/awards/litefeet-awards/submit"' in form
    response = client.post('/awards/litefeet-awards/submit', data=dict(
        submission_type='award_winner',year='2023',category_name='DCA 2023 — Best Trickster',
        winner_name='Kid Smoove',additional_details='Historical correction for review',
        source_information='Community-provided historical evidence'))
    assert response.status_code == 200
    with factory() as db:
        contribution = db.query(LFAArchiveSubmission).one()
        assert contribution.year == 2023 and contribution.status == 'pending'
        assert contribution.category_name == 'DCA 2023 — Best Trickster'
        assert contribution.source_information == 'Community-provided historical evidence'
        assert [db.query(model).count() for model in models] == before
    # Do not replace other historical edition templates or routes.
    unrelated = client.get('/awards/litefeet-awards/2023').get_data(as_text=True)
    assert 'id="dca-2023-archive"' not in unrelated


@pytest.mark.skipif(os.getenv('TEST_BROWSER') != '1',reason='Set TEST_BROWSER=1 for Chromium')
@pytest.mark.parametrize('width',[390,1440])
def test_archive_search_accordion_navigation_and_themes(website,width):
    from playwright.sync_api import sync_playwright
    server = make_server('127.0.0.1',0,website,threaded=True)
    thread = Thread(target=server.serve_forever,daemon=True);thread.start()
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch()
            page = browser.new_page(viewport={'width':width,'height':900})
            errors=[];page.on('pageerror',lambda error:errors.append(str(error)))
            page.goto(f'http://127.0.0.1:{server.server_port}'+PATH)
            assert page.locator('.dca23-category').count() == 31
            assert page.locator('[data-winner]').count() == 32
            assert page.locator('[data-other-nominee]').count() == 120
            assert page.locator('.dca23-overview dd').all_text_contents() == ['31','152','32','1']
            assert page.evaluate('document.documentElement.scrollWidth <= innerWidth')
            first=page.locator('.dca23-category').first
            first.locator('summary').click()
            assert first.get_attribute('open') is not None
            assert first.locator('li').all_text_contents() == ['Richie Rich','Larry Smoove','FLii BOOGiiE','D Astro']
            first.locator('summary').focus();page.keyboard.press('Enter')
            assert first.get_attribute('open') is None
            search=page.get_by_role('searchbox',name='Search categories')
            search.fill('best team video')
            assert page.locator('.dca23-category:visible').count() == 1
            team=page.locator('#dca23-best-team-video')
            assert team.locator('[data-winner]').all_text_contents() == ['2Crafty','Bombsquad']
            assert 'Co-winners' in team.inner_text()
            team.locator('summary').click()
            assert team.locator('li').all_text_contents() == ['God Of Shoe Tricks','Lyve Rockets','Lyvetyme']
            page.screenshot(path=f'/tmp/vault-2023-co-winners-{width}.png',full_page=True)
            search.fill('no matching category')
            assert page.get_by_text('No matching categories.',exact=True).is_visible()
            page.get_by_role('button',name='All categories',exact=True).click()
            assert page.locator('.dca23-category:visible').count() == 31
            assert search.input_value() == ''
            region=page.get_by_role('region',name='2023 award categories',exact=True)
            region.focus();page.keyboard.press('ArrowDown')
            page.wait_for_function("document.getElementById('dca23-categories').scrollTop > 0")
            page.locator('.lfv-theme-button').click()
            assert page.locator('html').get_attribute('data-theme') == 'dark'
            page.reload()
            assert page.locator('html').get_attribute('data-theme') == 'dark'
            assert page.evaluate('document.documentElement.scrollWidth <= innerWidth')
            page.screenshot(path=f'/tmp/vault-2023-archive-{width}.png',full_page=True)
            link=page.get_by_role('link',name='Contribute historical information',exact=True)
            assert link.get_attribute('href') == '/awards/litefeet-awards#contribute'
            link.click()
            assert page.locator('#contribute form').is_visible()
            assert errors == []
            # Native category accordions remain usable with scripts disabled.
            fallback=browser.new_page(java_script_enabled=False,viewport={'width':width,'height':900})
            fallback.goto(f'http://127.0.0.1:{server.server_port}'+PATH)
            fallback.locator('.dca23-category').first.locator('summary').click()
            assert fallback.locator('.dca23-category').first.get_attribute('open') is not None
            browser.close()
    finally:
        server.shutdown();thread.join(timeout=5)
