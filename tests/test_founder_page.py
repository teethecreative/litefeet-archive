"""One canonical About page with founder letter and interactive story topics."""


def test_about_page_is_story_and_preserves_letter(website):
    response = website.test_client().get("/about")
    assert response.status_code == 200
    html = response.get_data(as_text=True)
    assert 'id="vault-story"' in html
    assert "<h1>Why The Vault Exists</h1>" in html
    assert "Dear LiteFeet," in html
    assert "How much of our history do we actually have documented" in html
    assert "We can't change what was never documented" in html
    assert "With love for the culture," in html
    assert html.index('id="explore"') < html.index('id="letter"')
    assert html.index('id="letter"') < html.index('class="lfv-story-next"')
    assert "lfv-story-page.css" in html
    assert "20261123b" in html
    assert "lfv-story-page.js" in html
    assert 'href="/archive"' in html
    assert 'href="/community#contribute"' in html


def test_about_topics_expand_beneath_navigation(website):
    html = website.test_client().get("/about").get_data(as_text=True)
    for topic in ("beginning", "culture", "people", "roots", "timeline", "process"):
        assert f'id="story-toggle-{topic}"' in html
        assert f'aria-controls="story-panel-{topic}"' in html
        assert f'id="story-panel-{topic}"' in html
    assert html.index('class="lfv-story-nav"') < html.index('id="story-details"')
    assert html.count("data-story-toggle") == 6
    assert html.count("data-story-panel hidden") == 6


def test_old_about_urls_redirect_to_one_page(website):
    for path in ("/about/founder", "/about/our-story"):
        response = website.test_client().get(path)
        assert response.status_code == 301
        assert response.headers["Location"].endswith("/about")


def test_home_card_links_to_single_about_page(website):
    response = website.test_client().get("/")
    assert response.status_code == 200
    html = response.get_data(as_text=True)
    assert 'href="/about">Read Our Story' in html
    assert "Meet the founder" not in html


def test_about_letter_uses_available_card_width():
    from pathlib import Path
    root = Path(__file__).resolve().parents[1]
    css = (root / "dca_rebuild" / "static" / "css" / "lfv-story-page.css").read_text()
    assert ".lfv-story-letter-body {\n  width:100%;\n  max-width:none;" in css
    assert "max-width:73ch" not in css
