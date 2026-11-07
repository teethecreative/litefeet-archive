"""Read-only public section organization. Nomination/admin handlers stay intact."""
from datetime import datetime, timedelta
import hashlib
import secrets
from flask import g, request, render_template, redirect, abort, jsonify, session, url_for, flash, current_app
from dca_rebuild.models import LedgerEra, BetaChangelog, VaultArchiveVerification
from dca_rebuild.public_site_updates import PUBLIC_SITE_UPDATES
from dca_rebuild.archive_history_guide import load_history_guide
from dca_rebuild.lock_in import practice_view
from dca_rebuild.timeline_catalog import timeline_browse, timeline_payload
from dca_rebuild.upcoming_calendar import upcoming_calendar
from dca_rebuild.archive_catalog import (
    COLLECTIONS, PAGE_SIZE, all_records, browse, find_record,
    listing_payload, public_record, people_crew_cloud,
)

# Stable future catalog; readiness is separate from the intended ordering.
SECTION_CATALOG = (
    ('home', 'Home', '/', True),
    ('archive', 'The Archive', '/archive', True),
    ('people', 'People', '/people', False),
    ('stories', 'Stories & Media', '/stories', False),
    ('awards', 'Awards', '/awards', True),
    ('community', 'Community', '/community', False),
    ('about', 'About', '/about', True),
)
CONTACT = 'mailto:teethecreative@gmail.com?subject=LiteFeet%20Vault%20Enquiry'


