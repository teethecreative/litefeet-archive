"""Regression coverage for the sitewide icon and social share experience."""
from html import unescape
import re
import struct


def head(response):
    return response.get_data(as_text=True).split("</head>", 1)[0]


def test_sitewide_icons_and_manifest(website):
    client = website.test_client()
    for path in ("/", "/write-ins", "/awards", "/calendar", "/archive/timeline"):
        response = client.get(path)
        assert response.status_code == 200
        markup = head(response)
        assert '/favicon.ico?v=20261109' in markup
        assert '/static/favicon-32x32.png?v=20261109' in markup
        assert '/static/favicon-16x16.png?v=20261109' in markup
        assert '/static/apple-touch-icon.png?v=20261109' in markup
        assert '/site.webmanifest?v=20261109' in markup
        assert markup.count('rel="icon"') == 3
        assert markup.count('rel="canonical"') == 1
    assert client.get("/favicon.ico").status_code == 200
    assert client.get("/favicon.ico").data[:4] == b"\\x00\\x00\\x01\\x00"
    manifest = client.get("/site.webmanifest")
    assert manifest.status_code == 200
    assert manifest.get_json()["name"] == "The LiteFeet Vault"


def test_share_dialog_on_public_pages_and_no_private_leaks(website):
    client = website.test_client()
    for path in ("/", "/write-ins", "/awards"):
        html = client.get(path).get_data(as_text=True)
        assert 'id="lfv-share-dialog"' in html
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
    assert client.get("/social/instagram/story/not-real-format.png").status_code == 200


def test_share_previews_use_canonical_urls_without_private_query_strings(website):
    client = website.test_client()
    result = client.get("/write-ins?q=Example&email=private@example.org")
    markup = head(result)
    assert 'https://thelitefeetvault.com/write-ins' in markup
    assert 'private@example.org' not in markup
    assert markup.count('property="og:title"') == 1
    assert markup.count('name="twitter:card"') == 1
    assert 'social/cards/write-ins.png' in markup
