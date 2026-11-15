"""Synthetic fixtures exercise relationships; none are historical claims."""
import copy
import json
import sqlite3
import os
import subprocess
import sys

import pytest

from dca_rebuild.archive_foundation import stage_snapshot
from dca_rebuild.archive_graph import (
    ReviewConflict, connected_path, decide_connection, graph_workspace, propose_connection,
)


@pytest.fixture
def graph(tmp_path):
    records = [dict(system='test_fixture', key=key, title=title, kind=kind,
                    visibility='private_review', payload=payload) for key, title, kind, payload in (
        ('dancer', 'Test Dancer', 'person', {'aliases': ['Earlier Name']}),
        ('team', 'Test Team', 'team', {}),
        ('event', 'Test Event', 'event', {'event_date': '2010', 'date_certainty': 'approximate'}),
        ('battle', 'Test Battle', 'battle', {}),
        ('footage', 'Test Footage', 'footage', {'upload_date': '2012-03-04'}),
        ('track', 'Test Track', 'track', {}),
        ('other', 'Another Source Name', 'person', {}),
    )]
    path = tmp_path / 'graph.staging.sqlite'
    stage_snapshot(path, records)
    with sqlite3.connect(path) as db:
        ids = dict(db.execute('SELECT source_key,entity_id FROM source_crosswalk'))
        revisions = dict(db.execute('SELECT c.source_key,r.id FROM source_crosswalk c JOIN source_revisions r ON r.entity_id=c.entity_id'))
    return path, ids, revisions, records


def propose(graph, first='dancer', relation='member_of', second='team', **kwargs):
    path, ids, revisions, _ = graph
    return propose_connection(path, ids[first], relation, ids[second], revisions[first],
                              'admin-session:test', 'Synthetic source explicitly supports this test relation.', **kwargs)


def decide(graph, link, action='approve', version=1, reason='Reviewed fixture evidence.'):
    decide_connection(graph[0], link, action, version, 'admin-session:reviewer', reason)


def test_full_dancer_team_event_battle_footage_path_and_reversal(graph):
    path, ids, _, _ = graph
    links = [propose(graph, details={'from': '2009', 'until': '2011', 'date_certainty': 'approximate'}),
             propose(graph, 'team', 'participated_in', 'event', details={'role': 'team'}),
             propose(graph, 'event', 'contains_battle', 'battle'),
             propose(graph, 'battle', 'documented_by', 'footage', details={'start_seconds': 35, 'end_seconds': 92})]
    assert connected_path(path, ids['dancer'], ids['footage']) is None
    for link in links:
        decide(graph, link)
    route = connected_path(path, ids['dancer'], ids['footage'])
    assert [r['relation'] for r in route] == ['member_of', 'participated_in', 'contains_battle', 'documented_by']
    assert all(r['evidence_revision_id'] for r in route)
    assert json.loads(route[-1]['details_json']) == {'start_seconds': 35, 'end_seconds': 92}
    assert len(connected_path(path, ids['footage'], ids['dancer'])) == 4
    decide(graph, links[1], 'reverse', 2, 'Source connection withdrawn after review.')
    assert connected_path(path, ids['dancer'], ids['footage']) is None
    reversed_link = graph_workspace(path, 'reversed')['links'][0]
    assert [h['status'] for h in reversed_link['history']] == ['pending', 'approved', 'reversed']
    assert reversed_link['history'][-1]['reason'] == 'Source connection withdrawn after review.'
    decide(graph, links[1], 'reopen', 3)
    decide(graph, links[1], 'approve', 4)
    assert len(connected_path(path, ids['dancer'], ids['footage'])) == 4
    assert len(graph_workspace(path, 'approved')['links'][1]['history']) >= 2


