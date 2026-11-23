"""Dedicated founder page, homepage discovery, and preserved letter."""


def test_founder_page_is_public_and_readable(website):
    response = website.test_client().get("/about/founder")
    assert response.status_code == 200
    html = response.get_data(as_text=True)
    assert 'id="vault-founder"' in html
    assert "Dear LiteFeet," in html
    assert "Because LiteFeet's history belongs to the people who made it." in html
    assert "Founder, The LiteFeet Vault" in html
    assert "lfv-founder-page.css" in html
    assert 'href="/about#mission"' in html
    assert 'href="/archive"' in html


def test_home_founder_card_links_to_dedicated_page(website):
    response = website.test_client().get("/")
    assert response.status_code == 200
    assert 'href="/about/founder">The Founder' in response.get_data(as_text=True)


def test_about_page_still_has_original_letter(website):
    response = website.test_client().get("/about")
    assert response.status_code == 200
    html = response.get_data(as_text=True)
    assert 'id="letter"' in html
    assert 'href="/about/founder"' in html
