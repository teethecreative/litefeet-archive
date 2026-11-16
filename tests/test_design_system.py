"""Regression checks for the shared LiteFeet Vault design foundation."""
from pathlib import Path
import re

REBUILD = Path(__file__).resolve().parents[1] / "dca_rebuild"
CSS = REBUILD / "static" / "css"


def read_css(name):
    return (CSS / name).read_text(encoding="utf-8")


def test_design_tokens_are_imported_once_and_not_redefined_by_editorial_v2():
    sitewide = read_css("litefeet-sitewide.css")
    editorial = read_css("lfv-editorial-v2.css")
    tokens = read_css("lfv-design-tokens.css")

    assert sitewide.count('@import url("./lfv-design-tokens.css");') == 1
    assert sitewide.count('@import url("./lfv-ui-components.css");') == 1
    assert '--vault-color-navy: #0a2c5f;' in tokens
    assert '--vault-color-gold: #c9a127;' in tokens
    assert '--lfv-navy: var(--vault-color-navy);' in tokens
    assert '--lfv-gold: var(--vault-color-gold);' in tokens
    assert re.search(r'html\[data-theme="dark"\]', tokens)

    legacy_declaration = r'--lfv-(?:navy|gold|white|bg|surface(?:-muted)?|ink|muted|line|max|gutter|radius|font)\s*:'
    assert not re.search(legacy_declaration, sitewide)
    assert not re.search(legacy_declaration, editorial)
    assert 'var(--vault-color-navy, #0a2c5f)' in read_css("dca.css")
    assert 'var(--vault-color-gold, #c9a127)' in read_css("dca.css")


def test_public_design_assets_are_served(website):
    client = website.test_client()
    for name in ("lfv-design-tokens.css", "lfv-ui-components.css",
                 "litefeet-sitewide.css"):
        response = client.get("/static/css/" + name)
        assert response.status_code == 200, name
        assert b"404" not in response.data[:100], name


def test_archive_and_awards_use_reusable_header_markup(website):
    client = website.test_client()
    for path, heading in [("/archive", "The Archive"),
                          ("/awards", "Recognition from the culture.")]:
        response = client.get(path)
        assert response.status_code == 200, path
        html = response.get_data(as_text=True)
        assert '<header class="lfv-ui-page-header">' in html, path
        assert '<p class="vault-kicker lfv-ui-kicker">' in html, path
        assert '<p class="lfv-ui-lead">' in html, path
        assert heading in html, path
        assert "lfv-design-tokens.css" not in html  # Imported by shared sitewide CSS.
        assert 'css/litefeet-sitewide.css' in html, path


def test_component_actions_have_primary_secondary_and_keyboard_styles():
    components = read_css("lfv-ui-components.css")
    for selector in (".lfv-ui-action--primary", ".lfv-ui-action--secondary",
                     ".lfv-ui-field:focus-visible", ".lfv-ui-page-header"):
        assert selector in components
    assert "var(--vault-control-min-height)" in components
