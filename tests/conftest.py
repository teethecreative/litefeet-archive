import importlib
import os
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from dca_rebuild.models import Base, DCAEdition, DCACategory
from dca_rebuild.phase9e import CategoryStage9E


@pytest.fixture
def database(tmp_path):
    url = os.environ.get('TEST_DATABASE_URL') or f'sqlite:///{tmp_path}/test.db'
    if os.environ.get('TEST_DATABASE_URL'):
        from sqlalchemy.engine import make_url
        if not (make_url(url).database or '').endswith('_tests'):
            raise RuntimeError('TEST_DATABASE_URL must name a disposable database ending in _tests')
    engine = create_engine(url, connect_args={'timeout': 20} if url.startswith('sqlite:') else {})
    Base.metadata.create_all(engine)
    factory = sessionmaker(engine)
    with factory.begin() as db:
        edition = DCAEdition(year=2026, title='Awards', phase='nominations', is_public=True)
        db.add(edition); db.flush()
        for index in range(27):
            category = DCACategory(edition_id=edition.id, name=f'Category {index+1}',
                                  normalized_name=f'category {index+1}', source_type='new', status='official' if index < 25 else 'write_in_eligible')
            db.add(category); db.flush()
            db.add(CategoryStage9E(edition_id=edition.id, category_id=category.id,
                                  position=index+1, stage='top25' if index < 25 else 'write_in'))
        edition_id = edition.id
    yield engine, factory, edition_id
    # PostgreSQL tests must use a disposable database; no production data.
    if os.environ.get('TEST_DATABASE_URL'):
        Base.metadata.drop_all(engine)
    engine.dispose()


@pytest.fixture
def website(database, monkeypatch, tmp_path):
    monkeypatch.setenv('DATABASE_URL', f'sqlite:///{tmp_path}/bootstrap.db')
    monkeypatch.setenv('DCA_2026_NOMINATIONS_ENABLED', 'true')
    module = importlib.import_module('dca_rebuild.app')
    monkeypatch.setattr(module, 'SessionLocal', database[1])
    # install_phase9e captures its session factory when registering routes.
    monkeypatch.setattr(module, 'engine', database[0])
    from flask import Flask
    from pathlib import Path
    from dca_rebuild.phase9e import install_phase9e
    rebuild = Path(module.__file__).parent
    app = Flask('vault-tests', template_folder=str(rebuild / 'templates'), static_folder=str(rebuild / 'static'))
    app.secret_key = 'test-only-secret'
    app.testing = True
    # Reuse real routing, context processors and admin workflows without module
    # globals leaking database state between tests.
    for rule in module.app.url_map.iter_rules():
        if rule.endpoint == 'static' or rule.endpoint.startswith('phase9e_'):
            continue
        app.add_url_rule(rule.rule, rule.endpoint, module.app.view_functions[rule.endpoint], methods=list(rule.methods))
    for processor in module.app.template_context_processors[None]:
        if processor.__name__ != 'phase9e_admin_template_context':
            app.context_processor(processor)
    ns = dict(module.__dict__, engine=database[0], SessionLocal=database[1])
    install_phase9e(app, ns)
    # Preserve SEO noindex response headers in the isolated website fixture.
    for callback in module.app.after_request_funcs.get(None, []):
        if callback.__name__ == "litefeet_noindex_private_pages":
            app.after_request(callback)
    return app


def identify(client, email='person@example.com'):
    client.get('/awards/dancers-choice/nominations')
    with client.session_transaction() as sess:
        token = sess['lf9e_nomination_csrf']
    response = client.post('/awards/dancers-choice/nominations', data=dict(action='identify', email=email, csrf_token=token))
    assert response.status_code == 302
    return token
