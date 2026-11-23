"""Public DCA/LFA program content stays distinct and nomination copy is not voting copy."""


def test_awards_hub_groups_results_under_dca(website):
    client = website.test_client()
    html = client.get("/awards").get_data(as_text=True)
    assert "Dancer’s Choice Awards" in html
    assert "LiteFeet Awards" in html
    assert "<h2>Historical Results</h2>" not in html
    assert 'href="/awards/dancers-choice"' in html


def test_dca_program_explains_origins_and_four_stages(website):
    client = website.test_client()
    html = client.get("/awards/dancers-choice").get_data(as_text=True)
    assert "The community chooses." in html
    for phrase in ("The Dancer’s Choice Awards were created",
                   "Suggest categories:", "Nominate:", "Top five:", "Vote:"):
        assert phrase in html
    assert 'href="/awards/dancers-choice/2026"' in html
    assert 'href="/awards/dancers-choice/2023"' in html


def test_dca_2026_has_two_main_actions_and_round_explanation(website):
    html = website.test_client().get("/awards/dancers-choice/2026").get_data(as_text=True)
    assert "NOMINATIONS ARE NOT VOTING" in html
    assert "TOP FIVE" in html
    assert 'href="/awards/dancers-choice/nominations"' in html
    assert "Category results" in html
    assert "Past editions" not in html


def test_nomination_page_separates_nomination_totals_from_final_votes(website):
    client = website.test_client()
    html = client.get("/awards/dancers-choice/nominations").get_data(as_text=True)
    assert "THIS IS THE NOMINATION ROUND, NOT THE FINAL VOTE." in html
    assert "Each valid nomination adds one" in html
    assert "The top five eligible nominees" in html


def test_lfa_explains_distinct_program(website):
    html = website.test_client().get("/awards/litefeet-awards").get_data(as_text=True)
    assert "The LiteFeet Awards are an established awards program" in html
    assert "The Dancer's Choice Awards are a separate, community-led program" in html


def test_lfa_2026_winners_publish_and_correction_is_idempotent(website, database):
    from dca_rebuild.seed_awards import seed_lfa_2026
    from dca_rebuild.models import LFARecord

    with database[1].begin() as db:
        db.add(LFARecord(
            year=2026, record_type="award_winner",
            category_name="LADY OF LITE", person_name="JADA CHANELL",
            team_name="2 Crafty", source_submission_id=2,
        ))
    with database[1].begin() as db:
        assert seed_lfa_2026(db) == (6, 1)
    with database[1].begin() as db:
        assert seed_lfa_2026(db) == (0, 0)
        rows = db.query(LFARecord).filter_by(year=2026, record_type="award_winner").all()
        assert len(rows) == 7
        lady = next(r for r in rows if r.category_name == "Lady of Lite")
        assert lady.person_name == "Ty Shotz"
        assert lady.source_submission_id is None
        assert "JADA CHANELL" in lady.additional_details

    for route in ("/awards/litefeet-awards", "/awards/litefeet-awards/2026"):
        response = website.test_client().get(route)
        assert response.status_code == 200
        html = response.get_data(as_text=True)
        for name in ("XO Wavy", "A Handro", "Speights Raw Kid", "D Ski",
                     "Ty Shotz", "Team Demon", "Jay Bull"):
            assert name in html
        assert "Jada Chanell" in html  # nominee, not winner
        assert "2026 LITEFEET AWARDS" in html


def test_lfa_directory_uses_compact_winner_rows_and_nominee_dropdowns(website):
    client = website.test_client()
    response = client.get("/awards/litefeet-awards")
    html = response.get_data(as_text=True)
    assert response.status_code == 200
    assert "THE LITEFEET VAULT" in html
    assert "2026 LITEFEET AWARDS" in html
    assert '<details class="lfa-category lfa-category--grammys">' in html
    assert html.count('<details class="lfa-category lfa-category--grammys">') == 7
    assert "<summary>" in html
    assert '<a href="/people/cito">Cito</a>' in html
    for name in ("Cito", "XO Wavy", "Lexii", "Taylah Gang", "Ash Rocket",
                 "Playdo", "A Haundro", "Red Robin", "Y Axis", "King Kai",
                 "Lil Live", "Phresh Tune", "Sound Wave", "Kid Smoove",
                 "Tiny Rillz", "Lady Live", "Jada Chanell", "2 Real Boyz",
                 "2 Crafty", "2 Live Krew", "Bomb Squad", "Noah Lot", "Tah Swag"):
        assert name in html
    assert "Nominee list not yet documented." in html
    assert "lfa-contribution-form" not in html
    assert 'action="/awards/litefeet-awards/submit"' not in html
    assert "HELP BUILD THE ARCHIVE" not in html
    assert client.post("/awards/litefeet-awards/submit", data={
        "submission_type": "award_winner", "year": "2026",
        "category_name": "Invented award", "winner_name": "Invented winner"
    }).status_code == 410


