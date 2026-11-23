"""The 2026 LiteFeet Awards keeps announced nominee slates and winners separate."""
from types import SimpleNamespace
from dca_rebuild.lfa_2026_data import LFA_2026_NOMINEES, LFA_2026_WINNERS
from dca_rebuild.public_profiles import PublicProfileIndex


def test_six_documented_flyers_keep_all_original_names():
    assert len(LFA_2026_NOMINEES) == 6
    assert all(len(nominees) == 5 for nominees in LFA_2026_NOMINEES.values())
    assert LFA_2026_NOMINEES["Kid of the Year"] == (
        "Cito", "XO Wavy", "Lexii", "Taylah Gang", "Ash Rocket")
    assert "A Haundro" in LFA_2026_NOMINEES["Rookie of the Year"]
    assert "A Handro" not in LFA_2026_NOMINEES["Rookie of the Year"]
    assert "Shaker of the Year" not in LFA_2026_NOMINEES


def test_nominee_only_gets_nomination_not_unearned_win():
    index = PublicProfileIndex([], [], [], [
        SimpleNamespace(year=2026, category_name=category,
                        person_name=winner)
        for category, winner in LFA_2026_WINNERS
    ])
    cito = index.by_name("Cito")
    assert cito is not None
    assert not cito["wins"]
    assert len(cito["nominations"]) == 1
    assert cito["nominations"][0]["program"] == "LiteFeet Awards"
    assert index.href("Cito") == "/people/cito"
    xo = index.by_name("XO Wavy")
    assert any(row["category"] == "Kid of the Year" for row in xo["wins"])
    assert any(row["category"] == "Kid of the Year" for row in xo["nominations"])
    shaker = index.by_name("D Ski")
    assert any(row["category"] == "Shaker of the Year" for row in shaker["wins"])
    assert not shaker["nominations"]


def test_nominees_render_on_both_year_and_directory_pages(website, database):
    from dca_rebuild.seed_awards import seed_lfa_2026
    with database[1].begin() as db:
        seed_lfa_2026(db)
    for path in ("/awards/litefeet-awards", "/awards/litefeet-awards/2026"):
        response = website.test_client().get(path)
        assert response.status_code == 200
        html = response.get_data(as_text=True)
        assert html.count('class="lfa-category lfa-category--grammys"') == 7
        assert 'href="/people/cito"' in html
        assert "NOMINEES" in html  # nominees visibly labeled
        assert "Original nominee list not yet documented." in html
        assert html.count('<details class="lfa-category lfa-category--grammys">') == 7
        assert "<summary>" in html
        assert "<strong>XO Wavy</strong>" in html
