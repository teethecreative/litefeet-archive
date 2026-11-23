"""Simplified analytics overview retains existing detailed report routes."""
def _admin(client):
    with client.session_transaction() as state:
        state["ledger_admin_authenticated"]=True

def test_analytics_simple_overview_and_drilldowns(website):
    client=website.test_client()
    assert client.get("/admin/analytics").status_code in (302,303,401,403)
    _admin(client)
    response=client.get("/admin/analytics?period=30days")
    assert response.status_code==200
    html=response.get_data(as_text=True)
    for item in ("At a glance","Page views","Visits","Browser identifiers",
                 "Returning identifiers","Top pages","Activity trend",
                 "Visitor activity","Traffic quality and technical breakdown"):
        assert item in html
    assert "admin-analytics-simple.css" in html
    assert client.get("/admin/analytics/visitors").status_code==200
    assert client.get("/admin/analytics?period=custom&start=2026-11-01&end=2026-11-15").status_code==200
    assert client.get("/admin/analytics?period=invalid&traffic=bad").status_code==400
