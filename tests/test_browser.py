"""Real Chromium checks. Run with TEST_BROWSER=1 after playwright install chromium."""
import os
from pathlib import Path
from threading import Thread
import pytest
from werkzeug.serving import make_server

pytestmark = pytest.mark.skipif(os.getenv('TEST_BROWSER') != '1', reason='Set TEST_BROWSER=1 to run Chromium checks')


@pytest.mark.parametrize('width,height', [(390, 844), (1440, 1000)])
def test_grid_navigation_theme_and_keyboard(website, width, height):
    from playwright.sync_api import sync_playwright
    server = make_server('127.0.0.1', 0, website, threaded=True)
    thread = Thread(target=server.serve_forever, daemon=True); thread.start()
    base = f'http://127.0.0.1:{server.server_port}'
    try:
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch()
            page = browser.new_page(viewport={'width': width, 'height': height})
            errors = []
            page.on('pageerror', lambda error: errors.append(str(error)))
            page.goto(base + '/')
            assert page.locator('#vault-home > section').count() == 4
            assert page.locator('#vault-home a[href="/awards/dancers-choice/nominations"]').count() == 1
            assert page.locator('.lfv-shell-nominations').count() == 0
            menu = page.get_by_role('button', name='Open site navigation')
            menu.click()
            assert page.locator('#lfv-menu-panel').is_visible()
            assert page.locator('#lfv-menu-panel a[href="/awards/dancers-choice/nominations"]').count() == 0
            page.keyboard.press('Escape')
            assert menu.evaluate('(node) => node === document.activeElement')
            theme = page.locator('.lfv-theme-button')
            theme.click()
            assert page.locator('html').get_attribute('data-theme') == 'dark'
            page.reload()
            assert page.locator('html').get_attribute('data-theme') == 'dark'
            page.goto(base + '/awards/dancers-choice/nominations')
            assert page.locator('main input[name="email"]').is_visible()
            assert page.locator('#lf9e-intro-categories li').count() == 25
            assert page.locator('.lf9e-intro-category-scroll').bounding_box()['height'] <= 202
            assert page.locator('#lf9e-email-start').bounding_box()['y'] < 850
            page.screenshot(path=f'/tmp/vault-introduction-compact-{width}.png', full_page=True)
            assert page.locator('#lf9e-intro-categories').bounding_box()['y'] < page.locator('#lf9e-email-start').bounding_box()['y']
            assert page.evaluate('document.documentElement.scrollWidth <= innerWidth')
            assert page.locator('[data-category-id]').count() == 0
            page.locator('main input[name="email"]').fill('browser@example.com')
            page.get_by_role('button', name='CONTINUE').click()
            assert page.locator('section[aria-labelledby="official-title"] [data-category-id]').count() == 25
            assert page.locator('#writeins').is_visible()
            assert not page.locator('.lf9e-summary-stats').is_visible()
            assert 'browser@example.com' not in page.content()
            assert page.locator('h1[tabindex]').count() == 0
            assert page.evaluate('document.documentElement.scrollWidth <= innerWidth')
            assert page.get_by_role('button', name='USE A DIFFERENT EMAIL').count() == 0
            assert page.locator('[data-category-id="1"]').inner_text().strip() == 'Category 1'
            page.locator('[data-category-id="1"] > a').click()
            assert page.get_by_role('heading', name='Suggestions', exact=True).is_visible()
            assert page.locator('input[name="name"]').count() == 0
            page.get_by_role('link', name='NOMINATE', exact=True).click()
            page.locator('input[name="name"]').fill('Browser Dancer')
            page.locator('input[name="team"]').fill('Browser Crew')
            page.locator('textarea[name="reason"]').fill('They bring the community together.')
            page.get_by_role('button', name='SUBMIT NOMINATION', exact=True).click()
            assert page.get_by_role('heading', name='NOMINEE STANDINGS', exact=True).is_visible()
            assert page.locator('.lf9e-summary-stats').count() == 0
            assert page.locator('.lf9e-standings-category').count() == 27
            assert page.locator('#standings-25 .lf9e-standings-empty').inner_text() == 'No nominations yet.'
            standings = page.locator('.lf9e-standings-category').first
            assert standings.bounding_box()['height'] < 150
            assert standings.evaluate('node => getComputedStyle(node).borderLeftWidth') == '0px'
            nominee_link = standings.get_by_role('link', name='Browser Dancer')
            assert nominee_link.evaluate('node => getComputedStyle(node).backgroundColor') == 'rgba(0, 0, 0, 0)'
            assert nominee_link.bounding_box()['height'] >= 44
            assert page.locator('.lf9e-standings-heading').bounding_box()['height'] < 100
            page.screenshot(path=f'/tmp/vault-nominee-standings-{width}.png', full_page=True)
            assert page.get_by_role('link', name='Browser Dancer', exact=True).is_visible()
            assert page.locator('[role="status"]').inner_text().find('Nomination received') >= 0
            page.get_by_role('link', name='Nominate', exact=True).click()
            page.locator('[data-category-id="1"] > a').click()
            assert 'cooldown active' in page.locator('.lf9e-status').inner_text()
            page.get_by_role('link', name='Browser Dancer').click()
            assert page.get_by_role('heading', name='Browser Dancer', exact=True).is_visible()
            assert 'Browser Crew' in page.locator('.lf9e-suggestion-details').inner_text()
            assert 'They bring the community together.' in page.locator('.lf9e-suggestion-details').inner_text()
            assert 'approved' not in page.locator('main').inner_text().lower()
            page.get_by_role('link', name='ALL CATEGORIES').click()
            page.locator('[data-category-id="2"] > a').click()
            assert 'Available to nominate' in page.locator('.lf9e-status').inner_text()
            page.get_by_role('link', name='ALL CATEGORIES').click()
            page.locator('.lfv-theme-button').click()
            assert page.locator('html').get_attribute('data-theme') == 'light'
            page.mouse.move(0, 0)
            link = page.locator('[data-category-id="2"] > a')
            assert link.evaluate('node => getComputedStyle(node).textDecorationLine') == 'none'
            link.focus()
            page.keyboard.press('Tab')
            page.keyboard.press('Shift+Tab')
            assert link.evaluate('node => getComputedStyle(node).outlineStyle') != 'none'
            assert page.evaluate('document.documentElement.scrollWidth <= innerWidth')
            page.screenshot(path=f'/tmp/vault-grid-{width}.png', full_page=True)
            assert errors == []
            browser.close()
    finally:
        server.shutdown(); thread.join(timeout=5)
