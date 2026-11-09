import json
import os
import re
import struct
from threading import Thread
from urllib.parse import urlsplit
import pytest
from werkzeug.serving import make_server
from dca_rebuild.information_architecture import SECTION_CATALOG
from dca_rebuild.models import LedgerEra, BetaChangelog, DCACategory, DCANominationSubmission


def navigation(html):
    match = re.search(r'<script id="lfv-navigation-data" type="application/json">(.*?)</script>', html, re.S)
    assert match
    return json.loads(match.group(1))


def test_ready_navigation_and_every_active_link(website):
    client = website.test_client()
    html = client.get('/').get_data(as_text=True)
    items = navigation(html)
    assert [x[1] for x in SECTION_CATALOG] == ['Home','The Archive','People & Teams','History & Timeline','Upcoming Calendar','Awards & Recognition','Lock In Card Battle Game','Music','Media','Stories & Media','Community','About']
    assert [x['label'] for x in items] == ['Home','The Archive','People & Teams','History & Timeline','Upcoming Calendar','Awards & Recognition','Lock In Card Battle Game','Music','About']
    links = [x['href'] for x in items] + [c['href'] for x in items for c in x['children']]
    assert not any('/admin' in x or '/nominations' in x for x in links)
    assert not any(x in links for x in ['/people','/stories','/media'])
    assert '/archive' in links and '/archive/people' in links and '/calendar' in links
    assert not next(x for x in items if x['label'] == 'The Archive')['children']
    assert '/awards/hypeitup' in links
    # About is a direct top-level link, never a submenu or nested overview.
    about_item = next(x for x in items if x['label'] == 'About')
    assert about_item['href'] == '/about'
    assert about_item['children'] == []
    for href in links:
        url = urlsplit(href)
        response = client.get(url.path + ('?' + url.query if url.query else ''))
        assert response.status_code == 200, href
        if url.fragment:
            assert f'id="{url.fragment}"' in response.get_data(as_text=True), href
    assert 'href="/people/dancers"' not in html.split('<main',1)[1].split('</main>',1)[0]
    assert client.get('/submit/start').headers['Location'] == '/community#contribute'
    for path in ['/people/dancers','/people/teams','/litefeet-music','/events','/battles','/awards/hypeitup','/awards/litefeet-awards','/awards/dancers-choice/2023']:
        assert client.get(path).status_code == 200
    assert client.get('/dca/2023').status_code == 302


def test_publication_filters_and_no_data_mutation(website, database):
    with database[1].begin() as db:
        db.add_all([
            LedgerEra(name='Published era',slug='published-era',status='published',start_year=2000,description='Published history',source_notes='PRIVATE SOURCE NOTES'),
            LedgerEra(name='Draft era',slug='draft-era',status='draft',description='PRIVATE DRAFT'),
            BetaChangelog(title='Public update',details='Published community update',visibility='public',is_published=True),
            BetaChangelog(title='Private beta update',details='PRIVATE BETA',visibility='beta',is_published=True),
            BetaChangelog(title='Unpublished update',details='PRIVATE UNPUBLISHED',visibility='public',is_published=False),
        ])
    with database[1]() as db:
        before = (db.query(DCACategory).count(),db.query(DCANominationSubmission).count())
    client = website.test_client()
    for path in ['/','/archive','/archive/timeline','/calendar','/community','/about','/awards']:
        page = client.get(path)
        assert page.status_code == 200
        assert 'PRIVATE' not in page.get_data(as_text=True)
    timeline = client.get('/archive/timeline?q=Published+era').get_data(as_text=True)
    assert 'Published era' in timeline and '2000' in timeline
    assert 'Public update' in client.get('/community').get_data(as_text=True)
    assert '/archive/timeline' in [n['href'] for n in navigation(client.get('/').get_data(as_text=True))]
    assert 'Submit to the Archive' in client.get('/archive').get_data(as_text=True)
    with database[1]() as db:
        assert (db.query(DCACategory).count(),db.query(DCANominationSubmission).count()) == before


def test_unpublished_eras_are_not_leaked_into_public_timeline(website):
    client = website.test_client()
    page = client.get('/archive/timeline')
    assert page.status_code == 200
    assert 'HISTORY &amp; TIMELINE' in page.get_data(as_text=True)
    items = navigation(client.get('/').get_data(as_text=True))
    assert any(n['href'] == '/archive/timeline' for n in items)
    assert 'id="updates"' not in client.get('/community').get_data(as_text=True)


