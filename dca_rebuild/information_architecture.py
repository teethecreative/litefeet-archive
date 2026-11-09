"""Read-only public section organization. Nomination/admin handlers stay intact."""
from datetime import datetime, timedelta
import hashlib
import secrets
import json
from urllib.parse import urlsplit
from flask import g, request, render_template, redirect, abort, jsonify, session, url_for, flash, current_app
from dca_rebuild.models import LedgerEra, BetaChangelog, VaultArchiveVerification, LockInCardRequest
from dca_rebuild.public_site_updates import PUBLIC_SITE_UPDATES
from dca_rebuild.archive_history_guide import load_history_guide
from dca_rebuild.lock_in import practice_view, published_music_cards
from dca_rebuild.timeline_catalog import timeline_browse, timeline_payload
from dca_rebuild.upcoming_calendar import upcoming_calendar
from dca_rebuild.archive_recovery import recovery_review
from dca_rebuild.archive_catalog import (
    COLLECTIONS, PAGE_SIZE, all_records, browse, find_record,
    listing_payload, public_record, people_crew_cloud,
)

# Stable future catalog; readiness is separate from the intended ordering.
SECTION_CATALOG = (
    ('home', 'Home', '/', True),
    ('archive', 'The Archive', '/archive', True),
    ('people', 'People & Teams', '/archive/people', True),
    ('timeline', 'History & Timeline', '/archive/timeline', True),
    ('calendar', 'Upcoming Calendar', '/calendar', True),
    ('awards', 'Awards & Recognition', '/awards', True),
    ('lock-in', 'Lock In Card Battle Game', '/archive/lock-in', True),
    ('music', 'Music', '/litefeet-music', True),
    ('media', 'Media', '/media', False),
    ('stories', 'Stories & Media', '/stories', False),
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
            'awards': [dict(label="Dancer’s Choice Awards", href='/awards/dancers-choice'),
                       dict(label='LiteFeet Awards', href='/awards/litefeet-awards'),
                       dict(label='HypeItUpTV Awards', href='/awards/hypeitup'),
                       dict(label='DCA 2023 Archive', href='/awards/dancers-choice/2023')],
            'about': [dict(label="Founder's Letter", href='/about/letter'),
                      dict(label='Our Mission', href='/about/mission'),
                      dict(label='About the Archive', href='/about/archive'),
                      dict(label='How It Works', href='/about/how-it-works'),
                      dict(label='Contact', href='/about/contact')],
        }
        path = request.path
        active = 'home' if path == '/' else (
            'people' if path.startswith('/archive/people') else
            'timeline' if path.startswith(('/archive/timeline', '/archive/history', '/archive/records')) else
            'lock-in' if path.startswith('/archive/lock-in') else
            'calendar' if path.startswith(('/calendar', '/events')) else
            'awards' if path.startswith(('/awards', '/dca', '/litefeet-awards', '/hypeitup-awards')) else
            'music' if path.startswith('/litefeet-music') else
            'media' if path.startswith('/media') else
            'archive' if path.startswith(('/archive', '/community', '/submit', '/newsletter')) else
            'about' if path.startswith('/about') else None)
        navigation = [dict(key=k, label=label, href=href, active=k == active,
                           children=children.get(k, [])) for k, label, href, ready in SECTION_CATALOG if ready]
        breadcrumbs = []
        program = []
        if path != '/' and not path.startswith(('/admin', '/beta')):
            breadcrumbs = [dict(label='Home', href='/')]
            section = next((s for s in navigation if s['key'] == active), None)
            labels = {'vault_music_public': 'Release Radar', 'vault_music_release': 'Music Record',
                      'vault_media_public': 'Media', 'vault_archive': 'The Archive', 'vault_timeline': 'Historical Timeline',
                      'vault_history_guide': 'Cultural History', 'vault_lock_in': 'Lock In', 'legacy_calendar': 'Calendar',
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
        if path.startswith('/awards/') and not path.startswith('/awards/litefeet-awards/submit'):
            program = [dict(label='Awards overview', href='/awards'),
                       dict(label="Dancer’s Choice Awards", href='/awards/dancers-choice'),
                       dict(label='LiteFeet Awards', href='/awards/litefeet-awards'),
                       dict(label='HypeItUpTV Awards', href='/awards/hypeitup')]
            if path.startswith('/awards/dancers-choice'):
                program.extend([dict(label='DCA 2026', href='/awards/dancers-choice/2026'),
                                dict(label='DCA 2023 Archive', href='/awards/dancers-choice/2023')])
            elif path.startswith('/awards/litefeet-awards'):
                program.append(dict(label='Contribute historical records',
                                    href='/awards/litefeet-awards#contribute'))
        calendar = upcoming_calendar(session_factory=ns['SessionLocal'])
        page_size = 5
        selected_day = request.args.get('calendar_day', '').strip()
        valid_dates = {day['iso'] for day in calendar['days']}
        if selected_day not in valid_dates:
            selected_day = ''
        shown_events = [event for event in calendar['events']
                        if event['date'] == selected_day] if selected_day else calendar['events']
        count = len(shown_events)
        total_pages = max(1, (count + page_size - 1) // page_size)
        page = max(1, min(request.args.get('calendar_page', 1, type=int) or 1, total_pages))
        calendar_page = dict(
            events=shown_events[(page - 1) * page_size:page * page_size],
            page=page, pages=total_pages, total=count,
            selected_day=selected_day,
            has_previous=page > 1, has_next=page < total_pages,
        )
        return dict(vault_navigation=navigation, vault_breadcrumbs=breadcrumbs,
                    vault_program_navigation=program, vault_emit_chrome=emit_chrome,
                    vault_upcoming_calendar=calendar, vault_calendar_page=calendar_page,
                    vault_site_updates=PUBLIC_SITE_UPDATES,
                    vault_updates=content['updates'], vault_eras=content['eras'], vault_contact=CONTACT)

    def section_page(page, **extra):
        return render_template('vault_section.html', section=page,
                               **public_content(), **extra)

    @app.get('/archive', endpoint='vault_archive')
    def archive():
        """Direct Archive overview; preserve legacy bookmarked filters."""
        if request.args.get('collection') == 'music':
            return redirect(url_for('vault_music_public'), code=302)
        if request.args.get('view') == 'people' or request.args.get('collection') == 'people':
            query = {k: v for k, v in request.args.items() if k not in ('view','collection')}
            return redirect(url_for('vault_archive_people', **query), code=302)
        if request.args.get('collection') or request.args.get('q') or request.args.get('view') == 'timeline':
            query = {k: v for k, v in request.args.items() if k != 'view'}
            return redirect(url_for('vault_timeline', **query), code=302)
        return section_page('overview')

    @app.get('/calendar', endpoint='vault_calendar_public')
    def public_calendar():
        return render_template('calendar_public.html',
                               calendar=upcoming_calendar(session_factory=ns['SessionLocal']))

    @app.get('/archive/people', endpoint='vault_archive_people')
    def archive_people():
        """Separate People & Teams browser, never the deleted Archive landing page."""
        current_page = max(1, request.args.get('page', 1, type=int) or 1)
        query = request.args.get('q', '').strip()
        filtered = browse(query=query, collection='people', page=current_page) if query else {
            'items': [], 'count': 0, 'has_more': False, 'next_page': None,
            'page': current_page, 'collection': 'people'
        }
        return section_page('people', archive_items=filtered['items'],
                            archive_pagination=filtered, people_cloud=people_crew_cloud(),
                            archive_start_page=current_page)

    @app.get('/archive/lock-in', endpoint='vault_lock_in')
    def lock_in():
        if 'lock_card_csrf' not in session:
            session['lock_card_csrf'] = secrets.token_urlsafe(32)
        return section_page('lock-in', lock_card_csrf=session['lock_card_csrf'],
                            **practice_view(request.args, extra_songs=published_music_cards(ns['engine'])))

    @app.post('/archive/lock-in/card-requests', endpoint='vault_lock_in_card_request')
    def lock_in_card_request():
        token = request.form.get('csrf_token', '')
        expected = session.get('lock_card_csrf', '')
        if not expected or not secrets.compare_digest(token, expected):
            return jsonify(error='Please refresh the page and try again.'), 400
        now = datetime.utcnow()
        previous = session.get('lock_card_request_at')
        if previous:
            try:
                if (now - datetime.fromisoformat(previous)).total_seconds() < 30:
                    return jsonify(error='Please wait before submitting another request.'), 429
            except ValueError:
                pass
        kind = request.form.get('card_type', '').strip()
        name = request.form.get('card_name', '').strip()
        email = request.form.get('email', '').strip().lower()
        if kind not in {'Dancer', 'Song', 'Arena', 'Move', 'Trick', 'Upgrade', 'Frib'}:
            return jsonify(error='Select a card type.'), 400
        if not 2 <= len(name) <= 160 or not 3 <= len(email) <= 255 or '@' not in email:
            return jsonify(error='Enter a card name and contact email.'), 400
        fields = ('aliases', 'team_location', 'stats', 'signature', 'permission',
                  'producer', 'release_year', 'era_level', 'arena_location',
                  'arena_type', 'arena_history', 'move_style', 'move_connection',
                  'trick_style', 'trick_connection', 'gameplay')
        limits = {'aliases':240,'team_location':240,'stats':500,'signature':500,
                  'permission':30,'producer':160,'release_year':4,'era_level':160,
                  'arena_location':200,'arena_type':120,'arena_history':700,
                  'move_style':160,'move_connection':280,'trick_style':160,
                  'trick_connection':280,'gameplay':1000}
        payload = {key: request.form.get(key, '').strip() for key in fields}
        if any(len(value) > limits[key] for key, value in payload.items()):
            return jsonify(error='A response is too long.'), 400
        if kind == 'Dancer' and payload['permission'] not in ('yes','request-first','not-confirmed'):
            return jsonify(error='Select a permission option.'), 400
        if kind == 'Song' and not payload['producer']:
            return jsonify(error='Who produced this song?'), 400
        if kind == 'Arena' and not payload['arena_history']:
            return jsonify(error='Tell us why this space matters to LiteFeet.'), 400
        source = request.form.get('source', '').strip()
        if len(source) > 800 or (source and urlsplit(source).scheme not in ('http','https')):
            return jsonify(error='Use a valid source link.'), 400
        with ns['SessionLocal'].begin() as db:
            db.add(LockInCardRequest(card_type=kind, card_name=name, contact_email=email,
                                     details_json=json.dumps(payload), source_url=source or None,
                                     status='pending'))
        session['lock_card_request_at'] = now.isoformat()
        return jsonify(ok=True, message='Card request received for review.'), 201

    @app.get('/archive/timeline', endpoint='vault_timeline')
    def timeline():
        if request.args.get('collection') == 'music':
            return redirect(url_for('vault_music_public'), code=302)
        current_page = max(1, request.args.get('page', 1, type=int) or 1)
        search = dict(query=request.args.get('q', ''),
                      collection=request.args.get('collection', 'all'), page=current_page)
        filtered = timeline_browse(**search, eras=public_content()['eras'])
        return section_page('timeline', archive_items=filtered['items'],
                            archive_pagination=filtered, archive_collections=COLLECTIONS,
                            archive_start_page=current_page)

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
                               review_records=review,
                               recovery_profiles=recovery_review(all_records()))

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