def test_multiple_roles_music_aliases_and_unknown_outcomes(graph):
    path, ids, _, _ = graph
    dancer = propose(graph, 'dancer', 'participated_in', 'battle', details={'role': 'dancer'})
    judge = propose(graph, 'dancer', 'participated_in', 'battle', details={'role': 'judge'})
    produced = propose(graph, 'dancer', 'produced', 'track')
    heard = propose(graph, 'track', 'featured_in', 'footage')
    for link in (dancer, judge, produced, heard):
        decide(graph, link)
    assert len(connected_path(path, ids['dancer'], ids['footage'])) == 2
    matching = graph_workspace(path, query='earlier name')['records']
    assert matching[0]['id'] == ids['dancer']
    battle = next(r for r in graph_workspace(path)['records'] if r['id'] == ids['battle'])
    assert 'winner' not in battle['details']
    event = next(r for r in graph_workspace(path)['records'] if r['id'] == ids['event'])
    footage = next(r for r in graph_workspace(path)['records'] if r['id'] == ids['footage'])
    assert event['details']['event_date'] == '2010'
    assert footage['details']['upload_date'] == '2012-03-04'
    assert 'event_date' not in footage['details']


def test_identity_match_is_reversible_and_never_merges_source_rows(graph):
    path, ids, revisions, _ = graph
    link = propose(graph, 'dancer', 'same_identity', 'other')
    decide(graph, link)
    assert connected_path(path, ids['dancer'], ids['other']) is None
    with pytest.raises(ReviewConflict):
        propose_connection(path, ids['other'], 'same_identity', ids['dancer'], revisions['dancer'], 'admin', 'Reverse endpoint duplicate')
    decide(graph, link, 'reverse', 2)
    with sqlite3.connect(path) as db:
        assert db.execute('SELECT count(*) FROM source_crosswalk').fetchone()[0] == 7
        assert db.execute('SELECT count(*) FROM graph_records').fetchone()[0] == 7


@pytest.mark.parametrize('first,relation,second,details', [
    ('footage','member_of','dancer',{}), ('dancer','member_of','dancer',{}),
    ('dancer','same_identity','team',{}), ('dancer','invented','team',{}),
    ('dancer','member_of','team',{'from':'2015','until':'2010'}),
    ('dancer','member_of','team',{'from':'2010-02-30'}),
    ('dancer','member_of','team',{'date_certainty':'guessed'}),
    ('battle','documented_by','footage',{'start_seconds':-1}),
    ('battle','documented_by','footage',{'start_seconds':15,'end_seconds':10}),
    ('dancer','participated_in','event',{'role':'winner'}),
    ('event','contains_battle','battle',{'winner':'made up'}),
])
def test_invalid_connections_cannot_enter_queue(graph, first, relation, second, details):
    with pytest.raises(ValueError):
        propose(graph, first, relation, second, details=details)
    assert graph_workspace(graph[0])['total'] == 0


def test_year_only_membership_end_does_not_create_false_precision(graph):
    link = propose(graph, details={'from':'2010-06', 'until':'2010'})
    decide(graph, link)
    assert graph_workspace(graph[0], 'approved')['total'] == 1


def test_stale_evidence_and_stale_decisions_are_blocked(graph):
    path, ids, _, records = graph
    link = propose(graph)
    records[0]['title'] = 'Changed Source Label'
    stage_snapshot(path, records)
    with pytest.raises(ReviewConflict, match='Evidence changed'):
        decide(graph, link)
    assert graph_workspace(path)['links'][0]['evidence_current'] is False
    decide(graph, link, 'reject')
    with pytest.raises(ReviewConflict):
        decide(graph, link, 'approve', 1)
    assert graph_workspace(path, 'rejected')['links'][0]['version'] == 2
    with sqlite3.connect(path) as db:
        assert db.execute('SELECT label FROM graph_records WHERE id=?', (ids['dancer'],)).fetchone()[0] == 'Test Dancer'
    assert graph_workspace(path, query='Changed Source Label')['records'][0]['id'] == ids['dancer']


