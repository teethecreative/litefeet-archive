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
    DCAEdition, DCANominee, DCANominationSubmission,
)
from dca_rebuild.nomination_service import (
    add_nomination, canonical_nominee_name, canonical_nominee_key, candidate_matches,
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


TABLES = [DailyNominationClaim9E.__table__, LegacyNominationDetail9E.__table__, NominationDetail9E.__table__,
          CategoryStage9E.__table__, DraftCategoryDescription9E.__table__]


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
    return (db.query(CategoryStage9E, DCACategory)
            .join(DCACategory, DCACategory.id == CategoryStage9E.category_id)
            .filter(CategoryStage9E.edition_id == edition.id)
            .order_by(CategoryStage9E.position, DCACategory.name).all())


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
    grouped = defaultdict(list)
    for n in nominees:
        grouped[(n.category_id, canonical_nominee_key(n.name))].append(n)
    by_cat = defaultdict(list)
    category_supporters = defaultdict(set)
    for (cid, _), matching in grouped.items():
        # Prefer the canonical ID for new submissions; previous alias IDs
        # remain linked via the ids list for existing justification records.
        display, canonical_key = canonical_nominee_name(matching[0].name)
        matching.sort(key=lambda n: (n.normalized_name != canonical_key, n.id))
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


def install_phase9e(app, ns):
    """Run after the original routes are registered; never changes existing route URL."""
    engine = ns['engine']
    Base.metadata.create_all(bind=engine, tables=TABLES, checkfirst=True)
    from dca_rebuild.nomination_migration import migrate_nomination_history
    migrate_nomination_history(engine)
    SessionLocal = ns['SessionLocal']
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
            display, key = canonical_nominee_name(name)
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
                if action == 'change-email':
                    session.pop('lf9e_recent_hash', None)
                    session.pop('lf9e_skipped', None)
                    return redirect(url_for('dca_nominations_closed'))
                if action == 'identify':
                    email = request.form.get('email', '').strip().casefold()
                    if len(email) > 254 or not re.fullmatch(r'[^\s@]+@[^\s@]+\.[^\s@]+', email):
                        abort(400, 'Enter a valid email')
                    who = private_hash('dca-nomination:' + email)
                    if who != session.get('lf9e_recent_hash'):
                        session.pop('lf9e_skipped', None)
                    session['lf9e_recent_hash'] = who
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
                try:
                    nominee, created = add_nomination(db, edition_id=edition.id, category_id=cid,
                                                      name=name, submitter_hash=who, description=reason)
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
                    row = dict(id=cat.id, name=cat.name, description=cat.description or '',
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
                                   intro_writeins=[dict(id=c.id, name=c.name) for _, c in other],
                                   selected=selected, suggestion=suggestion, suggestion_details=suggestion_details,
                                   show_form=request.args.get('nominate') == '1' or 'draft' in request.args,
                                   identified=bool(who), results_view=results_view, summary=summary,
                                   csrf_token=session['lf9e_nomination_csrf'], closed=is_closed())
        finally:
            db.close()

    app.view_functions['dca_nominations_closed'] = nomination_view_9e
    app.logger.info('DCA nominations: per-category rolling UTC cooldowns and email-first grid')
