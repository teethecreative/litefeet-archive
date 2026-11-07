"""Source-linked research in unified timeline, with compact, safe progressive API."""
from dca_rebuild.archive_history_guide import load_history_guide
from dca_rebuild.timeline_catalog import all_timeline_entries


def test_guide_is_curated_and_claims_are_cited():
    history = load_history_guide()
    assert len(history["chapters"]) == 11
    assert len(history["timeline"]) >= 10
    assert len(history["sources"]) >= 15
    assert len(set(chapter["id"] for chapter in history["chapters"])) == 11
    assert all(source["url"].startswith("https://") for source in history["sources"].values())
    assert all(paragraph["sources"] for chapter in history["chapters"] for paragraph in chapter["paragraphs"])


def test_history_page_redirects_to_one_unified_timeline(website):
    client = website.test_client()
    response = client.get("/archive/history")
    assert response.status_code == 302
    assert response.headers["Location"].endswith("/archive/timeline")
    page = client.get("/archive/timeline").get_data(as_text=True)
    assert "HISTORY &amp; TIMELINE" in page
    assert 'data-unified-timeline' in page
    assert 'data-timeline-search' in page
    assert 'timeline-v2.js' in page
    assert 'lfv-consistency-v5.css' in page
    assert "NO MATCHING RECORDS" in page
    assert "editorial_notes" not in page


def test_all_research_chapters_and_milestones_are_in_timeline(website):
    entries = all_timeline_entries()
    chapters = [entry for entry in entries if entry["kind"] == "chapter"]
    milestones = [entry for entry in entries if entry["kind"] == "milestone"]
    events = [entry for entry in entries if entry["kind"] == "record"]
    assert len(chapters) == 11
    assert len(milestones) >= 10
    assert len(events) == 43
    assert all(chapter["detail"] and chapter["sources"] for chapter in chapters)
    client = website.test_client()
    history = client.get("/archive/api/records?timeline=1&collection=history&q=harlem+shake").get_json()
    assert history["total"] >= 2
    assert all(item["collection"] == "history" for item in history["records"])
    assert any(item["sources"] for item in history["records"])
    assert all("editorial_notes" not in item for item in history["records"])


def test_archive_links_to_unified_timeline_and_keeps_compact_rows(website):
    client = website.test_client()
    text = client.get("/archive").get_data(as_text=True)
    assert 'href="/archive/timeline"' in text
    assert "archive-v3.css" in text
    assert "data-unified-timeline" in text
    assert "SEARCH THE TIMELINE" in text
    assert "THE ARCHIVE TIMELINE" in text


def test_guide_seo_redirect_preserves_search_canonical(website):
    client = website.test_client()
    page = client.get("/archive/timeline").get_data(as_text=True)
    head = page.split("</head>", 1)[0]
    assert "https://thelitefeetvault.com/archive/timeline" in head
    sitemap = client.get("/sitemap.xml").get_data(as_text=True)
    assert "https://thelitefeetvault.com/archive/timeline</loc>" in sitemap
