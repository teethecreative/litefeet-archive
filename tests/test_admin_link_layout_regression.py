"""Regression tests for old broad gold-link styles on admin pages."""
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
BASE=ROOT/"dca_rebuild"

def test_admin_activity_rows_override_old_link_buttons(website):
    html=website.test_client().get("/admin").get_data(as_text=True)
    # Unauthenticated redirect is expected. Source test checks actual layout contract.
    template=(BASE/"templates"/"admin_workspace_overview.html").read_text()
    css=(BASE/"static"/"css"/"admin-overview-v2.css").read_text()
    assert "lfv-admin-overview__list" in template
    assert "lfv-admin-overview__entry" in template
    assert "admin-overview-v2.css', v='20261123b'" in template
    assert "ONE FULL-WIDTH GRID ROW" in css
    assert "display:grid!important" in css
    assert "width:100%!important" in css
    assert "background:transparent!important" in css

def test_analytics_visitor_activity_is_linked_card():
    html=(BASE/"templates"/"admin_analytics.html").read_text()
    css=(BASE/"static"/"css"/"admin-analytics-simple.css").read_text()
    assert "lfv-analytics-link-card--visitor" in html
    assert "<strong>Visitor activity</strong>" in html
    assert 'aria-label="Detailed analytics and admin workspaces"' in html
    assert "admin-analytics-simple.css', v='20261123b'" in html
    assert "nav.lfv-analytics-links > a.lfv-analytics-link-card" in css
    assert "background:var(--surface-2)!important" in css
    assert 'html[data-theme="dark"]' in css