def test_lfa_previous_year_archive_has_no_submissions_cta(website):
    client = website.test_client()
    for year in (2023, 2024, 2025):
        response = client.get(f"/awards/litefeet-awards/{year}")
        assert response.status_code == 200
        html = response.get_data(as_text=True)
        assert "Results not yet documented" in html
        assert "CONTRIBUTE HISTORICAL INFORMATION" not in html
        assert 'href="/awards/litefeet-awards#contribute"' not in html


def test_homepage_announces_documented_lfa_2026_winners_in_own_brand(website, database):
    from dca_rebuild.seed_awards import seed_lfa_2026

    with database[1].begin() as db:
        assert seed_lfa_2026(db) == (7, 0)
    response = website.test_client().get("/")
    assert response.status_code == 200
    html = response.get_data(as_text=True)
    assert "Dear LiteFeet," in html
    assert "And the winners are" in html
    assert html.index("Dear LiteFeet,") < html.index("And the winners are")
    assert "THE LITEFEET AWARDS · 2026" in html
    assert "THE LITEFEET VAULT" in html
    assert "lfv-home-lfa-2026.css" in html
    assert 'href="/awards/litefeet-awards/2026"' in html
    for category, name in (
        ("Kid of the Year", "XO Wavy"),
        ("Rookie of the Year", "A Handro"),
        ("Producer of the Year", "Speights Raw Kid"),
        ("Shaker of the Year", "D Ski"),
        ("Lady of Lite", "Ty Shotz"),
        ("Best Team", "Team Demon"),
        ("I Am the Lite", "Jay Bull"),
    ):
        assert category in html
        assert name in html
    assert "Dancer’s Choice Awards 2026" in html
    assert "THIS MONTH IN LITEFEET" in html
    assert "Help Make It Happen" in html
    assert 'lfa-contribution-form' not in html


def test_homepage_does_not_invent_awards_before_results_exist(website):
    html = website.test_client().get("/").get_data(as_text=True)
    assert "Dear LiteFeet," in html
    assert "And the winners are" not in html



def test_sitewide_brand_public_templates_use_same_shell():
    from pathlib import Path
    templates = Path(__file__).resolve().parents[1] / "dca_rebuild" / "templates"
    for name in (
        "ledger_home.html",
        "lfa_home.html",
        "award_landing.html",
        "dca_nominations_form.html",
        "vault_calendar.html",
        "vault_calendar_event.html",
        "vault_submit.html",
        "vault_submit_success.html",
        "dca_verify_email.html",
        "error_404.html",
        "round1_success.html",
    ):
        html = (templates / name).read_text()
        assert "litefeet-sitewide.css" in html, name
        assert "lfv-editorial-v2.css" in html, name
        assert "_navigation.html" in html, name


def test_sitewide_palette_is_shared_across_awards():
    from pathlib import Path
    styles = (Path(__file__).resolve().parents[1]
              / "dca_rebuild" / "static" / "css")
    core = (styles / "dca.css").read_text()
    shell = (styles / "litefeet-sitewide.css").read_text()
    assert "--blue:var(--lfv-navy" in core
    assert "--gold:var(--lfv-gold" in core
    assert "--page:var(--lfv-bg" in core
    assert "LFV NOVEMBER 2026 BRAND CONSISTENCY" in shell


def test_awards_nav_has_no_retired_public_lfa_form(website):
    html = website.test_client().get("/awards/litefeet-awards/2026").get_data(as_text=True)
    assert "/awards/litefeet-awards#contribute" not in html


def test_theme_bootstrap_is_shared_between_public_admin_and_legacy():
    from pathlib import Path
    root = Path(__file__).resolve().parents[1]
    dca = root / "dca_rebuild"
    public = (dca / "templates" / "_navigation.html").read_text()
    admin = (dca / "templates" / "_admin_navigation.html").read_text()
    legacy = (root / "templates" / "base.html").read_text()
    for html in (public, admin, legacy):
        assert "lfv-theme-init.js" in html
    public_js = (dca / "static" / "js" / "litefeet-sitewide.js").read_text()
    admin_html = admin
    legacy_js = (root / "static" / "js" / "litefeet-sitewide.js").read_text()
    for text in (public_js, admin_html, legacy_js):
        assert "window.LFVTheme.set(next)" in text
        assert "lfv:themechange" in text
    theme_a = (dca / "static" / "js" / "lfv-theme-init.js").read_text()
    theme_b = (root / "static" / "js" / "lfv-theme-init.js").read_text()
    assert theme_a == theme_b
    assert "localStorage.setItem(KEY, theme)" in theme_a
    assert "window.addEventListener('storage'" in theme_a
    assert "root.style.colorScheme = theme" in theme_a


def test_theme_css_provides_both_mode_surfaces_and_lfa_selectors():
    from pathlib import Path
    root = Path(__file__).resolve().parents[1] / "dca_rebuild" / "static" / "css"
    css = (root / "litefeet-sitewide.css").read_text()
    lfa = (root / "lfa-results.css").read_text()
    assert 'html[data-theme="light"]' in css
    assert 'html[data-theme="dark"]' in css
    assert 'html:is(.lfv-root,.lfv-sitewide)' in lfa
    assert 'html[data-theme="dark"]:is(.lfv-root,.lfv-sitewide)' in lfa
