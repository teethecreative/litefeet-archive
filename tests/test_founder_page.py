"""Vault origin-story page and expandable section regression checks."""


def test_story_page_is_public_and_preserves_original_letter(website):
    response = website.test_client().get("/about/our-story")
    assert response.status_code == 200
    html = response.get_data(as_text=True)
    assert 'id="vault-story"' in html
    assert "<h1>Why The Vault Exists</h1>" in html
    assert "Dear LiteFeet," in html
    assert "Because LiteFeet's history belongs to the people who made it." in html
    assert "With love for the culture," in html
    assert "lfv-story-page.css" in html
    assert "lfv-story-page.js" in html
    assert 'href="/archive"' in html
    assert 'href="/community#contribute"' in html


def test_story_topics_expand_beneath_navigation(website):
    html = website.test_client().get("/about/our-story").get_data(as_text=True)
    for topic in ("beginning", "culture", "people", "roots", "timeline", "process"):
        assert f'id="story-toggle-{topic}"' in html
        assert f'aria-controls="story-panel-{topic}"' in html
        assert f'id="story-panel-{topic}"' in html
    assert html.index('class="lfv-story-nav"') < html.index('id="story-details"')
    assert html.count('data-story-toggle') == 6
    assert html.count('data-story-panel hidden') == 6


def test_legacy_founder_link_redirects_to_story(website):
    response = website.test_client().get("/about/founder")
    assert response.status_code == 301
    assert response.headers["Location"].endswith("/about/our-story")


def test_home_story_card_links_to_story(website):
    response = website.test_client().get("/")
    assert response.status_code == 200
    html = response.get_data(as_text=True)
    assert 'href="/about/our-story">Read Our Story' in html
    assert "Meet the founder" not in html


def test_about_page_links_to_story_and_keeps_letter(website):
    response = website.test_client().get("/about")
    assert response.status_code == 200
    html = response.get_data(as_text=True)
    assert 'id="letter"' in html
    assert 'href="/about/our-story"' in html