def test_approved_history_survives_but_stale_paths_are_excluded(graph):
    path, ids, _, records = graph
    link = propose(graph)
    decide(graph, link)
    assert connected_path(path, ids['dancer'], ids['team'])
    stage_snapshot(path, records[1:])
    assert connected_path(path, ids['dancer'], ids['team']) is None
    assert graph_workspace(path, 'approved')['links'][0]['status'] == 'approved'


def test_missing_audit_reason_rolls_back_decision_and_preserves_backups(graph):
    link = propose(graph)
    with pytest.raises(ValueError):
        decide(graph, link, reason='')
    pending = graph_workspace(graph[0])['links'][0]
    assert pending['version'] == 1 and len(pending['history']) == 1
    assert list(graph[0].parent.glob('*.bak'))


def test_version_one_upgrade_preserves_ids_and_creates_backup(graph):
    path, ids, _, records = graph
    with sqlite3.connect(path) as db:
        for table in ('graph_decisions','graph_links','graph_aliases','graph_records'):
            db.execute('DROP TABLE ' + table)
        db.execute('UPDATE staging_metadata SET version=1')
    result = stage_snapshot(path, records)
    with sqlite3.connect(result['backup']) as db:
        assert db.execute('SELECT version FROM staging_metadata').fetchone()[0] == 1
    with sqlite3.connect(path) as db:
        assert dict(db.execute('SELECT source_key,entity_id FROM source_crosswalk')) == ids
        assert db.execute('SELECT version FROM staging_metadata').fetchone()[0] == 2
        assert db.execute('SELECT count(*) FROM graph_records').fetchone()[0] == 7
        assert db.execute('PRAGMA foreign_key_check').fetchall() == []


def test_bad_import_rolls_back_existing_graph(graph):
    path, _, _, records = graph
    records = copy.deepcopy(records)
    records[0]['payload']['aliases'] = 'badly shaped aliases'
    with pytest.raises(ValueError):
        stage_snapshot(path, records)
    with sqlite3.connect(path) as db:
        assert db.execute('SELECT count(*) FROM source_revisions').fetchone()[0] == 7


def test_admin_auth_opt_in_csrf_review_history_and_public_isolation(website, graph):
    path, ids, revisions, _ = graph
    route = '/admin/archive/connections'
    client = website.test_client()
    assert client.get(route).status_code in (302,303,401,403)
    with client.session_transaction() as state:
        state['ledger_admin_authenticated'] = True
    assert 'No staging snapshot is configured' in client.get(route).get_data(as_text=True)
    assert client.post(route).status_code == 403
    website.config['VAULT_ARCHIVE_STAGING_PATH'] = str(path)
    assert 'read-only' in client.get(route).get_data(as_text=True)
    website.config['VAULT_ARCHIVE_STAGING_REVIEW_ENABLED'] = True
    client.get(route)
    with client.session_transaction() as state:
        token = state['vault_archive_graph_csrf']
    data = dict(action='propose', subject_id=ids['dancer'], relation='member_of',
                object_id=ids['team'], evidence_revision_id=revisions['dancer'], reason='Fixture evidence',
                csrf_token=token, reviewer_id='untrusted posted identity')
    assert client.post(route, data=dict(data, csrf_token='bad')).status_code == 400
    assert client.post(route, data=data).status_code == 303
    pending = graph_workspace(path)['links'][0]
    assert pending['history'][0]['reviewer_id'].startswith('admin-session:')
    assert pending['history'][0]['reviewer_id'] != data['reviewer_id']
    decision = dict(action='approve', link_id=pending['id'], expected_version=1,
                    reason='Reviewed fixture source', csrf_token=token)
    assert client.post(route, data=decision).status_code == 303
    assert client.post(route, data=decision).status_code == 409
    html = client.get(route+'?status=approved').get_data(as_text=True)
    assert 'Decision history' in html and 'Reverse approval' in html
    assert client.post(route, data=dict(decision, action='reverse', expected_version=2)).status_code == 303
    assert 'Test Dancer' not in client.get('/archive/api/records').get_data(as_text=True)
    for query in ('?status=invalid','?page=0','?page=bad'):
        assert client.get(route+query).status_code == 400


