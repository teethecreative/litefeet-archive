"""Voluntary engagement and verified-email linkage are separate from basic traffic."""
from dca_rebuild.analytics_engagement import VaultPageEngagement, VaultAnalyticsIdentityLink

def test_optin_and_revoke_engagement(website, database):
    client=website.test_client()
    # Isolated tests do not install the production after-request visitor cookie hook.
    client.set_cookie("lf_ledger_visitor", "b"*32)
    assert client.get("/privacy/analytics").status_code==200
    with client.session_transaction() as state:
        csrf=state["lfv_privacy_form_token"]
    assert client.post("/privacy/analytics",data={"action":"enable","csrf_token":"wrong"}).status_code==400
    assert client.post("/analytics/engagement").status_code==403
    assert client.post("/privacy/analytics",data={"action":"enable","csrf_token":csrf,"agree":"yes","link_email":"yes"}).status_code==403
    enabled=client.post("/privacy/analytics",data={"action":"enable","csrf_token":csrf,"agree":"yes"})
    assert enabled.status_code==303
    with client.session_transaction() as state:
        token=state["lfv_engagement_token"]
    visitor=client.get_cookie("lf_ledger_visitor").value
    data={"instance":"a"*32,"path":"/","seconds":"22","token":token}
    agent={"User-Agent":"Mozilla/5.0 (Macintosh) Chrome/145"}
    assert client.post("/analytics/engagement",data=data,headers=agent).status_code==204
    assert client.post("/analytics/engagement",data=dict(data,seconds="35"),headers=agent).status_code==204
    with database[1]() as db:
        events=db.query(VaultPageEngagement).filter_by(visitor_id=visitor).all()
        assert len(events)==1 and events[0].active_seconds==35
        assert db.query(VaultAnalyticsIdentityLink).count()==0
    with client.session_transaction() as state:
        state["ledger_admin_authenticated"]=True
    dashboard=client.get("/admin/analytics?period=30days")
    assert dashboard.status_code==200
    assert "Avg. active time" in dashboard.get_data(as_text=True)
    assert client.post("/privacy/analytics",data={"action":"disable","csrf_token":csrf}).status_code==303
    with database[1]() as db:
        assert db.query(VaultPageEngagement).filter_by(visitor_id=visitor).count()==0

def test_existing_email_contacts_do_not_link_automatically(website, database):
    from dca_rebuild.models import DCANominationContact
    with database[1].begin() as db:
        db.add(DCANominationContact(submitter_hash="existing-hash",email_address="keptprivate@example.test"))
    client=website.test_client()
    client.get("/")
    with client.session_transaction() as state:
        state["ledger_admin_authenticated"]=True
    assert client.get("/admin/analytics/visitors").status_code==200
    with database[1]() as db:
        assert db.query(VaultAnalyticsIdentityLink).count()==0
