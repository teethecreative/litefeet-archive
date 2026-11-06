"""Archive research migration is inert until explicitly applied."""
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from dca_rebuild.models import VaultArchiveRecord, VaultArchiveAssertion, VaultArchiveResponse
from dca_rebuild.stage_archive_research import staged_rows, apply_private_import, main


def test_source_rows_remain_private_and_distinct():
    rows = staged_rows()
    assert len(rows) == 18
    assert len({r["source_key"] for r in rows}) == len(rows)
    assert len({r["slug"] for r in rows}) == len(rows)
    assert all(r["visibility"] == "private" for r in rows)
    assert all(r["editorial_status"] == "under_review" for r in rows)
    assert all(r["summary"] for r in rows)
    assert any("Harlem Shake" in r["title"] for r in rows)
    assert any("Kid The Wiz" in r["title"] for r in rows)


def test_default_cli_dry_run_does_not_write(capsys):
    assert main([]) == 0
    output = capsys.readouterr().out
    assert "Dry-run only" in output
    assert "18 historical research seed entries" in output


def test_staging_is_idempotent_and_private(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path}/archive_tests.db")
    factory = sessionmaker(bind=engine)
    try:
        first = apply_private_import(factory, engine)
        count_claims = sum(bool(r["assertion"]) for r in staged_rows())
        assert first == (18, 0, count_claims)
        assert apply_private_import(factory, engine) == (0, 18, 0)
        with factory() as db:
            records = db.query(VaultArchiveRecord).all()
            assertions = db.query(VaultArchiveAssertion).all()
            assert len(records) == 18
            assert len(assertions) == count_claims
            assert all(r.visibility == "private" and r.editorial_status == "under_review" for r in records)
            assert all(a.visibility == "private" for a in assertions)
            assert db.query(VaultArchiveResponse).count() == 0
    finally:
        engine.dispose()