def test_admin_get_never_creates_staging_database(website, tmp_path):
    path = tmp_path/'missing.staging.sqlite'
    website.config['VAULT_ARCHIVE_STAGING_PATH'] = str(path)
    client = website.test_client()
    with client.session_transaction() as state:
        state['ledger_admin_authenticated'] = True
    assert client.get('/admin/archive/connections').status_code == 503
    assert not path.exists()


def test_explicit_cli_export_can_stage_typed_sources(graph, tmp_path):
    exported = tmp_path/'export.json'
    exported.write_text(json.dumps(graph[3]), encoding='utf-8')
    destination = tmp_path/'imported.staging.sqlite'
    result = subprocess.run([sys.executable, '-m', 'dca_rebuild.archive_foundation',
                             '--input', str(exported), '--stage', str(destination)],
                            capture_output=True, text=True, check=True)
    assert json.loads(result.stdout)['records'] == 7
    assert {r['kind'] for r in graph_workspace(destination)['records']} == {'person','team','event','battle','footage','track'}


def test_malformed_export_is_rejected_before_staging(tmp_path):
    destination = tmp_path/'invalid.staging.sqlite'
    with pytest.raises(ValueError, match='nonempty strings'):
        stage_snapshot(destination, [dict(system='export',key='',title='Name',kind='person',
                                          visibility='private_review',payload={})])
    assert not destination.exists()


@pytest.mark.skipif(os.getenv('TEST_BROWSER') != '1', reason='Opt-in real Chromium review flow')
@pytest.mark.parametrize('width,height', [(390,844),(1440,1000)])
def test_browser_propose_approve_reverse_on_mobile_and_desktop(website, graph, width, height):
    from threading import Thread
    from werkzeug.serving import make_server
    from playwright.sync_api import sync_playwright
    website.config.update(VAULT_ARCHIVE_STAGING_PATH=str(graph[0]),
                          VAULT_ARCHIVE_STAGING_REVIEW_ENABLED=True)
    client = website.test_client()
    with client.session_transaction() as state:
        state['ledger_admin_authenticated'] = True
    cookie = client.get_cookie('session').value
    server = make_server('127.0.0.1', 0, website, threaded=True)
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(executable_path=os.getenv('CHROMIUM_EXECUTABLE'), args=['--no-sandbox'])
            context = browser.new_context(viewport={'width':width, 'height':height})
            context.add_cookies([dict(name='session', value=cookie, domain='127.0.0.1', path='/')])
            page = context.new_page()
            errors = []
            page.on('pageerror', lambda error: errors.append(str(error)))
            page.goto(f'http://127.0.0.1:{server.server_port}/admin/archive/connections')
            page.select_option('#subject', graph[1]['dancer'])
            page.select_option('#relation', 'member_of')
            page.select_option('#object', graph[1]['team'])
            page.select_option('#evidence', str(graph[2]['dancer']))
            page.fill('#proposal-reason', 'Browser fixture evidence reviewed.')
            page.get_by_role('button', name='Submit for review').click()
            assert page.get_by_role('heading', name='Test Dancer → member_of → Test Team').is_visible()
            page.locator('textarea[id^="reason-"]').fill('Browser fixture approval.')
            page.get_by_role('button', name='Approve connection', exact=True).click()
            page.get_by_role('link', name='Approved', exact=True).click()
            assert page.get_by_role('button', name='Reverse approval').is_visible()
            assert page.evaluate('document.documentElement.scrollWidth <= innerWidth')
            page.screenshot(path=f'/tmp/vault-connected-{width}.png', full_page=True)
            page.locator('textarea[id^="reason-"]').fill('Browser fixture reversal.')
            page.get_by_role('button', name='Reverse approval').click()
            page.get_by_role('link', name='Reversed', exact=True).click()
            assert page.get_by_role('button', name='Reopen for review').is_visible()
            assert not errors
            browser.close()
    finally:
        server.shutdown()
        thread.join(timeout=5)
