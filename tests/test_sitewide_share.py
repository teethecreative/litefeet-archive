"""Regression coverage for the sitewide icon and social share experience."""
from html import unescape
import re
import struct
from dca_rebuild.share_sitewide import VERSION


def head(response):
    return response.get_data(as_text=True).split("</head>", 1)[0]


def test_sitewide_icons_and_manifest(website):
    client = website.test_client()
    for path in ("/", "/write-ins", "/awards", "/calendar", "/archive/timeline"):
        response = client.get(path)
        assert response.status_code == 200
        markup = head(response)
        assert f'/favicon.ico?v={VERSION}' in markup
        assert f'/static/favicon-32x32.png?v={VERSION}' in markup
        assert f'/static/favicon-16x16.png?v={VERSION}' in markup
        assert f'/static/apple-touch-icon.png?v={VERSION}' in markup
        assert f'/site.webmanifest?v={VERSION}' in markup
        assert markup.count('rel="icon"') == 3
        assert markup.count('rel="canonical"') == 1
    assert client.get("/favicon.ico").status_code == 200
    assert client.get("/favicon.ico").data[:4] == bytes.fromhex("00000100")
    manifest = client.get("/site.webmanifest")
    assert manifest.status_code == 200
    assert manifest.get_json()["name"] == "The LiteFeet Vault"


def test_share_dialog_on_public_pages_and_no_private_leaks(website):
    client = website.test_client()
    for path in ("/", "/write-ins", "/awards"):
        html = client.get(path).get_data(as_text=True)
        assert 'id="lfv-share-dialog"' in html
        assert 'id="lfv-page-controls"' in html
        assert 'id="lfv-page-options"' in html
        assert 'id="lfv-awards-controls"' not in html
        assert 'data-lfv-format="story"' in html
        assert 'data-lfv-format="post"' in html
        assert 'id="lfv-copy-link"' in html
        assert 'js/vault-share.js' in html
    assert 'id="lfv-share-dialog"' not in client.get("/admin").get_data(as_text=True)


def test_instagram_graphics_have_correct_dimensions(website):
    client = website.test_client()
    for fmt, size in (("story", (1080, 1920)), ("post", (1080, 1350))):
        response = client.get(f"/social/instagram/{fmt}/write-ins.png")
        assert response.status_code == 200
        assert response.mimetype == "image/png"
        assert response.data[:8] == bytes.fromhex("89504e470d0a1a0a")
        assert struct.unpack(">II", response.data[16:24]) == size
    assert client.get("/social/instagram/reel/write-ins.png").status_code == 404


def test_share_previews_use_canonical_urls_without_private_query_strings(website):
    client = website.test_client()
    result = client.get("/write-ins?q=Example&email=private@example.org")
    markup = head(result)
    assert 'https://thelitefeetvault.com/write-ins' in markup
    assert 'private@example.org' not in markup
    assert markup.count('property="og:title"') == 1
    assert markup.count('name="twitter:card"') == 1
    assert 'social/cards/write-ins.png' in markup

def test_share_builder_only_reads_the_current_page_source(website):
    client = website.test_client()
    script = client.get("/static/js/vault-share.js").get_data(as_text=True)
    assert 'document.querySelector("main")' in script
    assert 'page.querySelectorAll("dl")' not in script  # Facts are read from the scoped root.
    assert 'root.querySelectorAll("dl")' in script
    assert 'root.querySelectorAll(lists.join(","))' in script
    assert 'MAX_ITEMS = 6' in script
    assert 'URL.createObjectURL(blob)' in script
    assert '/social/awards/options.json' not in script
    assert '/social/instagram/' not in script
    assert 'getComputedStyle(element)' in script
    assert 'node.closest(".lfv-archive-battles")' in script


def test_page_share_ui_excludes_off_page_content_chooser(website):
    client = website.test_client()
    for path in ("/", "/about", "/calendar", "/archive/timeline", "/awards/dancers-choice/2026"):
        response = client.get(path)
        assert response.status_code == 200
        html = response.get_data(as_text=True)
        assert 'id="lfv-page-options"' in html
        assert 'this page only' in html
        assert 'id="lfv-awards-category"' not in html
        assert 'id="lfv-share-image"' in html
        assert 'id="lfv-save-image"' in html
