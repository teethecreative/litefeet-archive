"""Short branded links and page-specific crawler previews."""
import struct

def _head(response):
    return response.get_data(as_text=True).split("</head>", 1)[0]


def test_writeins_short_url_preserves_legacy_and_search(website):
    client = website.test_client()
    for path in ("/write-ins", "/awards/dancers-choice/write-ins"):
        response = client.get(path + "?q=Category")
        assert response.status_code == 200, path
        head = _head(response)
        assert "Write-In Categories | Dancer" in head
        assert '<link rel="canonical" href="https://thelitefeetvault.com/write-ins">' in head
        assert '<meta property="og:url" content="https://thelitefeetvault.com/write-ins">' in head
        assert '<meta name="twitter:url" content="https://thelitefeetvault.com/write-ins">' in head
        assert '<meta property="og:image" content="https://thelitefeetvault.com/social/write-ins.png">' in head
        assert "Help shape" not in head or "categories" in head
        assert "q=Category" not in head
        assert 'action="/write-ins"' in response.get_data(as_text=True)
    assert "https://thelitefeetvault.com/write-ins</loc>" in client.get("/sitemap.xml").get_data(as_text=True)


def test_sitewide_previews_are_distinct_and_have_images(website):
    client = website.test_client()
    pages = {
        "/": "The LiteFeet Vault | LiteFeet Culture",
        "/archive": "The Archive | The LiteFeet Vault",
        "/awards": "Awards | The LiteFeet Vault",
        "/about": "About The LiteFeet Vault",
        "/awards/dancers-choice/2026": "Dancer's Choice Awards 2026",
    }
    for path, title in pages.items():
        response = client.get(path)
        assert response.status_code == 200, path
        head = _head(response)
        assert title in head, path
        assert 'property="og:description"' in head
        assert 'property="og:image" content="https://thelitefeetvault.com/social/vault.png"' in head
        assert 'name="twitter:card" content="summary_large_image"' in head
        assert 'property="og:url" content="https://thelitefeetvault.com' + path + '"' in head


def test_social_assets_are_png_1200_by_630_and_standings_keeps_own_card(website):
    client = website.test_client()
    for path in ("/social/vault.png", "/social/write-ins.png"):
        response = client.get(path)
        assert response.status_code == 200
        assert response.mimetype == "image/png"
        assert response.data[:8] == b"\\x89PNG\\r\\n\\x1a\\n"
        assert struct.unpack(">II", response.data[16:24]) == (1200, 630)
        assert "public" in response.headers["Cache-Control"]
    assert client.get("/social/invalid.png").status_code == 404
    head = _head(client.get("/awards/dancers-choice/nominations?view=results&email=secret@example.org"))
    assert "dca-2026-standings-v1.png" in head
    assert "secret@example.org" not in head
