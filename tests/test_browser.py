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
            assert page.locator('[data-category-id]').count() == 0
            page.locator('main input[name="email"]').fill('browser@example.com')
            page.get_by_role('button', name='CHECK CATEGORY ELIGIBILITY').click()
            assert page.locator('section[aria-labelledby="official-title"] [data-category-id]').count() == 25
            assert page.locator('#writeins').is_visible()
            assert page.locator('.lf9e-summary-stats').bounding_box()['height'] < 300
            assert 'browser@example.com' not in page.content()
            assert page.locator('h1[tabindex]').count() == 0
            assert page.evaluate('document.documentElement.scrollWidth <= innerWidth')
            page.locator('[data-category-id="1"] > a').click()
            page.locator('input[name="name"]').fill('Browser Dancer')
            page.get_by_role('button', name='SUBMIT NOMINATION', exact=True).click()
            assert page.locator('[data-category-id="1"]').inner_text().find('cooldown active') >= 0
            assert page.locator('[data-category-id="2"]').inner_text().find('Available to nominate') >= 0
            assert page.locator('[role="status"]').inner_text().find('Nomination received') >= 0
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
