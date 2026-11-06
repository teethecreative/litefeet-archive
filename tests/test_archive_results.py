import os
from threading import Thread
import pytest
from werkzeug.serving import make_server
from dca_rebuild.models import DCAEdition, DCACategory


@pytest.mark.parametrize('path,title', [('/people/dancers','People &amp; dancers'),('/people/teams','Crews &amp; teams'),('/litefeet-music','Music'),('/battles','Battles'),('/events','Events')])
def test_archive_links_open_distinct_placeholders(website, path, title):
    response = website.test_client().get(path)
    assert response.status_code == 200 and 'Location' not in response.headers
    html = response.get_data(as_text=True)
    assert title in html and 'IN DEVELOPMENT' in html
    assert 'Back to Explore the Vault' in html
    assert 'id="vault-home"' not in html


def seed_results(database):
    _, factory, _ = database
    with factory.begin() as db:
        edition = DCAEdition(year=2023, title='Historical awards', phase='archived', is_public=True)
        db.add(edition); db.flush()
        for number in range(12):
            db.add(DCACategory(edition_id=edition.id, name=f'Historical category {number+1:02}', normalized_name=f'historical category {number+1:02}', source_type='historical', status='historical'))


def test_results_keep_all_rows_and_table_semantics(website, database):
    seed_results(database)
    response = website.test_client().get('/awards/dancers-choice/category-voting')
    assert response.status_code == 200
    html = response.get_data(as_text=True)
    assert html.count('data-result-row') == 12
    assert '<table' in html and '<thead>' in html and 'scope="row"' in html
    assert 'data-lf-compact' not in html
    assert 'Search returning categories' in html
    assert 'Historical category 12' in html


@pytest.mark.skipif(os.getenv('TEST_BROWSER') != '1', reason='Set TEST_BROWSER=1 for Chromium')
@pytest.mark.parametrize('width', [390, 1440])
def test_scrollable_results_search_keyboard_and_themes(website, database, width):
    from playwright.sync_api import sync_playwright
    seed_results(database)
    server = make_server('127.0.0.1', 0, website, threaded=True)
    thread = Thread(target=server.serve_forever, daemon=True); thread.start()
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch()
            page = browser.new_page(viewport={'width':width,'height':900})
            base = f'http://127.0.0.1:{server.server_port}'
            page.goto(base + '/people/dancers')
            assert page.get_by_role('heading',name='People & dancers').is_visible()
            page.locator('.lfv-theme-button').click()
            assert page.locator('html').get_attribute('data-theme') == 'dark'
            page.goto(base + '/awards/dancers-choice/2026')
            assert page.locator('.lfv3-awards-side').count() == 0
            assert page.locator('.lfv3-awards-intro').evaluate('node => node.clientWidth') > page.locator('.lfv3-awards-hero').evaluate('node => node.clientWidth') * .95
            page.screenshot(path=f'/tmp/vault-awards-compact-{width}.png', full_page=True)
            page.goto(base + '/awards/dancers-choice/category-voting')
            region = page.get_by_role('region',name='Returning category results',exact=True)
            page.wait_for_function("document.querySelector('.lfv-results-scroll').style.maxHeight !== ''")
            geometry = region.evaluate('''node => ({height:node.clientHeight, scroll:node.scrollHeight, expected:node.querySelector('thead').getBoundingClientRect().height + Array.from(node.querySelectorAll('tbody tr')).slice(0,5).reduce((sum,row)=>sum+row.getBoundingClientRect().height,0)})''')
            assert abs(geometry['height'] - geometry['expected']) <= 4
            assert geometry['scroll'] > geometry['height']
            assert page.get_by_role('button',name='Next',exact=False).count() == 0
            region.focus(); page.keyboard.press('ArrowDown')
            page.wait_for_function("document.querySelector('.lfv-results-scroll').scrollTop > 0")
            search = page.get_by_role('searchbox',name='Search returning categories')
            search.fill('category 12')
            assert page.locator('[data-result-row]:visible').count() == 1
            assert '1 of 12 categories' in page.locator('[data-results-count]').inner_text()
            search.fill('no matching record')
            assert page.get_by_text('No matching categories.',exact=True).is_visible()
            search.fill('')
            assert page.locator('[data-result-row]:visible').count() == 12
            assert region.evaluate('node=>node.scrollTop') == 0
            assert page.evaluate('document.documentElement.scrollWidth <= innerWidth')
            page.locator('.lfv-theme-button').click()
            assert page.locator('html').get_attribute('data-theme') == 'light'
            page.screenshot(path=f'/tmp/vault-results-table-{width}.png',full_page=True)
            browser.close()
    finally:
        server.shutdown(); thread.join(timeout=5)


def test_awards_landing_has_short_intro_and_single_actions(website):
    response = website.test_client().get('/awards/dancers-choice/2026')
    assert response.status_code == 200
    html = response.get_data(as_text=True)
    main = html.split('<main', 1)[1].split('</main>', 1)[0]
    assert 'Nominate the people who move LiteFeet forward.' in main
    assert main.count('href="/awards/dancers-choice/nominations"') == 1
    assert main.count('href="/awards/dancers-choice/category-voting"') == 1
    assert 'href="/awards/dancers-choice/2023"' in main
    assert 'lfv3-awards-side' not in main
    assert 'One awards program. Two ways in.' not in main
