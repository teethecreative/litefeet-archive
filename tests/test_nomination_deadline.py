from datetime import datetime, timezone

import pytest

from conftest import identify
from dca_rebuild import phase9e
from dca_rebuild.models import DCANominationSubmission

PATH = '/awards/dancers-choice/nominations'


def freeze(monkeypatch, instant):
    class Clock(datetime):
        @classmethod
        def now(cls, tz=None):
            return instant.astimezone(tz) if tz else instant.replace(tzinfo=None)
    monkeypatch.setattr(phase9e, 'datetime', Clock)


@pytest.mark.parametrize('instant,closed', [
    ('2026-12-01T04:59:59.999999+00:00', False),
    ('2026-12-01T05:00:00+00:00', True),
    ('2026-12-01T05:00:01+00:00', True),
])
def test_default_cutoff_new_york(monkeypatch, instant, closed):
    monkeypatch.delenv('DCA_2026_NOMINATIONS_CLOSE_AT', raising=False)
    freeze(monkeypatch, datetime.fromisoformat(instant))
    assert phase9e.is_closed() is closed


def test_close_blocks_new_support_preserves_provisional_standings(website, database, monkeypatch):
    monkeypatch.delenv('DCA_2026_NOMINATIONS_CLOSE_AT', raising=False)
    freeze(monkeypatch, datetime(2026, 12, 1, 4, 59, 59, tzinfo=timezone.utc))
    client = website.test_client()
    token = identify(client)
    response = client.post(PATH, data=dict(action='nominate', csrf_token=token,
        category_id=1, name='Provisional Dancer', reason='Active in LiteFeet this season.'))
    assert response.status_code == 302
    freeze(monkeypatch, datetime(2026, 12, 1, 5, tzinfo=timezone.utc))
    response = client.post(PATH, data=dict(action='nominate', csrf_token=token,
        category_id=2, name='Late Dancer', reason='Active in LiteFeet this season.'))
    assert response.status_code == 403
    with database[1]() as db:
        assert db.query(DCANominationSubmission).count() == 1
    page = website.test_client().get(PATH + '?view=results').get_data(as_text=True)
    assert 'Provisional Dancer' in page
    assert 'Nominations are closed' in page
    assert 'November 30, 2026 at 11:59 PM' in page
    assert 'Review begins December 1, 2026' in page


def test_schedule_and_reason_copy(website, monkeypatch):
    monkeypatch.delenv('DCA_2026_NOMINATIONS_CLOSE_AT', raising=False)
    client = website.test_client()
    for path in (PATH, '/awards/dancers-choice', '/awards/dancers-choice/2026'):
        response = client.get(path)
        assert response.status_code == 200
        page = response.get_data(as_text=True)
        assert 'November 30, 2026 at 11:59 PM' in page
        assert 'announced separately' not in page
    page = client.get(PATH).get_data(as_text=True)
    assert 'without repeating it' in page
    assert 'every new nomination must include a reason' not in page