def test_page_context_indexing_and_admin_routes(website):
    client = website.test_client()
    page = client.get('/awards/dancers-choice/2023').get_data(as_text=True)
    assert 'aria-label="Breadcrumb"' in page
    assert 'aria-label="Award program navigation"' in page
    assert 'href="/awards"' in page and 'href="/awards/dancers-choice"' in page
    assert client.get('/admin').status_code == 302
    with client.session_transaction() as session:
        session['ledger_admin_authenticated'] = True
    admin = client.get('/admin/dca/nominations')
    assert admin.status_code == 200
    assert 'class="ledger-admin-nav"' in admin.get_data(as_text=True)
    assert 'Admin' not in [x['label'] for x in navigation(admin.get_data(as_text=True))]
    sitemap = client.get('/sitemap.xml').get_data(as_text=True)
    for path in ['/archive/timeline','/awards','/community','/about','/awards/dancers-choice/2023']:
        assert 'https://thelitefeetvault.com'+path+'</loc>' in sitemap


def test_standings_share_card_is_public_query_aware_and_private(website):
    client = website.test_client()
    page = client.get('/awards/dancers-choice/nominations?view=results&email=private@example.com').get_data(as_text=True)
    head = page.split('</head>',1)[0]
    assert 'DCA 2026 Nominee Standings | The LiteFeet Vault' in head
    assert 'nominees and nomination totals across every category' in head
    assert 'https://thelitefeetvault.com/awards/dancers-choice/nominations?view=results' in head
    assert 'private@example.com' not in head
    assert 'property="og:image"' in head
    assert 'name="twitter:card" content="summary_large_image"' in head
    assert 'og:image:width" content="1200"' in head
    image = client.get('/static/social/dca-2026-standings-v1.png')
    assert image.status_code == 200 and image.mimetype == 'image/png'
    assert image.data[:8] == b'\x89PNG\r\n\x1a\n'
    assert struct.unpack('>II',image.data[16:24]) == (1200,630)
    nomination_head = client.get('/awards/dancers-choice/nominations').get_data(as_text=True).split('</head>',1)[0]
    assert "Nominate for Dancer" in nomination_head
    assert 'private@example.com' not in nomination_head


@pytest.mark.skipif(os.getenv('TEST_BROWSER') != '1',reason='Set TEST_BROWSER=1 for Chromium')
@pytest.mark.parametrize('width',[390,1440])
def test_nested_right_drawer_keyboard_and_program_links(website,width):
    from playwright.sync_api import sync_playwright
    server = make_server('127.0.0.1',0,website,threaded=True)
    thread = Thread(target=server.serve_forever,daemon=True);thread.start()
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch()
            page = browser.new_page(viewport={'width':width,'height':900})
            errors=[];page.on('pageerror',lambda error:errors.append(str(error)))
            base=f'http://127.0.0.1:{server.server_port}'
            page.goto(base+'/')
            trigger=page.get_by_role('button',name='Open site navigation')
            trigger.click()
            panel=page.get_by_role('dialog',name='Site navigation')
            assert panel.is_visible()
            page.screenshot(path=f'/tmp/vault-phase1-menu-{width}.png')
            assert abs(panel.bounding_box()['x']+panel.bounding_box()['width']-width) <= 1
            assert panel.locator('[data-section]').all_text_contents() == ['Home','The Archive','People & Teams','History & Timeline','Upcoming Calendar','Awards & Recognition','Lock In Card Battle Game','Music','About']
            assert page.locator('main').evaluate('node=>node.inert') is True
            page.keyboard.press('Shift+Tab')
            assert panel.locator('[data-section="about"]').evaluate('node=>node===document.activeElement')
            panel.locator('[data-section="awards"]').click()
            back=page.get_by_role('button',name='Back to main menu')
            assert back.evaluate('node=>node===document.activeElement')
            page.screenshot(path=f'/tmp/vault-phase1-submenu-{width}.png')
            assert panel.get_by_role('link',name='Dancer’s Choice Awards',exact=True).is_visible()
            back.click()
            assert panel.locator('[data-section="awards"]').evaluate('node=>node===document.activeElement')
            page.keyboard.press('Escape')
            assert trigger.evaluate('node=>node===document.activeElement')
            assert page.locator('main').evaluate('node=>node.inert') is False
            page.locator('.lfv-theme-button').click();page.reload()
            assert page.locator('html').get_attribute('data-theme') == 'dark'
            page.goto(base+'/awards')
            assert page.locator('main>header').evaluate('node=>getComputedStyle(node).backgroundColor') == 'rgba(0, 0, 0, 0)'
            assert page.locator('.vault-collection').count() == 2
            page.screenshot(path=f'/tmp/vault-phase1-awards-{width}.png',full_page=True)
            page.goto(base+'/awards/dancers-choice/2023')
            assert page.get_by_role('navigation',name='Breadcrumb').is_visible()
            assert page.get_by_role('navigation',name='Award program navigation').is_visible()
            page.get_by_role('button',name='Open site navigation').click()
            panel.locator('[data-section="awards"]').click()
            assert panel.get_by_role('link', name='Dancer’s Choice Awards', exact=True).is_visible()
            assert panel.get_by_role('link', name='DCA 2023 Archive').count() == 0
            page.locator('.lfv-menu-backdrop').click(position={'x':1,'y':1},force=True)
            assert not panel.is_visible()
            assert page.evaluate('document.documentElement.scrollWidth <= innerWidth')
            page.screenshot(path=f'/tmp/vault-phase1-{width}.png',full_page=True)
            # Public shell must not remove the authenticated admin toolbar.
            with website.test_client() as client:
                with client.session_transaction() as session:
                    session['ledger_admin_authenticated'] = True
                cookie = client.get_cookie('session')
            page.context.add_cookies([{'name':'session','value':cookie.value,'url':base}])
            page.goto(base+'/admin/dca/nominations')
            assert page.locator('.ledger-admin-nav[data-lfv-admin-toolbar]').is_visible()
            assert page.locator('.lfv-shell').count() == 1
            page.get_by_role('button',name='Open site navigation').click()
            assert 'Admin' not in page.locator('.lfv-menu-list').inner_text()
            page.keyboard.press('Escape')
            assert errors == []
            fallback=browser.new_page(java_script_enabled=False)
            fallback.goto(base+'/')
            assert fallback.get_by_role('navigation',name='Main navigation').is_visible()
            assert fallback.get_by_role('link',name='Home',exact=True).first.is_visible()
            browser.close()
    finally:
        server.shutdown();thread.join(timeout=5)


