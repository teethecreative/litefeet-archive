"""Read-only public section organization. Nomination/admin handlers stay intact."""
from flask import g, request, render_template, redirect
from dca_rebuild.models import LedgerEra, BetaChangelog

# Stable future catalog; readiness is separate from the intended ordering.
SECTION_CATALOG = (
    ('home', 'Home', '/', True),
    ('archive', 'The Archive', '/archive', True),
    ('people', 'People', '/people', False),
    ('stories', 'Stories & Media', '/stories', False),
    ('awards', 'Awards', '/awards', True),
    ('community', 'Community', '/community', True),
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
            'archive': [dict(label='Historical collections', href='/archive#collections')] +
                       ([dict(label='Historical Timeline', href='/archive/timeline')] if content['eras'] else []),
            'awards': [dict(label="Dancer’s Choice Awards", href='/awards/dancers-choice'),
                       dict(label='LiteFeet Awards', href='/awards/litefeet-awards'),
                       dict(label='Historical Results', href='/awards/dancers-choice/2023')],
            'community': [dict(label='Contribute to the Archive', href='/community#contribute'),
                          dict(label='Suggest Corrections', href='/awards/litefeet-awards#contribute')] +
                         ([dict(label='Community Updates', href='/community#updates')] if content['updates'] else []),
            'about': [dict(label='Our Mission', href='/about#mission'),
                      dict(label='About the Archive', href='/about#archive'),
                      dict(label='How It Works', href='/about#how-it-works'),
                      dict(label='Contact', href='/about#contact')],
        }
        path = request.path
        active = 'home' if path == '/' else (
            'awards' if path.startswith(('/awards', '/dca', '/litefeet-awards', '/hypeitup-awards')) else
            'archive' if path.startswith('/archive') else
            'community' if path.startswith(('/community', '/submit', '/newsletter')) else
            'about' if path == '/about' else None)
        navigation = [dict(key=k, label=label, href=href, active=k == active,
                           children=children.get(k, [])) for k, label, href, ready in SECTION_CATALOG if ready]
        breadcrumbs = []
        program = []
        if path != '/' and not path.startswith(('/admin', '/beta')):
            breadcrumbs = [dict(label='Home', href='/')]
            section = next((s for s in navigation if s['key'] == active), None)
            labels = {'vault_archive': 'The Archive', 'vault_timeline': 'Historical Timeline',
                      'vault_community': 'Community', 'legacy_about': 'About', 'awards_home': 'Awards',
                      'vault_dca_program': 'Dancer’s Choice Awards', 'dca_2026_home': '2026',
                      'dca_2023_home': '2023 archive', 'round1': 'Category survey', 'round2': 'Category results',
                      'lfa_year': 'LiteFeet Awards ' + str((request.view_args or {}).get('year', '')),
                      'dca_nominations_closed': 'Nominee standings' if request.args.get('view') == 'results' else 'Nominations',
                      'lfa_home': 'LiteFeet Awards', 'hypeitup_awards': 'HypeItUpTV Awards'}
            if section and path != section['href']:
                breadcrumbs.append(dict(label=section['label'], href=section['href']))
            if path.startswith('/awards/dancers-choice') and path != '/awards/dancers-choice':
                breadcrumbs.append(dict(label='Dancer’s Choice Awards', href='/awards/dancers-choice'))
            current = labels.get(request.endpoint)
            if current:
                breadcrumbs.append(dict(label=current, href=None))
            elif section:
                breadcrumbs.append(dict(label=section['label'] if path == section['href'] else 'Current page', href=None))
            else:
                breadcrumbs = []
        if path.startswith('/awards/dancers-choice'):
            program = [dict(label='2026', href='/awards/dancers-choice/2026'),
                       dict(label='2023 archive', href='/awards/dancers-choice/2023'),
                       dict(label='Category results', href='/awards/dancers-choice/category-voting')]
        elif path.startswith('/awards/litefeet-awards'):
            program = [dict(label='LiteFeet Awards', href='/awards/litefeet-awards'),
                       dict(label='Contribute historical records', href='/awards/litefeet-awards#contribute')]
        return dict(vault_navigation=navigation, vault_breadcrumbs=breadcrumbs,
                    vault_program_navigation=program, vault_emit_chrome=emit_chrome,
                    vault_updates=content['updates'], vault_eras=content['eras'], vault_contact=CONTACT)

    def section_page(page):
        return render_template('vault_section.html', section=page, **public_content())

    @app.get('/archive', endpoint='vault_archive')
    def archive():
        return section_page('archive')

    @app.get('/archive/timeline', endpoint='vault_timeline')
    def timeline():
        if not public_content()['eras']:
            from flask import abort
            abort(404)
        return section_page('timeline')

    @app.get('/community', endpoint='vault_community')
    def community():
        return section_page('community')

    @app.get('/awards/dancers-choice', endpoint='vault_dca_program')
    def dca_program():
        return section_page('dca')

    app.view_functions['awards_home'] = lambda: section_page('awards')
    app.view_functions['legacy_about'] = lambda: section_page('about')
    # Previously homepage loops; retain paths and route names, use a real hub.
    for endpoint in ('legacy_submit', 'legacy_submit_start', 'legacy_contributor'):
        if endpoint in app.view_functions:
            app.view_functions[endpoint] = lambda: redirect('/community#contribute', code=302)
