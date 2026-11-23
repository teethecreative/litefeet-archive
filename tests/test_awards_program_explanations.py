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

def test_lfa_archive_public_and_submission_closed(website):
    client = website.test_client()
    landing = client.get("/awards/litefeet-awards")
    assert landing.status_code == 200
    content = landing.get_data(as_text=True)
    assert "LITEFEET" in content
    assert "The LiteFeet Awards are an established awards program" in content
    assert 'name="submission_type"' not in content
    assert 'action="/awards/litefeet-awards/submit"' not in content
    assert client.get("/awards/litefeet-awards/2026").status_code == 200
    assert client.get("/litefeet-awards").status_code == 302
    assert client.post("/awards/litefeet-awards/submit", data={
        "submission_type": "nomination", "year": "2026",
        "category_name": "Example", "winner_name": "Example"
    }).status_code == 410
    assert client.get("/awards/dancers-choice").status_code == 200
