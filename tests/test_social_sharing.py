"""Exhaustive public URL and social metadata regression checks."""
import re
import struct
import xml.etree.ElementTree as ET
from html import unescape
from urllib.parse import urlsplit

from dca_rebuild.seo import metadata_for_path

def _head(res):
    return res.get_data(as_text=True).split("</head>", 1)[0]

def _meta(head, attribute, name):
    matches = re.findall(r'<meta\s+[^>]*'+re.escape(attribute)+
                         r'="'+re.escape(name)+r'"[^>]*>', head)
    assert len(matches) == 1, (attribute, name, len(matches))
    value = re.search(r'content="([^"]+)"', matches[0])
    assert value, name
    return unescape(value.group(1))

def test_old_writeins_links_redirect_to_canonical_and_preserve_search(website):
    client = website.test_client()
    for legacy, target in [
        ("/awards/dancers-choice/write-ins", "/write-ins"),
        ("/awards/dancers-choice/write-ins?q=Category", "/write-ins?q=Category"),
    ]:
        response = client.get(legacy)
        assert response.status_code == 301
        assert response.headers["Location"] == target
    res = client.get("/write-ins?q=Category")
    assert res.status_code == 200
    head = _head(res)
    assert _meta(head, "property", "og:url") == "https://thelitefeetvault.com/write-ins"
    assert _meta(head, "name", "twitter:url") == "https://thelitefeetvault.com/write-ins"
    assert _meta(head, "property", "og:image").endswith("/social/cards/write-ins.png")
    assert "q=Category" not in head
    assert 'action="/write-ins"' in res.get_data(as_text=True)

def test_public_sitemap_pages_have_consistent_unique_metadata_and_valid_images(website):
    client = website.test_client()
    sitemap = client.get("/sitemap.xml")
    assert sitemap.status_code == 200
    xml = ET.fromstring(sitemap.data)
    urls = [node.text for node in xml.findall(".//{*}loc")]
    assert len(urls) == len(set(urls)), "Duplicate sitemap entries"
    assert len(urls) > 35, "Expected public archive records, not just navigation"
    assert "https://thelitefeetvault.com/write-ins" in urls
    assert "https://thelitefeetvault.com/archive/people" in urls
    assert "https://thelitefeetvault.com/music" in urls
    assert not any(urlsplit(url).path in ("/archive", "/media", "/archive/history") for url in urls)
    assert any("/music/" in url for url in urls)
    assert any("/music/" in url for url in urls)
    for url in urls:
        path = urlsplit(url).path
        res = client.get(path)
        assert res.status_code == 200, (path, res.status_code)
        head = _head(res)
        with website.app_context():
            meta = metadata_for_path(path)
        assert meta is not None, path
        title = re.search(r'<title[^>]*>(.*?)</title>', head, re.S)
        assert title and unescape(title.group(1)).strip() == meta["title"], path
        assert _meta(head, "name", "description") == meta["description"], path
        assert 30 <= len(meta["description"]) <= 200, path
        assert _meta(head, "property", "og:title") == meta["title"], path
        assert _meta(head, "property", "og:description") == meta["description"], path
        assert _meta(head, "name", "twitter:title") == meta["title"], path
        assert _meta(head, "name", "twitter:description") == meta["description"], path
        assert _meta(head, "property", "og:url") == url, path
        assert _meta(head, "name", "twitter:url") == url, path
        image_url = _meta(head, "property", "og:image")
        assert image_url.startswith("https://thelitefeetvault.com/social/cards/"), path
        assert _meta(head, "name", "twitter:image") == image_url, path
        assert _meta(head, "property", "og:image:width") == "1200", path
        assert _meta(head, "property", "og:image:height") == "630", path
        assert _meta(head, "name", "twitter:card") == "summary_large_image", path
        assert head.count('<link rel="canonical"') == 1, path
        asset = client.get(urlsplit(image_url).path)
        assert asset.status_code == 200, (path, image_url)
        assert asset.mimetype == "image/png", image_url
        assert asset.data[:8] == bytes.fromhex("89504e470d0a1a0a")
        assert struct.unpack(">II", asset.data[16:24]) == (1200, 630)

def test_query_privacy_and_special_standings_preview(website):
    client = website.test_client()
    res = client.get("/awards/dancers-choice/nominations?view=results&email=private@example.com&category=22")
    head = _head(res)
    assert _meta(head, "property", "og:url") == "https://thelitefeetvault.com/awards/dancers-choice/nominations?view=results"
    assert "private@example.com" not in head
    assert _meta(head, "property", "og:image").endswith("/static/social/dca-2026-standings-v1.png")
    assert _meta(head, "name", "twitter:card") == "summary_large_image"

def test_private_and_confirmation_urls_are_not_advertised(website):
    client = website.test_client()
    for path in ("/submit/thank-you", "/awards/litefeet-awards/submit", "/admin"):
        response = client.get(path)
        assert response.headers.get("X-Robots-Tag", "").startswith("noindex"), path
    assert client.get("/social/cards/not-real.png").status_code == 404
    robots = client.get("/robots.txt")
    assert robots.status_code == 200
    assert "https://thelitefeetvault.com/sitemap.xml" in robots.get_data(as_text=True)


def test_active_public_pages_have_specific_canonical_social_metadata(website):
    client = website.test_client()
    for path in ("/archive/people", "/litefeet-music",
                 "/litefeet-music/catalog/track/music-b1-001"):
        response = client.get(path)
        assert response.status_code == 200, path
        head = _head(response)
        assert _meta(head, "property", "og:url") == "https://thelitefeetvault.com" + path
        assert _meta(head, "name", "twitter:url") == "https://thelitefeetvault.com" + path
        assert head.count('<link rel="canonical"') == 1
        assert _meta(head, "name", "description")
        image = _meta(head, "property", "og:image")
        assert client.get(urlsplit(image).path).status_code == 200


def test_deleted_and_unpublished_section_urls_are_excluded_from_sitemap(website):
    client = website.test_client()
    root = ET.fromstring(client.get("/sitemap.xml").data)
    paths = {urlsplit(x.text).path for x in root.findall(".//{*}loc")}
    assert "/archive" not in paths
    assert "/media" not in paths
    assert "/archive/history" not in paths
    assert "/music" in paths
    assert "/archive/people" in paths


def test_calendar_event_sitemap_urls_resolve_and_have_metadata(website):
    client = website.test_client()
    urls = [n.text for n in ET.fromstring(client.get("/sitemap.xml").data).findall(".//{*}loc")]
    event_urls = [urlsplit(url).path for url in urls if "/events/" in url or "/calendar/events/" in url]
    for path in event_urls:
        response = client.get(path)
        assert response.status_code == 200, path
        assert _meta(_head(response), "property", "og:url") == "https://thelitefeetvault.com" + path
