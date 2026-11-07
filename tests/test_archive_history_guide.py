"""Sourced cultural-history guide, accessible Archive links and compact mobile layout."""
from pathlib import Path
from dca_rebuild.archive_history_guide import load_history_guide


def test_history_guide_is_curated_and_every_claim_is_cited():
    history = load_history_guide()
    assert len(history["chapters"]) == 11
    assert len(history["timeline"]) >= 10
    assert len(history["sources"]) >= 15
    assert len(set(chapter["id"] for chapter in history["chapters"])) == len(history["chapters"])
    assert all(source["url"].startswith("https://") for source in history["sources"].values())
    assert all(paragraph["sources"] for chapter in history["chapters"] for paragraph in chapter["paragraphs"])
    assert all(source_id in history["sources"] for chapter in history["chapters"]
               for paragraph in chapter["paragraphs"] for source_id in paragraph["sources"])


def test_history_guide_page_has_linked_sources_and_topic_navigation(website):
    client = website.test_client()
    response = client.get("/archive/history")
    assert response.status_code == 200
    text = response.get_data(as_text=True)
    assert "THE HISTORY OF LITEFEET" in text
    for anchor in (
        "what-is-litefeet", "harlem-shake", "early-get-lite",
        "people-crews", "movement-vocabulary", "music-history",
        "battles-spaces", "showtime", "beyond-new-york",
        "documentaries", "open-questions", "history-sources",
    ):
        assert 'id="' + anchor + '"' in text
    for source in ("smithsonianmag.com", "daily.redbullmusicacademy.com",
                   "vice.com", "iuda.dance", "steezy.co",
                   "factmag.com", "dance-enthusiast.com"):
        assert source in text
    assert "PUBLICATION" not in text.upper() or "RESEARCH" in text.upper()
    assert "ARCHIVE /" not in text  # No accidental admin-only notes.
    assert "editorial_notes" not in text
    assert "SOURCE 1:" in text
    assert "rel=\"noopener noreferrer\"" in text
    assert 'href="/archive"' in text


def test_archive_links_to_history_and_remains_compact(website):
    client = website.test_client()
    text = client.get("/archive").get_data(as_text=True)
    assert 'href="/archive/history"' in text
    assert "RESEARCH / 11 CHAPTERS" in text
    assert "archive-v3.css" in text
    assert "lfv-archive-row-meta" in text
    assert "lfv-archive-entry-date" in text
    assert "lfv-archive-entry-type" in text
    assert 'lfv-archive-entry-meta' not in text
    assert "VIEW HISTORICAL RESULTS" in text
    assert "READ THE RESEARCH" in text
    assert "HISTORY &amp; TIMELINE" in text
    assert "2023 AWARDS" in text
    assert "RESEARCH NOTES" not in text


def test_timeline_and_scroll_render_same_mini_record_structure(website):
    client = website.test_client()
    html = client.get("/archive/timeline").get_data(as_text=True)
    assert "lfv-archive-row-meta" in html
    assert "CHRONOLOGICAL TIMELINE" in html
    assert "lfv-archive-entry-date" in html
    assert 'href="/archive/history"' in html
    js = client.get("/static/js/archive-v1.js").get_data(as_text=True)
    assert "lfv-archive-row-meta" in js
    assert "lfv-archive-entry-type" in js
    css = client.get("/static/css/archive-v3.css").get_data(as_text=True)
    assert "grid-template-columns:minmax(0,1fr) 27px" in css
    assert ".lfv-archive-collection-grid>a" in css


def test_guide_seo_includes_canonical_and_sitemap_entry(website):
    client = website.test_client()
    page = client.get("/archive/history").get_data(as_text=True)
    head = page.split("</head>", 1)[0]
    assert "https://thelitefeetvault.com/archive/history" in head
    assert "History of LiteFeet, Get Lite" in head
    assert "https://thelitefeetvault.com/archive/history</loc>" in client.get(
        "/sitemap.xml").get_data(as_text=True)
