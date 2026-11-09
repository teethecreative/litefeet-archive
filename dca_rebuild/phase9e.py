"""LiteFeet DCA 2026 Phase 9E — install Flask hooks onto the existing site.

Existing public routes, historical votes, and visual system are preserved.
New tables are additive and created on startup; this module never drops data.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo
import os
import re
import secrets
from collections import defaultdict
from fractions import Fraction

from flask import abort, flash, jsonify, redirect, render_template, request, session, url_for
from sqlalchemy import Column, Date, DateTime, ForeignKey, Integer, String, Text, UniqueConstraint, func
from sqlalchemy.exc import IntegrityError

from dca_rebuild.models import (
    Base, DCACategory, DCACategorySuggestionSubmission, DCAReturnCategoryVote,
    DCAEdition, DCANominee, DCANominationSubmission, DCANominationContact,
)
from dca_rebuild.nomination_service import (
    add_nomination, canonical_nominee_name, canonical_nominee_key, candidate_matches, insert_for,
)

NY = ZoneInfo('America/New_York')


class DailyNominationClaim9E(Base):
    __tablename__ = 'ledger_dca9e_daily_claims'
    id = Column(Integer, primary_key=True)
    edition_id = Column(Integer, nullable=False)
    submitter_hash = Column(String(128), nullable=False)
    local_day = Column(Date, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    __table_args__ = (UniqueConstraint('edition_id', 'submitter_hash', 'local_day', name='uq_dca9e_daily'),)


class LegacyNominationDetail9E(Base):
    __tablename__ = 'ledger_dca9e_nomination_details'
    id = Column(Integer, primary_key=True)
    submission_id = Column(Integer, ForeignKey('ledger_dca_nomination_submissions.id'), unique=True, nullable=False)
    team = Column(String(250))
    location = Column(String(250))
    instagram = Column(String(100))
    justification = Column(Text)


class NominationDetail9E(Base):
    __tablename__ = 'ledger_dca_nomination_entry_details'
    id = Column(Integer, primary_key=True)
    submission_id = Column(Integer, ForeignKey('ledger_dca_nomination_entries.id'), unique=True, nullable=False)
    team = Column(String(250))
    location = Column(String(250))
    instagram = Column(String(100))
    justification = Column(Text)


class CategoryStage9E(Base):
    __tablename__ = 'ledger_dca9e_category_stages'
    id = Column(Integer, primary_key=True)
    edition_id = Column(Integer, nullable=False)
    category_id = Column(Integer, ForeignKey('ledger_dca_categories.id'), nullable=False)
    stage = Column(String(24), nullable=False)  # top25, write_in, qualified
    position = Column(Integer, nullable=False)
    __table_args__ = (UniqueConstraint('edition_id', 'category_id', name='uq_dca9e_category_stage'),)


class DraftCategoryDescription9E(Base):
    __tablename__ = 'ledger_dca9e_draft_descriptions'
    id = Column(Integer, primary_key=True)
    edition_id = Column(Integer, nullable=False)
    category_key = Column(String(100), nullable=False)
    description = Column(String(500), nullable=False)
    __table_args__ = (UniqueConstraint('edition_id', 'category_key', name='uq_dca9e_draft_desc'),)


class NomineeQualificationReason9E(Base):
    """Additional community evidence: does not count as a nomination."""
    __tablename__ = 'ledger_dca_nominee_qualification_reasons'
    id = Column(Integer, primary_key=True)
    edition_id = Column(Integer, nullable=False, index=True)
    nominee_id = Column(Integer, ForeignKey('ledger_dca_nominees.id'), nullable=False, index=True)
    submitter_hash = Column(String(128), nullable=False)
    reason = Column(Text, nullable=False)
    evidence_url = Column(String(500))
    moderation_status = Column(String(24), nullable=False, default='pending')
    submitted_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    reviewed_at = Column(DateTime)
    __table_args__ = (UniqueConstraint('edition_id', 'nominee_id', 'submitter_hash',
                                       name='uq_dca_qualification_one_per_supporter'),)


TABLES = [DailyNominationClaim9E.__table__, LegacyNominationDetail9E.__table__, NominationDetail9E.__table__,
          CategoryStage9E.__table__, DraftCategoryDescription9E.__table__,
          NomineeQualificationReason9E.__table__]


def nominees_missing_reasons(db, edition):
    """Public-facing unique nominee/category pairs needing an explanation.

    Historical nomination entries and nominee descriptions are retained.
    Unverified new explanations remain pending and don't establish eligibility.
    """
    nominations, _ = get_counts(db, edition, include_pending=True)
    original = (db.query(DCANominationSubmission.nominee_id, NominationDetail9E.justification)
                .outerjoin(NominationDetail9E,
                           NominationDetail9E.submission_id == DCANominationSubmission.id)
                .filter(DCANominationSubmission.edition_id == edition.id).all())
    justified = {nid for nid, explanation in original if explanation and explanation.strip()}
    justified.update(n.id for n in db.query(DCANominee).filter(
        DCANominee.edition_id == edition.id).all()
        if n.description and n.description.strip())
    reviewed = (db.query(NomineeQualificationReason9E.nominee_id)
                .filter_by(edition_id=edition.id, moderation_status='verified').all())
    justified.update(nid for nid, in reviewed)
    results = []
    for cid, nominees in nominations.items():
        cat = db.get(DCACategory, cid)
        if not cat:
            continue
        for item in nominees:
            if not any(nid in justified for nid in item['ids']):
                results.append(dict(category_id=cid, category=cat.name,
                                    nominee_id=item['id'], name=item['name'],
                                    count=item['count']))
    return sorted(results, key=lambda item: (item['category'].casefold(), item['name'].casefold()))



def today_ny():
    return datetime.now(NY).date()


def day_bounds_utc(day):
    start = datetime.combine(day, datetime.min.time(), tzinfo=NY).astimezone(timezone.utc)
    end = (datetime.combine(day + timedelta(days=1), datetime.min.time(), tzinfo=NY)
           .astimezone(timezone.utc))
    return start.replace(tzinfo=None), end.replace(tzinfo=None)


def nomination_deadline():
    """Optional explicit cutoff, e.g. 2026-12-31T23:59:00-05:00. No implicit closing date."""
    value = os.getenv('DCA_2026_NOMINATIONS_CLOSE_AT', '').strip()
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(value)
        if parsed.tzinfo is None:
            return parsed.replace(tzinfo=NY)
        return parsed
    except ValueError:
        raise RuntimeError('Invalid DCA_2026_NOMINATIONS_CLOSE_AT (must be ISO date/time)')


def is_closed():
    end = nomination_deadline()
    return bool(end and datetime.now(NY) >= end)


def csrf_ok():
    token = request.form.get('csrf_token', '')
    expected = session.get('dca_moderation_csrf', '')
    return bool(token and expected and secrets.compare_digest(token, expected))


def normalized(value):
    return ' '.join(value.casefold().split())


# Owner-confirmed: these write-in labels represent the same category.
PRODUCER_YEAR_NAMES = frozenset((
    'producer of the year',
    'producer of the year award',
    'producer of the year awards',
))
PRODUCER_YEAR_DISPLAY = 'Producer of The Year'


def writein_category_key(name):
    key = normalized(name)
    return 'producer of the year' if key in PRODUCER_YEAR_NAMES else key


def writein_category_label(name):
    return PRODUCER_YEAR_DISPLAY if normalized(name) in PRODUCER_YEAR_NAMES else name


def producer_writein_alias_map(db, edition, *, rows=None):
    """Resolve duplicate producer write-ins without moving or deleting records.

    Official Top 25 categories are never collapsed into the write-in.
    Historical nominee IDs, entries and cooldowns retain their original links.
    """
    if edition is None or edition.year != 2026:
        return {}
    if rows is None:
        rows = (db.query(CategoryStage9E, DCACategory)
                .join(DCACategory, DCACategory.id == CategoryStage9E.category_id)
                .filter(CategoryStage9E.edition_id == edition.id).all())
    matches = [(stage, cat) for stage, cat in rows
               if stage.stage in ('write_in', 'qualified')
               and normalized(cat.name) in PRODUCER_YEAR_NAMES]
    if len(matches) < 2:
        return {}
    primary = min(matches, key=lambda pair: (
        normalized(pair[1].name) != 'producer of the year',
        pair[0].stage != 'qualified', pair[0].position, pair[1].id
    ))[1]
    return {cat.id: primary.id for stage, cat in matches if cat.id != primary.id}


# LITEFEET_PHASE9E_PERCENTAGE_RANKING_HOTFIX
# A category needs at least five Round 1 Yes/No responses before it is eligible
# for the automatic Top 25. This does NOT remove it from write-in consideration.
MIN_TOP25_CATEGORY_RESPONSES = 5


def top25_rank_key(item):
    """Approval ratio descending, then total votes descending, then stable name.

    Fractions compare exactly; rounding is for display only. Low-response
    categories sort below eligible ones and cannot be confirmed into the Top 25.
    """
    yes = int(item['yes'])
    no = int(item['no'])
    total = yes + no
    ratio = Fraction(yes, total) if total else Fraction(0, 1)
    return (total < MIN_TOP25_CATEGORY_RESPONSES,
            -ratio, -total, item['name'].casefold(), item['key'])


def ranked_candidates(db, ns, edition):
    """Rank Round 1 categories by YES percentage, with participation safeguard.

    Pending/rejected new suggestions are excluded. No saved-draft prerequisite.
    """
    historical = db.query(DCAEdition).filter_by(year=2023).first()
    if not historical:
        return []
    votes = (db.query(DCAReturnCategoryVote.category_id, DCAReturnCategoryVote.bring_back,
                      func.count(DCAReturnCategoryVote.id))
             .join(DCACategorySuggestionSubmission,
                   DCACategorySuggestionSubmission.id == DCAReturnCategoryVote.submission_id)
             .filter(DCACategorySuggestionSubmission.edition_id == edition.id)
             .group_by(DCAReturnCategoryVote.category_id, DCAReturnCategoryVote.bring_back).all())
    by_id = defaultdict(lambda: {'yes': 0, 'no': 0})
    for cid, yes, count in votes:
        by_id[cid]['yes' if yes else 'no'] = int(count)
    entries = []
    for item in db.query(DCACategory).filter_by(edition_id=historical.id).all():
        v = by_id[item.id]
        entries.append(dict(key=f'returning:{item.id}', name=item.name, description=item.description or '',
                            source_type='returning', source_category_id=item.id,
                            yes=v['yes'], no=v['no']))
    for group in ns['dca_new_category_groups'](db, edition.id):
        if group['status'] != 'approved':
            continue
        entries.append(dict(key=f'new:{group["id"]}', name=group['name'],
                            description=group.get('description') or '', source_type='new',
                            source_category_id=None, yes=group['yes'], no=group['no']))
    overrides = {r.category_key: r.description for r in
                 db.query(DraftCategoryDescription9E).filter_by(edition_id=edition.id).all()}
    for item in entries:
        item['description'] = overrides.get(item['key'], item['description'])
    # An approved new suggestion may duplicate an older category's display name:
    # do not silently overwrite or double-count it when publishing.
    for item in entries:
        total = int(item['yes']) + int(item['no'])
        item['total_votes'] = total
        item['approval_percent'] = round(100 * item['yes'] / total, 1) if total else 0.0
        item['eligible_for_top25'] = total >= MIN_TOP25_CATEGORY_RESPONSES
    entries.sort(key=top25_rank_key)
    for index, item in enumerate(entries, 1):
        item['rank'] = index
    return entries


def stages_for(db, edition):
    rows = (db.query(CategoryStage9E, DCACategory)
            .join(DCACategory, DCACategory.id == CategoryStage9E.category_id)
            .filter(CategoryStage9E.edition_id == edition.id)
            .order_by(CategoryStage9E.position, DCACategory.name).all())
    aliases = producer_writein_alias_map(db, edition, rows=rows)
    return [(stage, cat) for stage, cat in rows if cat.id not in aliases]


def get_counts(db, edition, *, include_pending=False):
    """Count existing aliases together without deleting or rewriting votes.

    Only explicitly confirmed aliases are grouped. Other near-matches remain
    separate pending a human identity check.
    """
    statuses = ('pending', 'approved') if include_pending else ('approved',)
    nominees = (db.query(DCANominee).filter(
        DCANominee.edition_id == edition.id,
        DCANominee.moderation_status.in_(statuses)).all())
    nominee_ids = [n.id for n in nominees]
    counts = defaultdict(int)
    supporters = defaultdict(set)
    if nominee_ids:
        rows = (db.query(DCANominationSubmission.nominee_id,
                         DCANominationSubmission.submitter_hash)
                .filter(DCANominationSubmission.edition_id == edition.id,
                        DCANominationSubmission.nominee_id.in_(nominee_ids)).all())
        for nid, supporter in rows:
            counts[nid] += 1
            supporters[nid].add(supporter)
    aliases = producer_writein_alias_map(db, edition)
    categories = {cat.id: cat.name for cat in db.query(DCACategory).filter_by(
        edition_id=edition.id).all()}
    grouped = defaultdict(list)
    for n in nominees:
        canonical_id = aliases.get(n.category_id, n.category_id)
        group_name = categories.get(canonical_id, categories.get(n.category_id, ''))
        grouped[(canonical_id, canonical_nominee_key(
            n.name, category_name=group_name))].append(n)
    by_cat = defaultdict(list)
    category_supporters = defaultdict(set)
    for (cid, _), matching in grouped.items():
        # Prefer the canonical ID for new submissions; previous alias IDs
        # remain linked via the ids list for existing justification records.
        group_name = categories.get(cid, '')
        display, canonical_key = canonical_nominee_name(
            matching[0].name, category_name=group_name)
        matching.sort(key=lambda n: (n.category_id != cid,
                                     n.normalized_name != canonical_key, n.id))
        primary = matching[0]
        members = [n.id for n in matching]
        total = sum(counts[nid] for nid in members)
        by_cat[cid].append(dict(
            id=primary.id, ids=members, name=display, count=total,
        ))
        for nid in members:
            category_supporters[cid].update(supporters[nid])
    for vals in by_cat.values():
        vals.sort(key=lambda x: (-x['count'], x['name'].casefold()))
    category_support = {cid: len(people) for cid, people in category_supporters.items()}
    return by_cat, category_support

def qualification(db, edition, stages=None):
    if stages is None:
        stages = stages_for(db, edition)
    nominees, support = get_counts(db, edition)
    top = [cat.id for stage, cat in stages if stage.stage == 'top25']
    floor = min((support.get(cid, 0) for cid in top), default=0)
    required = max(20, floor + 1)
    results = {}
    for stage, cat in stages:
        if stage.stage not in ('write_in', 'qualified'):
            continue
        supporters = support.get(cat.id, 0)
        distinct_nominees = len(nominees.get(cat.id, []))
        results[cat.id] = dict(supporters=supporters, eligible_nominees=distinct_nominees,
                               required=required, met=supporters >= required and distinct_nominees >= 5,
                               qualified=stage.stage == 'qualified')
    return results, floor, required


def correct_2026_event_category_title(session_factory):
    """Correct the current award label, without rewriting historical editions.

    Existing nominations reference category IDs, so the rename preserves all
    nomination relationships, totals and moderation records.
    """
    with session_factory.begin() as db:
        edition = db.query(DCAEdition).filter_by(year=2026).first()
        if edition is None:
            return False
        previous = (db.query(DCACategory).filter_by(
            edition_id=edition.id, normalized_name='best event of 2023').first())
        if previous is None:
            return False
        collision = (db.query(DCACategory).filter_by(
            edition_id=edition.id, normalized_name='best event of the year').first())
        if collision is not None:
            return False  # Preserve distinct category records for editorial review.
        previous.name = 'Best Event of the Year'
        previous.normalized_name = 'best event of the year'
        return True


def install_phase9e(app, ns):
    """Run after the original routes are registered; never changes existing route URL."""
    engine = ns['engine']
    Base.metadata.create_all(bind=engine, tables=TABLES, checkfirst=True)
    from dca_rebuild.nomination_migration import migrate_nomination_history
    migrate_nomination_history(engine)
    SessionLocal = ns['SessionLocal']
    correct_2026_event_category_title(SessionLocal)
    admin_login_required = ns['admin_login_required']
    private_hash = ns['private_hash']

    @app.context_processor
    def phase9e_admin_template_context():
        if request.endpoint != 'admin_round1' or not session.get('ledger_admin_authenticated'):
            return {'phase9e': None}
        db = SessionLocal()
        try:
            edition = db.query(DCAEdition).filter_by(year=2026).first()
            if not edition:
                return {'phase9e': None}
            ranked = ranked_candidates(db, ns, edition)
            top_candidates = [r for r in ranked if r['eligible_for_top25']][:25]
            eligible_count = sum(r['eligible_for_top25'] for r in ranked)
            stages = stages_for(db, edition)
            published = {cat.normalized_name: (stage.stage, stage.position) for stage, cat in stages}
            top = [dict(category=cat, position=stage.position) for stage, cat in stages if stage.stage == 'top25']
            legacy_official = db.query(DCACategory).filter_by(edition_id=edition.id, status='official').count()
            writeins = [dict(category=cat, position=stage.position) for stage, cat in stages if stage.stage in ('write_in', 'qualified')]
            writein_names = {cat['category'].normalized_name for cat in writeins}
            remaining = [entry for entry in ranked if normalized(entry['name']) not in published]
            qualified, floor, requirement = qualification(db, edition, stages)
            return {'phase9e': dict(ranked=ranked, top_candidates=top_candidates,
                                   eligible_count=eligible_count, min_votes=MIN_TOP25_CATEGORY_RESPONSES,
                                   top=top, writeins=writeins, remaining=remaining,
                                   published=published, writein_names=writein_names,
                                   qualified=qualified, floor=floor, requirement=requirement,
                                   closed=is_closed(), count_top=len(top), legacy_official=legacy_official,
                                   host_enabled=os.getenv('DCA_2026_NOMINATIONS_ENABLED') == 'true')}
        finally:
            db.close()

    @app.route('/admin/dca/phase9e/adopt-existing-top25', methods=['POST'])
    @admin_login_required
    def phase9e_adopt_existing_top25():
        """Safely bridge previously published Phase 9D's 25 into the new wizard."""
        if not csrf_ok() or request.form.get('confirmation') != 'ADOPT TOP 25':
            abort(400, 'Invalid confirmation')
        db = SessionLocal()
        try:
            edition = db.query(DCAEdition).filter_by(year=2026).first()
            if not edition or edition.phase != 'nominations':
                abort(409, 'No staged nomination edition')
            if db.query(CategoryStage9E).filter_by(edition_id=edition.id).count():
                abort(409, 'Category stages already exist')
            categories = db.query(DCACategory).filter_by(edition_id=edition.id, status='official').all()
            if len(categories) != 25:
                abort(409, 'Expected exactly 25 existing official categories')
            rank_map = {normalized(entry['name']): entry['rank']
                        for entry in ranked_candidates(db, ns, edition)}
            categories.sort(key=lambda c: (rank_map.get(c.normalized_name, 99999), c.name.casefold()))
            for i, category in enumerate(categories, 1):
                db.add(CategoryStage9E(edition_id=edition.id, category_id=category.id,
                                      stage='top25', position=i))
            db.commit()
            flash('Existing Top 25 adopted without changing category membership or nominations.')
            return redirect(url_for('admin_round1') + '#lf-9e-top25')
        except Exception:
            db.rollback()
            raise
        finally:
            db.close()

    @app.route('/admin/dca/phase9e/description', methods=['POST'])
    @admin_login_required
    def phase9e_save_description():
        if not csrf_ok():
            abort(400, 'Invalid CSRF token')
        key = request.form.get('category_key', '')
        desc = ' '.join(request.form.get('description', '').split())
        if not desc or len(desc) > 500:
            abort(400, 'Description must be 1 to 500 characters')
        db = SessionLocal()
        try:
            edition = db.query(DCAEdition).filter_by(year=2026).first()
            if not edition:
                abort(404)
            eligible = {item['key']: item for item in ranked_candidates(db, ns, edition)}
            if key not in eligible:
                abort(400, 'Invalid category')
            existing = db.query(DraftCategoryDescription9E).filter_by(edition_id=edition.id, category_key=key).first()
            if existing:
                existing.description = desc
            else:
                db.add(DraftCategoryDescription9E(edition_id=edition.id, category_key=key, description=desc))
            # Keep an already-published 2026 category in sync without editing 2023 history.
            row = db.query(DCACategory).filter_by(edition_id=edition.id, normalized_name=normalized(eligible[key]['name'])).first()
            if row:
                row.description = desc
            db.commit()
            flash('Category description saved.')
            return redirect(url_for('admin_round1') + '#lf-9e-top25')
        except Exception:
            db.rollback()
            raise
        finally:
            db.close()

    @app.route('/admin/dca/phase9e/confirm-top25', methods=['POST'])
    @admin_login_required
    def phase9e_confirm_top25():
        if not csrf_ok() or request.form.get('confirmation') != 'CONFIRM TOP 25':
            abort(400, 'Invalid confirmation')
        if not ns['dca_categories_closed']():
            abort(409, 'Round 1 is still open')
        db = SessionLocal()
        try:
            edition = db.query(DCAEdition).filter_by(year=2026).first()
            if not edition:
                abort(404)
            if edition.phase == 'nominations' or db.query(CategoryStage9E).filter_by(edition_id=edition.id).count():
                abort(409, 'Top 25 already published; do not overwrite existing nominations')
            if db.query(DCACategory).filter_by(edition_id=edition.id, status='official').count():
                abort(409, 'Official categories already exist; review before republishing')
            ranked = ranked_candidates(db, ns, edition)
            eligible = [r for r in ranked if r['eligible_for_top25']]
            if len(eligible) < 25:
                abort(409, f'At least 25 categories with {MIN_TOP25_CATEGORY_RESPONSES} or more Round 1 votes required')
            selected = eligible[:25]
            names = [normalized(item['name']) for item in selected]
            if len(set(names)) != 25:
                abort(409, 'Duplicate category names in Top 25: merge before publishing')
            for position, item in enumerate(selected, 1):
                row = db.query(DCACategory).filter_by(edition_id=edition.id, normalized_name=normalized(item['name'])).first()
                if row is None:
                    row = DCACategory(edition_id=edition.id, name=item['name'],
                                      normalized_name=normalized(item['name']), description=item['description'],
                                      source_type=item['source_type'], source_category_id=item['source_category_id'],
                                      status='official')
                    db.add(row)
                    db.flush()
                else:
                    row.status = 'official'
                    row.description = item['description']
                db.add(CategoryStage9E(edition_id=edition.id, category_id=row.id, stage='top25', position=position))
            edition.phase = 'nominations'
            db.commit()
            flash('Top 25 confirmed. Public nominations still require the host enable flag.')
            return redirect(url_for('admin_round1') + '#lf-9e-top25')
        except Exception:
            db.rollback()
            raise
        finally:
            db.close()

    @app.route('/admin/dca/phase9e/publish-writeins', methods=['POST'])
    @admin_login_required
    def phase9e_publish_writeins():
        if not csrf_ok():
            abort(400, 'Invalid CSRF token')
        keys = list(dict.fromkeys(request.form.getlist('category_key')))
        if not keys:
            abort(400, 'Select approved categories')
        db = SessionLocal()
        try:
            edition = db.query(DCAEdition).filter_by(year=2026).first()
            if not edition or edition.phase != 'nominations':
                abort(409, 'Confirm Top 25 first')
            stages = stages_for(db, edition)
            if len([s for s, _ in stages if s.stage == 'top25']) != 25:
                abort(409, 'A confirmed Top 25 is required')
            available = {r['key']: r for r in ranked_candidates(db, ns, edition)}
            published_names = {cat.normalized_name for _, cat in stages}
            selected = []
            for key in keys:
                if key not in available:
                    abort(400, 'Invalid or unapproved category')
                item = available[key]
                if normalized(item['name']) in published_names:
                    abort(409, 'Category already visible')
                selected.append(item)
            if len({normalized(x['name']) for x in selected}) != len(selected):
                abort(409, 'Duplicate category names: merge before publishing')
            next_pos = max((s.position for s, _ in stages), default=25)
            for item in selected:
                row = db.query(DCACategory).filter_by(edition_id=edition.id, normalized_name=normalized(item['name'])).first()
                if not row:
                    row = DCACategory(edition_id=edition.id, normalized_name=normalized(item['name']),
                                      name=item['name'], description=item['description'],
                                      source_type=item['source_type'], source_category_id=item['source_category_id'],
                                      status='write_in_eligible')
                    db.add(row)
                    db.flush()
                else:
                    row.status = 'write_in_eligible'
                    row.description = item['description']
                next_pos += 1
                db.add(CategoryStage9E(edition_id=edition.id, category_id=row.id,
                                      stage='write_in', position=next_pos))
            db.commit()
            flash(f'{len(selected)} additional categories published for optional write-in nominations.')
            return redirect(url_for('admin_round1') + '#lf-9e-top25')
        except Exception:
            db.rollback()
            raise
        finally:
            db.close()

    @app.route('/admin/dca/phase9e/confirm-qualified', methods=['POST'])
    @admin_login_required
    def phase9e_confirm_qualified():
        if not csrf_ok():
            abort(400)
        if nomination_deadline() is None or not is_closed():
            abort(409, 'Set a nomination deadline and wait for nominations to close')
        try:
            category_id = int(request.form.get('category_id', ''))
        except ValueError:
            abort(400)
        db = SessionLocal()
        try:
            edition = db.query(DCAEdition).filter_by(year=2026).first()
            stages = stages_for(db, edition)
            matching = [(s, c) for s, c in stages if c.id == category_id and s.stage == 'write_in']
            if not matching:
                abort(404)
            result, _, _ = qualification(db, edition, stages)
            if not result[category_id]['met']:
                abort(409, 'Write-in has not met eligibility requirements')
            stage, category = matching[0]
            stage.stage = 'qualified'
            category.status = 'official'
            db.commit()
            flash('Write-in category qualified and added to the official awards list.')
            return redirect(url_for('admin_round1') + '#lf-9e-top25')
        except Exception:
            db.rollback()
            raise
        finally:
            db.close()

    @app.get('/awards/dancers-choice/write-ins', endpoint='phase9e_writeins_legacy')
    def legacy_writein_categories_9e():
        query = request.args.get('q', '').strip()[:100]
        return redirect(url_for('phase9e_writeins', **({'q': query} if query else {})), code=301)

    @app.get('/write-ins', endpoint='phase9e_writeins')
    def writein_categories_9e():
        """All moderator-approved categories outside the Top 25, not only published write-ins.

        Unapproved/rejected category suggestions and private supporter details stay private.
        Viewing does not publish, approve, or otherwise mutate a category.
        """
        db = SessionLocal()
        try:
            edition = db.query(DCAEdition).filter_by(year=2026).first()
            entries = []
            requirement = 20
            floor = 0
            if edition:
                stages = stages_for(db, edition)
                top_names = {
                    writein_category_key(cat.name) for stage, cat in stages if stage.stage == 'top25'
                }
                live_writeins = {
                    writein_category_key(cat.name): (stage, cat)
                    for stage, cat in stages if stage.stage in ('write_in', 'qualified')
                }
                qualifying, floor, requirement = qualification(db, edition, stages)
                public_nominees, public_support = get_counts(db, edition, include_pending=True)
                accepting_support = bool(edition.phase == 'nominations' and
                    os.getenv('DCA_2026_NOMINATIONS_ENABLED') == 'true' and
                    not is_closed() and len([stage for stage, _ in stages if stage.stage == 'top25']) == 25)
                # Include ALL submitted category names not in the Top 25,
                # including pending ones. Merged aliases are grouped, rejected
                # entries remain excluded to avoid resurfacing spam or abuse.
                # Listing a suggestion does not silently promote it to a finalist.
                historical = db.query(DCAEdition).filter_by(year=2023).first()
                candidates = {}
                if historical:
                    for cat in db.query(DCACategory).filter_by(edition_id=historical.id).all():
                        key = writein_category_key(cat.name)
                        if key not in top_names:
                            candidates[key] = dict(name=writein_category_label(cat.name),
                                                   description=cat.description or '')
                for group in ns['dca_new_category_groups'](db, edition.id):
                    key = writein_category_key(group['name'])
                    if key not in top_names:
                        candidates[key] = dict(
                            name=writein_category_label(group['name']),
                            description=group.get('description') or '',
                        )
                for name, (stage, cat) in live_writeins.items():
                    candidates[name] = dict(name=writein_category_label(cat.name),
                                            description=cat.description or '')
                for key, item in sorted(candidates.items(),
                                        key=lambda pair: pair[1]['name'].casefold()):
                    staged = live_writeins.get(key)
                    stage, cat = staged if staged else (None, None)
                    counts = qualifying.get(cat.id, {}) if cat is not None else {}
                    entries.append(dict(
                        name=item['name'], description=item['description'],
                        category_id=cat.id if cat is not None else None,
                        open_for_nominations=bool(
                            stage and stage.stage in ('write_in', 'qualified')
                            and edition.phase == 'nominations'
                            and os.getenv('DCA_2026_NOMINATIONS_ENABLED') == 'true'
                            and not is_closed()
                        ),
                        published=bool(stage),
                        accepting_support=accepting_support,
                        qualified=bool(stage and stage.stage == 'qualified'),
                        meets_threshold=bool(counts.get('met')),
                        supporters=counts.get('supporters', 0),
                        nominees=counts.get('eligible_nominees', 0),
                        public_nominees=public_nominees.get(cat.id, []) if cat is not None else [],
                        public_supporters=public_support.get(cat.id, 0) if cat is not None else 0,
                    ))
            total = len(entries)
            search = (request.args.get('q') or '').strip()[:100]
            if search:
                entries = [
                    item for item in entries
                    if search.casefold() in (item['name'] + ' ' + item['description']).casefold()
                ]
            session.setdefault('lf9e_writeins_csrf', secrets.token_urlsafe(32))
            response = render_template(
                'dca_writeins.html', entries=entries, total=total, search=search,
                requirement=requirement, floor=floor,
                writeins_csrf=session['lf9e_writeins_csrf'],
            )
            return response
        finally:
            db.close()

    @app.post('/awards/dancers-choice/write-ins/activate', endpoint='phase9e_activate_writein')
    def activate_writein_9e():
        """Community access to a proposed category without unavailable admin tooling.

        No public activation after nomination close; Top 25 and historical
        categories are not modified. Previously rejected suggestions are excluded.
        """
        expected = session.get('lf9e_writeins_csrf', '')
        submitted = request.form.get('csrf_token', '')
        if not expected or not secrets.compare_digest(expected, submitted):
            abort(400, 'Invalid submission token')
        key = writein_category_key((request.form.get('category') or '').strip()[:250])
        if not key:
            abort(400, 'Choose a category')
        db = SessionLocal()
        try:
            edition = db.query(DCAEdition).filter_by(year=2026).first()
            if (not edition or edition.phase != 'nominations'
                or os.getenv('DCA_2026_NOMINATIONS_ENABLED') != 'true'
                or is_closed()):
                abort(409, 'Nominations are not open')
            stages = stages_for(db, edition)
            if len([stage for stage, _ in stages if stage.stage == 'top25']) != 25:
                abort(409, 'The official Top 25 must be finalized first')
            existing = next((cat for stage, cat in stages
                             if writein_category_key(cat.name) == key), None)
            if existing:
                return redirect(url_for('dca_nominations_closed', category=existing.id))
            # Only names already provided through the recorded category round.
            # Reject names previously moderated out of the public list.
            historical = db.query(DCAEdition).filter_by(year=2023).first()
            possible = {}
            if historical:
                for cat in db.query(DCACategory).filter_by(edition_id=historical.id).all():
                    possible[writein_category_key(cat.name)] = dict(
                        name=writein_category_label(cat.name), description=cat.description or '',
                        source_type='returning', source_category_id=cat.id)
            for group in ns['dca_new_category_groups'](db, edition.id):
                possible[writein_category_key(group['name'])] = dict(
                    name=writein_category_label(group['name']), description=group.get('description') or '',
                    source_type='new', source_category_id=None)
            item = possible.get(key)
            if not item:
                abort(404, 'Unknown category')
            record = db.query(DCACategory).filter_by(
                edition_id=edition.id, normalized_name=key).first()
            if record is None:
                record = DCACategory(
                    edition_id=edition.id, name=item['name'],
                    normalized_name=key, description=item['description'],
                    source_type=item['source_type'],
                    source_category_id=item['source_category_id'],
                    status='write_in_eligible')
                db.add(record)
                db.flush()
            else:
                record.status = 'write_in_eligible'
            db.add(CategoryStage9E(
                edition_id=edition.id, category_id=record.id, stage='write_in',
                position=max((stage.position for stage, _ in stages), default=25) + 1))
            db.commit()
            return redirect(url_for('dca_nominations_closed', category=record.id))
        except IntegrityError:
            db.rollback()
            # Another visitor may have already activated this category.
            existing = next((cat for stage, cat in stages_for(db, edition)
                             if writein_category_key(cat.name) == key), None)
            if existing:
                return redirect(url_for('dca_nominations_closed', category=existing.id))
            raise
        finally:
            db.close()

    @app.route('/awards/dancers-choice/nomination-reasons', methods=['GET', 'POST'],
               endpoint='phase9e_nomination_reasons')
    def qualification_reasons():
        """Public list and moderated supporting reasons, separate from nominations."""
        with SessionLocal() as db:
            edition = db.query(DCAEdition).filter_by(year=2026).first()
            if not edition:
                abort(404)
            session.setdefault('lf9e_nomination_csrf', secrets.token_urlsafe(32))
            pending = nominees_missing_reasons(db, edition)
            if request.method == 'POST':
                token = request.form.get('csrf_token', '')
                if not token or not secrets.compare_digest(
                    token, session['lf9e_nomination_csrf']):
                    abort(400, 'Invalid form token')
                email = (request.form.get('email') or '').strip().casefold()
                if len(email) > 254 or not re.fullmatch(r'[^\s@]+@[^\s@]+\.[^\s@]+', email):
                    abort(400, 'Enter a valid email address')
                who = private_hash('dca-nomination:' + email)
                nominee_id = request.form.get('nominee_id', type=int)
                item = next((n for n in pending if n['nominee_id'] == nominee_id), None)
                if not item:
                    abort(400, 'Nominee is no longer awaiting qualification reasons')
                reason = (request.form.get('reason') or '').strip()
                evidence_url = (request.form.get('evidence_url') or '').strip()
                if len(reason) < 20 or len(reason) > 2000:
                    abort(400, 'Explain qualifying activity in 20–2000 characters')
                if evidence_url and (len(evidence_url) > 500 or
                                    not re.fullmatch(r'https?://[^\s]+', evidence_url)):
                    abort(400, 'Use a valid http(s) evidence link')
                existing = db.query(NomineeQualificationReason9E).filter_by(
                    edition_id=edition.id, nominee_id=nominee_id,
                    submitter_hash=who).first()
                if existing:
                    abort(409, 'You have already submitted a reason for this nominee')
                db.add(NomineeQualificationReason9E(
                    edition_id=edition.id, nominee_id=nominee_id,
                    submitter_hash=who, reason=reason,
                    evidence_url=evidence_url or None))
                try:
                    db.commit()
                except IntegrityError:
                    db.rollback()
                    abort(409, 'Reason already submitted')
                flash('Reason submitted for eligibility review. Nomination totals have not changed.')
                return redirect(url_for('phase9e_nomination_reasons'), code=303)
            return render_template('dca_nomination_reasons.html', pending=pending,
                                   csrf_token=session['lf9e_nomination_csrf'])

    @app.route('/admin/dca/nomination-reasons', methods=['GET', 'POST'],
               endpoint='phase9e_admin_qualification_reasons')
    @admin_login_required
    def review_qualification_reasons():
        if request.method == 'POST':
            if not csrf_ok():
                abort(400, 'Invalid administrator token')
            reason_id = request.form.get('reason_id', type=int)
            decision = request.form.get('decision')
            if decision not in ('verified', 'insufficient', 'rejected'):
                abort(400, 'Invalid decision')
            with SessionLocal.begin() as db:
                row = db.get(NomineeQualificationReason9E, reason_id)
                if not row:
                    abort(404)
                row.moderation_status = decision
                row.reviewed_at = datetime.utcnow()
            return redirect(url_for('phase9e_admin_qualification_reasons'), code=303)
        with SessionLocal() as db:
            reasons = db.query(NomineeQualificationReason9E).order_by(
                NomineeQualificationReason9E.submitted_at.desc()).limit(500).all()
            entries = [dict(id=r.id, nominee=db.get(DCANominee, r.nominee_id).name,
                            reason=r.reason, evidence_url=r.evidence_url,
                            status=r.moderation_status, submitted=r.submitted_at)
                       for r in reasons if db.get(DCANominee, r.nominee_id)]
            return render_template('admin_dca_qualification_reasons.html',
                                   entries=entries,
                                   csrf_token=session.get('dca_moderation_csrf', ''))

    @app.after_request
    def private_nomination_response(response):
        if request.endpoint == 'dca_nominations_closed':
            response.headers['Cache-Control'] = 'private, no-store'
            response.headers['Referrer-Policy'] = 'same-origin'
        return response

    @app.get('/awards/dancers-choice/nominee-name-check')
    def phase9e_nominee_name_check():
        """Fast pre-submit duplicate hint, scoped to the verified-email session."""
        if not session.get('lf9e_recent_hash'):
            abort(401)
        name = (request.args.get('name') or '').strip()[:250]
        cid = request.args.get('category_id', type=int)
        if not cid or len(name) < 2:
            return jsonify(matches=[], canonical_name=name, requires_confirmation=False)
        db = SessionLocal()
        try:
            edition = db.query(DCAEdition).filter_by(year=2026).first()
            if not edition or cid not in {
                category.id for _, category in stages_for(db, edition)
            }:
                abort(404)
            category = db.get(DCACategory, cid)
            display, key = canonical_nominee_name(name, category_name=category.name)
            matches = candidate_matches(db, category_id=cid, name=name)
            exact = any(match['type'] == 'existing' for match in matches)
            return jsonify(
                matches=matches,
                canonical_name=display,
                already_listed=exact,
                requires_confirmation=not exact and any(
                    match['type'] == 'similar' for match in matches
                ),
            )
        finally:
            db.close()

    def nomination_view_9e():
        from dca_rebuild.nomination_service import category_history, remaining_seconds, normalize_nominee_name
        db = SessionLocal()
        try:
            edition = db.query(DCAEdition).filter_by(year=2026).first()
            if (not edition or edition.phase != 'nominations'
                or os.getenv('DCA_2026_NOMINATIONS_ENABLED') != 'true'):
                if request.method == 'POST':
                    abort(403, 'Nominations not open')
                return render_template('dca_nominations_closed.html')
            stages = stages_for(db, edition)
            top = [(s, c) for s, c in stages if s.stage == 'top25']
            if len(top) != 25:
                if request.method == 'POST':
                    abort(403, 'Top 25 not confirmed')
                return render_template('dca_nominations_closed.html')
            other = [(s, c) for s, c in stages if s.stage in ('write_in', 'qualified')]
            allowed = {c.id: c for _, c in top + other}
            session.setdefault('lf9e_nomination_csrf', secrets.token_urlsafe(32))
            if request.method == 'POST':
                token = request.form.get('csrf_token', '')
                if not token or not secrets.compare_digest(token, session['lf9e_nomination_csrf']):
                    abort(400, 'Invalid submission token')
                action = request.form.get('action', 'nominate')
                if action in ('change-email', 'done'):
                    # Done ends only this visitor's selected email session.
                    # Persistent per-email nomination cooldowns and submissions stay intact.
                    session.pop('lf9e_recent_hash', None)
                    session.pop('lf9e_skipped', None)
                    if action == 'done' and request.form.get('next') == 'standings':
                        return redirect(url_for('dca_nominations_closed', view='results'), code=303)
                    return redirect(url_for('dca_nominations_closed'), code=303)
                if action == 'identify':
                    email = request.form.get('email', '').strip().casefold()
                    if len(email) > 254 or not re.fullmatch(r'[^\s@]+@[^\s@]+\.[^\s@]+', email):
                        abort(400, 'Enter a valid email')
                    who = private_hash('dca-nomination:' + email)
                    # Store the normalized email on the server, never in the
                    # signed (readable) browser session.
                    db.execute(
                        insert_for(db, DCANominationContact)
                        .values(submitter_hash=who, email_address=email,
                                updated_at=datetime.utcnow())
                        .on_conflict_do_update(
                            index_elements=['submitter_hash'],
                            set_={'email_address': email, 'updated_at': datetime.utcnow()},
                        )
                    )
                    # A returning participant can safely reconnect their
                    # own older hash-only nominations to the email they supplied.
                    # Never attempt to reverse or expose an email hash.
                    db.query(DCANominationSubmission).filter(
                        DCANominationSubmission.edition_id == edition.id,
                        DCANominationSubmission.submitter_hash == who,
                        DCANominationSubmission.submitter_email.is_(None),
                    ).update({'submitter_email': email}, synchronize_session=False)
                    db.commit()
                    if who != session.get('lf9e_recent_hash'):
                        session.pop('lf9e_skipped', None)
                    session['lf9e_recent_hash'] = who
                    requested = request.form.get('return_category', '').strip()
                    if requested:
                        try:
                            requested_id = int(requested)
                        except ValueError:
                            abort(400, 'Invalid return category')
                        if requested_id not in allowed:
                            abort(404)
                        return redirect(url_for('dca_nominations_closed', category=requested_id))
                    return redirect(url_for('dca_nominations_closed'))
                who = session.get('lf9e_recent_hash')
                if not who:
                    abort(400, 'Enter your email before selecting a category')
                if is_closed():
                    abort(403, 'Nominations are closed')
                try:
                    cid = int(request.form.get('category_id', ''))
                except (ValueError, TypeError):
                    abort(400, 'Select a valid category')
                if cid not in allowed:
                    abort(400, 'Category is not available')
                if action == 'skip':
                    skipped = set(session.get('lf9e_skipped', []))
                    skipped.add(cid)
                    session['lf9e_skipped'] = sorted(skipped)
                    return redirect(url_for('dca_nominations_closed'))
                if action != 'nominate':
                    abort(400, 'Invalid action')
                name = request.form.get('name', '').strip()
                team = request.form.get('team', '').strip()
                location = request.form.get('location', '').strip()
                instagram = request.form.get('instagram', '').strip().lstrip('@')
                instagram = re.sub(r'^https?://(?:www\.)?instagram\.com/', '', instagram, flags=re.I).split('?')[0].strip('/')
                reason = request.form.get('reason', '').strip()
                if len(reason) < 20:
                    abort(400, 'Explain the nominee\'s activity during November 2025–November 2026 (at least 20 characters)')
                if len(team) > 250 or len(location) > 250 or len(instagram) > 100 or len(reason) > 2000:
                    abort(400, 'One or more fields are too long')
                if instagram and not re.fullmatch(r'[A-Za-z0-9._]{1,30}', instagram):
                    abort(400, 'Instagram must be a username')
                try:
                    normalize_nominee_name(name)
                except ValueError as exc:
                    abort(400, str(exc))
                matches = candidate_matches(db, category_id=cid, name=name)
                if (not any(match['type'] == 'existing' for match in matches)
                    and any(match['type'] == 'similar' for match in matches)
                    and request.form.get('confirm_distinct') != '1'):
                    flash('A similar name already exists. Check the spelling or confirm a different person before submitting.')
                    return redirect(url_for('dca_nominations_closed', category=cid, nominate=1), code=303)
                contact = db.get(DCANominationContact, who)
                if contact is None:
                    # Existing pre-migration sessions have hashes but no stored email.
                    session.pop('lf9e_recent_hash', None)
                    flash('Please enter your email again to complete your nomination.')
                    return redirect(url_for('dca_nominations_closed'))
                try:
                    nominee, created = add_nomination(db, edition_id=edition.id, category_id=cid,
                                                      name=name, submitter_hash=who,
                                                      submitter_email=contact.email_address,
                                                      description=reason)
                    if not created:
                        db.rollback()
                        flash('This category is on cooldown. Other available categories are ready to nominate.')
                        return redirect(url_for('dca_nominations_closed'))
                    submission = (db.query(DCANominationSubmission).filter_by(
                        nominee_id=nominee.id, submitter_hash=who)
                        .order_by(DCANominationSubmission.id.desc()).first())
                    db.add(NominationDetail9E(submission_id=submission.id, team=team or None,
                                              location=location or None, instagram=instagram or None,
                                              justification=reason or None))
                    db.commit()
                except IntegrityError:
                    db.rollback()
                    flash('Your nomination could not be recorded. Check your category status and try again.')
                    return redirect(url_for('dca_nominations_closed'))
                session['lf9e_skipped'] = [x for x in session.get('lf9e_skipped', []) if x != cid]
                flash('Nomination received.')
                return redirect(url_for('dca_nominations_closed', view='results'))
            results_view = request.args.get('view') == 'results'
            who = session.get('lf9e_recent_hash')
            categories, writeins = [], []
            summary = dict(submitted=0, available=0, cooldown=0, skipped=0)
            selected = None
            suggestion = None
            suggestion_details = []
            if who or results_view:
                nominees, support = get_counts(db, edition, include_pending=True)
                history = defaultdict(list)
                for entry, nominee in (category_history(db, edition.id, who) if who else []):
                    history[nominee.category_id].append(dict(name=nominee.name,
                        status=nominee.moderation_status, at=entry.submitted_at.isoformat() + 'Z'))
                rules, floor, requirement = qualification(db, edition, stages)
                skipped = set(session.get('lf9e_skipped', []))
                now = datetime.now(timezone.utc).replace(tzinfo=None)
                for stage, cat in top + other:
                    past = history[cat.id]
                    remaining = remaining_seconds(datetime.fromisoformat(past[0]['at']), now) if past else 0
                    row = dict(id=cat.id, name=writein_category_label(cat.name),
                               description=cat.description or '',
                               nominees=nominees.get(cat.id, []), history=past,
                               remaining=remaining, available=not remaining and not is_closed(),
                               next_at=(datetime.fromisoformat(past[0]['at']) + timedelta(hours=24)).isoformat() if remaining else '',
                               support=support.get(cat.id, 0), required=requirement,
                               skipped=cat.id in skipped)
                    (categories if stage.stage == 'top25' else writeins).append(row)
                    summary['submitted'] += len(past)
                    summary['cooldown'] += bool(remaining)
                    summary['available'] += row['available']
                    summary['skipped'] += row['skipped']
                selected = next((c for c in categories + writeins if str(c['id']) == request.args.get('category')), None)
                if request.args.get('category') and selected is None:
                    abort(404)
                if request.args.get('suggestion'):
                    suggestion_id = request.args.get('suggestion', type=int)
                    suggestion = next((n for n in selected['nominees'] if n['id'] == suggestion_id), None) if selected else None
                    if suggestion is None:
                        abort(404)
                    rows = (db.query(NominationDetail9E)
                            .join(DCANominationSubmission, DCANominationSubmission.id == NominationDetail9E.submission_id)
                            .filter(DCANominationSubmission.nominee_id.in_(suggestion.get('ids', [suggestion_id])),
                                    DCANominationSubmission.edition_id == edition.id)
                            .order_by(DCANominationSubmission.submitted_at, DCANominationSubmission.id).all())
                    # Only submitted nominee details; never supporter identity.
                    suggestion_details = [dict(team=r.team, location=r.location,
                        instagram=r.instagram, reason=r.justification) for r in rows
                        if any((r.team, r.location, r.instagram, r.justification))]
                    if not suggestion_details:
                        nominee = db.get(DCANominee, suggestion_id)
                        if nominee.description:
                            suggestion_details = [dict(reason=nominee.description)]

            return render_template('dca_nominations_form.html', categories=categories, writeins=writeins,
                                   intro_categories=[dict(id=c.id, name=c.name) for _, c in top],
                                   intro_writeins=[dict(id=c.id, name=writein_category_label(c.name))
                                                   for _, c in other],
                                   selected=selected, suggestion=suggestion, suggestion_details=suggestion_details,
                                   show_form=request.args.get('nominate') == '1' or 'draft' in request.args,
                                   requested_category_id=(request.args.get('category', type=int)
                                                          if request.args.get('category', type=int) in allowed else None),
                                   identified=bool(who), results_view=results_view, summary=summary,
                                   csrf_token=session['lf9e_nomination_csrf'], closed=is_closed())
        finally:
            db.close()

    app.view_functions['dca_nominations_closed'] = nomination_view_9e
    app.logger.info('DCA nominations: per-category rolling UTC cooldowns and email-first grid')
