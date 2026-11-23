"""Compact homepage card layout and final calendar position."""
from pathlib import Path


def test_homepage_compact_cards_and_calendar_last(website, database):
    from dca_rebuild.seed_awards import seed_lfa_2026
    with database[1].begin() as db:
        seed_lfa_2026(db)
    response=website.test_client().get("/")
    assert response.status_code==200
    html=response.get_data(as_text=True)
    assert 'class="lfv-home-compact-grid"' in html
    assert 'class="lfv-home-compact-card lfv-home-compact-card--lfa"' in html
    assert 'class="lfv-home-compact-card lfv-home-compact-card--founder"' in html
    assert 'class="lfv-home-compact-card lfv-home-compact-card--dca"' in html
    assert 'class="lfv-home-compact-card lfv-home-compact-card--community"' in html
    assert html.index("And the winners are") < html.index("Dear LiteFeet,")
    assert html.index("Dear LiteFeet,") < html.index('id="whats-new"')
    assert "THIS MONTH IN LITEFEET" in html
    assert "lfv5-calendar-strip" in html
    assert "lfv-home-compact.css" in html
    for name in ("XO Wavy","A Handro","Speights Raw Kid","D Ski","Ty Shotz","Team Demon","Jay Bull"):
        assert name in html


def test_compact_home_styles_support_both_themes():
    root=Path(__file__).resolve().parents[1]
    css=(root/"dca_rebuild"/"static"/"css"/"lfv-home-compact.css").read_text()
    assert "var(--lfv-surface)" in css
    assert "var(--lfv-ink)" in css
    assert "html[data-theme=\"dark\"]" in css
    assert "@media(max-width:720px)" in css
