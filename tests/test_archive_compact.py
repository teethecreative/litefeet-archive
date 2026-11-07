"""Compact public Archive, protected research notes, and source enhancement checks."""
from dca_rebuild.archive_catalog import all_records, find_record, public_record


def test_compact_archive_rows_and_source_separation(website):
    client = website.test_client()
    page = client.get('/archive')
    assert page.status_code == 200
    html = page.get_data(as_text=True)
    assert 'archive-v2.css' in html
    assert 'lfv-archive-entry-date' in html
    assert 'lfv-archive-entry-meta' not in html
    assert 'View record <span' not in html
    assert 'More than a directory' not in html

    event = find_record('double-impact-2026')
    assert event and len(event['editorial_notes']) >= 1
    assert 'Multiple poster versions' in ' '.join(event['editorial_notes'])
    public = public_record(event)
    assert 'editorial_notes' not in public
    assert 'source_details' not in public
    assert 'research_details' not in public
    details = client.get('/archive/records/double-impact-2026').get_data(as_text=True)
    assert 'Multiple poster versions' not in details
    assert 'Nauli &amp; Lexi' in details
    assert 'Advertised lineup' in details


def test_original_research_sources_attached_without_marking_claim_verified(website):
    record = find_record('research-mr-youtube')
    assert record['research_findings']
    assert record['research_sources']
    assert any('STEEZY' in x['title'] for x in record['research_sources'])
    assert record['editorial_status'] == 'Research under review'
    content = website.test_client().get('/archive/records/research-mr-youtube')
    assert content.status_code == 200
    assert b'Additional sourced findings' in content.data
    assert b'steeezy' not in content.data.lower()
    assert b'steezy.co/instructors/mr-youtube' in content.data
    assert 'editorial_notes' not in content.get_data(as_text=True)


def test_editorial_notes_require_admin_login(website):
    client = website.test_client()
    assert client.get('/admin/archive/research-review').status_code == 302
    with client.session_transaction() as current:
        current['ledger_admin_authenticated'] = True
    page = client.get('/admin/archive/research-review')
    assert page.status_code == 200
    html = page.get_data(as_text=True)
    assert 'RESEARCH &amp; SOURCE REVIEW' in html
    assert 'Multiple poster versions' in html
    assert 'Dancer' in html
    assert 'ORIGINAL RESEARCH FIELDS' in html
    assert 'VIEW PUBLIC RECORD' in html