def test_awards_overview_and_hypeitup_are_integrated_and_vault_branded(website):
    client = website.test_client()
    overview = client.get('/awards')
    assert overview.status_code == 200
    text = overview.get_data(as_text=True)
    assert 'three distinct awards programs' in text
    assert 'Two distinct awards programs' not in text
    for name, href in [
        ('Dancer’s Choice Awards', '/awards/dancers-choice'),
        ('LiteFeet Awards', '/awards/litefeet-awards'),
        ('HypeItUpTV Awards', '/awards/hypeitup'),
    ]:
        assert name in text
        assert f'href="{href}"' in text

    hype = client.get('/awards/hypeitup')
    assert hype.status_code == 200
    body = hype.get_data(as_text=True)
    assert 'HypeItUpTV Awards' in body
    assert 'THE LITEFEET VAULT / AWARDS' in body
    assert 'LITEFEET LEDGER' not in body.upper()
    assert 'href="/awards"' in body
    assert 'aria-label="Award program navigation"' in body
    assert 'HypeItUpTV Awards | The LiteFeet Vault' in body.split('</head>', 1)[0]

    nav = next(item for item in navigation(text) if item['key'] == 'awards')
    assert [child['href'] for child in nav['children']] == [
        '/awards/dancers-choice', '/awards/litefeet-awards',
        '/awards/hypeitup',
    ]
    assert nav['children'][0]['label'] == 'Dancer’s Choice Awards'

    for path in ('/awards/dancers-choice/2026', '/awards/dancers-choice/2023',
                 '/awards/dancers-choice/nominations?view=results',
                 '/awards/litefeet-awards', '/awards/hypeitup'):
        page = client.get(path).get_data(as_text=True)
        assert 'aria-label="Award program navigation"' in page
        assert 'href="/awards/hypeitup"' in page
        assert 'href="/awards/litefeet-awards"' in page
        assert 'href="/awards/dancers-choice"' in page
        program_nav = page.split('aria-label="Award program navigation"', 1)[1].split('</nav>', 1)[0]
        assert 'DCA 2026' not in program_nav
        assert 'DCA 2023' not in program_nav

    # Year-specific pages are discoverable inside the Dancer's Choice Awards hub.
    dca_hub = client.get('/awards/dancers-choice').get_data(as_text=True)
    assert 'href="/awards/dancers-choice/2026"' in dca_hub
    assert 'href="/awards/dancers-choice/2023"' in dca_hub

    archive = client.get('/archive/timeline').get_data(as_text=True)
    nav_content = archive.split('aria-label="ARCHIVE NAVIGATION"', 1)[1].split('</nav>', 1)[0]
    assert 'PEOPLE &amp; TEAMS' in nav_content
    assert '>AWARDS</a>' in nav_content
    assert '2023 AWARDS' not in nav_content
    assert 'PEOPLE &amp; CREWS' not in nav_content


def test_archive_overview_and_unpublished_media(website):
    client = website.test_client()
    assert client.get('/archive').status_code == 200
    assert 'Submit to the Archive' in client.get('/archive').get_data(as_text=True)
    assert client.get('/archive?collection=people').status_code == 302
    assert client.get('/media').status_code == 404
    assert client.get('/calendar').status_code == 200
    nav = navigation(client.get('/').get_data(as_text=True))
    assert not next(row for row in nav if row['key'] == 'archive')['children']