def install_information_architecture(app, ns):
    def public_content():
        if not hasattr(g, 'vault_public_content'):
            with ns['SessionLocal']() as db:
                eras = db.query(LedgerEra).filter_by(status='published').order_by(
                    LedgerEra.sort_order, LedgerEra.start_year, LedgerEra.id).all()
                updates = db.query(BetaChangelog).filter_by(is_published=True, visibility='public').order_by(
                    BetaChangelog.created_at.desc(), BetaChangelog.id.desc()).limit(10).all()
                g.vault_public_content = dict(
                    eras=[dict(name=e.name, description=e.description, start_year=e.start_year,
                               end_year=e.end_year) for e in eras],
                    updates=[dict(title=u.title, details=u.details, created_at=u.created_at) for u in updates])
        return g.vault_public_content

    def emit_chrome():
        if getattr(g, 'vault_chrome_emitted', False):
            return False
        g.vault_chrome_emitted = True
        return True

    @app.context_processor
    def vault_site_context():
        content = public_content()
        children = {
            'archive': [dict(label='Browse collections', href='/archive#collections'),
                        dict(label='History & Timeline', href='/archive/timeline'),
                        dict(label='Lock In · Card Battle Game', href='/archive/lock-in'),
                        dict(label='Submit', href='/submit')],
            'awards': [dict(label="Dancer’s Choice Awards", href='/awards/dancers-choice'),
                       dict(label='LiteFeet Awards', href='/awards/litefeet-awards'),
                       dict(label='Historical Results', href='/awards/dancers-choice/2023')],
            'about': [dict(label="Founder's Letter", href='/about/letter'),
                      dict(label='Our Mission', href='/about/mission'),
                      dict(label='About the Archive', href='/about/archive'),
                      dict(label='How It Works', href='/about/how-it-works'),
                      dict(label='Contact', href='/about/contact')],
        }
        path = request.path
        active = 'home' if path == '/' else (
            'awards' if path.startswith(('/awards', '/dca', '/litefeet-awards', '/hypeitup-awards')) else
            'archive' if path.startswith(('/archive', '/community', '/submit', '/newsletter')) else
            'about' if path.startswith('/about') else None)
        navigation = [dict(key=k, label=label, href=href, active=k == active,
                           children=children.get(k, [])) for k, label, href, ready in SECTION_CATALOG if ready]
        breadcrumbs = []
        program = []
        if path != '/' and not path.startswith(('/admin', '/beta')):
            breadcrumbs = [dict(label='Home', href='/')]
            section = next((s for s in navigation if s['key'] == active), None)
            labels = {'vault_archive': 'The Archive', 'vault_timeline': 'Historical Timeline',
                      'vault_history_guide': 'Cultural History', 'vault_lock_in': 'Lock In',
                      'vault_community': 'Contribute & Correct', 'legacy_about': 'About', 'awards_home': 'Awards',
                      'vault_dca_program': 'Dancer’s Choice Awards', 'dca_2026_home': '2026',
                      'dca_2023_home': '2023 archive', 'round1': 'Category survey', 'round2': 'Category results',
                      'lfa_year': 'LiteFeet Awards ' + str((request.view_args or {}).get('year', '')),
                      'dca_nominations_closed': 'Nominee standings' if request.args.get('view') == 'results' else 'Nominations',
                      'lfa_home': 'LiteFeet Awards', 'hypeitup_awards': 'HypeItUpTV Awards'}
            if section and path != section['href']:
                breadcrumbs.append(dict(label=section['label'], href=section['href']))
            if path.startswith('/awards/dancers-choice') and path != '/awards/dancers-choice':
                breadcrumbs.append(dict(label='Dancer’s Choice Awards', href='/awards/dancers-choice'))
            if request.endpoint == 'vault_archive_record':
                archived = find_record((request.view_args or {}).get('slug', ''))
                labels['vault_archive_record'] = archived['title'] if archived else 'Archive entry'
            current = labels.get(request.endpoint)
            if current:
                breadcrumbs.append(dict(label=current, href=None))
            elif section:
                breadcrumbs.append(dict(label=section['label'] if path == section['href'] else 'Current page', href=None))
            else:
                breadcrumbs = []
        if path.startswith('/awards/dancers-choice'):
            program = [dict(label='2026', href='/awards/dancers-choice/2026'),
                       dict(label='2023', href='/awards/dancers-choice/2023')]
        elif path.startswith('/awards/litefeet-awards'):
            program = [dict(label='LiteFeet Awards', href='/awards/litefeet-awards'),
                       dict(label='Contribute historical records', href='/awards/litefeet-awards#contribute')]
        return dict(vault_navigation=navigation, vault_breadcrumbs=breadcrumbs,
                    vault_program_navigation=program, vault_emit_chrome=emit_chrome,
                    vault_upcoming_calendar=upcoming_calendar(session_factory=ns['SessionLocal']),
                    vault_site_updates=PUBLIC_SITE_UPDATES,
                    vault_updates=content['updates'], vault_eras=content['eras'], vault_contact=CONTACT)

    def section_page(page, **extra):
        return render_template('vault_section.html', section=page,
                               **public_content(), **extra)

    def archive_page(section):
        timeline = section == 'timeline'
        current_page = max(1, request.args.get('page', 1, type=int) or 1)
        search = dict(query=request.args.get('q', ''),
                      collection=request.args.get('collection', 'all'),
                      page=current_page)
        filtered = timeline_browse(**search, eras=public_content()['eras']) if timeline else browse(**search)
        return section_page(section, archive_items=filtered['items'],
                            archive_pagination=filtered, archive_collections=COLLECTIONS,
                            archive_timeline=timeline,
                            people_cloud=(people_crew_cloud() if not timeline and search['collection'] == 'people'
                                          else []),
                            archive_start_page=current_page)

    @app.get('/archive', endpoint='vault_archive')
    def archive():
        return archive_page('archive')

    @app.get('/archive/lock-in', endpoint='vault_lock_in')
    def lock_in():
        return section_page('lock-in', **practice_view(request.args))

    @app.get('/archive/timeline', endpoint='vault_timeline')
    def timeline():
        return archive_page('timeline')

    @app.get('/archive/history', endpoint='vault_history_guide')
    def history_guide():
        # Preserve bookmarks: source-linked research now lives in the unified timeline.
        return redirect(url_for('vault_timeline'), code=302)

    @app.get('/archive/api/records', endpoint='vault_archive_api')
    def archive_api():
        page = max(1, request.args.get('page', 1, type=int) or 1)
        timeline_only = request.args.get('timeline') == '1'
        search = dict(query=request.args.get('q', ''),
                      collection=request.args.get('collection', 'all'), page=page)
        result = timeline_browse(**search, eras=public_content()['eras']) if timeline_only else browse(**search)
        response = jsonify({
            'records': [(timeline_payload(x) if timeline_only else listing_payload(x))
                        for x in result['items']],
            'page': result['page'], 'next_page': result['next_page'],
            'has_more': result['has_more'], 'total': result['count'],
        })
        response.headers['Cache-Control'] = 'public, max-age=120'
        return response

    @app.get('/archive/records/<slug>', endpoint='vault_archive_record')
    def archive_record(slug):
        record = find_record(slug)
        if record is None:
            abort(404)
        if 'vault_archive_csrf' not in session:
            session['vault_archive_csrf'] = secrets.token_urlsafe(32)
        related_records = [
            item for item in all_records()
            if item['slug'] != slug and record.get('series')
            and item.get('series') == record['series']
        ][:8]
        return render_template('archive_record.html', record=public_record(record),
                               related_records=[public_record(item) for item in related_records],
                               archive_csrf=session['vault_archive_csrf'],
                               **public_content())

    @app.post('/archive/records/<slug>/verify', endpoint='vault_archive_verify')
    def archive_verify(slug):
        record = find_record(slug)
        if not record or not record['can_verify']:
            abort(404)
        token = request.form.get('csrf_token') or ''
        expected = session.get('vault_archive_csrf') or ''
        if not expected or not secrets.compare_digest(token, expected):
            abort(400)
        choice = (request.form.get('choice') or '').strip().lower()
        if choice not in ('true', 'false', 'debatable'):
            abort(400)
        explanation = (request.form.get('explanation') or '').strip()
        if len(explanation) > 1000:
            abort(400)
        if choice != 'debatable':
            explanation = ''
        # Opaque signed-cookie pseudonym; no raw IP, email or profile name stored.
        if 'vault_archive_voter' not in session:
            session['vault_archive_voter'] = secrets.token_hex(24)
        seed = str(current_app.secret_key) + ':' + session['vault_archive_voter']
        visitor_hash = hashlib.sha256(seed.encode('utf-8')).hexdigest()
        now = datetime.utcnow()
        with ns['SessionLocal'].begin() as db:
            existing = db.query(VaultArchiveVerification).filter_by(
                record_slug=slug, visitor_hash=visitor_hash).first()
            if existing:
                # Prevent rapid repeat submissions and vote flooding.
                if existing.updated_at and now - existing.updated_at < timedelta(seconds=30):
                    abort(429)
                existing.vote = choice
                existing.explanation = explanation or None
                existing.moderation_status = 'pending'
                existing.updated_at = now
            else:
                db.add(VaultArchiveVerification(
                    record_slug=slug, visitor_hash=visitor_hash, vote=choice,
                    explanation=explanation or None, moderation_status='pending',
                    created_at=now, updated_at=now))
        flash('Response received for editorial review.', 'archive')
        return redirect(url_for('vault_archive_record', slug=slug) + '#verification', code=303)

    @app.get('/admin/archive/research-review', endpoint='vault_archive_admin_review')
    @ns['admin_login_required']
    def archive_admin_review():
        """Private editorial notes and source conflicts, never a public endpoint."""
        review = [
            {
                'slug': item['slug'],
                'title': item['title'],
                'source_kind': item['source_kind'],
                'editorial_status': item['editorial_status'],
                'date_label': item.get('date_label', ''),
                'editorial_notes': item.get('editorial_notes') or [],
                'original_research': item.get('research_details') or [],
                'source_details': item.get('source_details') or {},
                'source_links': item.get('research_sources') or [],
            }
            for item in all_records()
        ]
        return render_template('admin_archive_research_review.html',
                               review_records=review)

    @app.get('/community', endpoint='vault_community')
    def community():
        return section_page('community')

    @app.get('/awards/dancers-choice', endpoint='vault_dca_program')
    def dca_program():
        return section_page('dca')

    app.view_functions['awards_home'] = lambda: section_page('awards')
    app.view_functions['legacy_about'] = lambda: section_page('about')
    for about_path, page, label in (
        ('letter', 'letter', "FOUNDER'S LETTER"),
        ('mission', 'mission', 'OUR MISSION'),
        ('archive', 'archive', 'ABOUT THE ARCHIVE'),
        ('how-it-works', 'how_it_works', 'HOW IT WORKS'),
        ('contact', 'contact', 'CONTACT'),
    ):
        def about_view(page=page, label=label):
            return render_template('about_' + page.replace('_', '-') + '.html',
                                   page_title=label, **public_content())
        app.add_url_rule('/about/' + about_path, endpoint='vault_about_' + page,
                         view_func=about_view, methods=['GET'])

    # Previously homepage loops; retain paths and route names, use a real hub.
    for endpoint in ('legacy_submit', 'legacy_submit_start', 'legacy_contributor'):
        if endpoint in app.view_functions:
            app.view_functions[endpoint] = lambda: redirect('/community#contribute', code=302)
