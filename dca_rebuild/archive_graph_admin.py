"""Opt-in admin UI for an explicitly configured local staging graph."""
import secrets
import sqlite3

from flask import abort, current_app, flash, redirect, render_template, request, session, url_for

from dca_rebuild.archive_graph import (
    RELATIONS, ReviewConflict, connected_path, decide_connection, graph_workspace, propose_connection,
)


def install_archive_graph_admin(app, ns):
    @app.route('/admin/archive/connections', methods=['GET', 'POST'], endpoint='vault_archive_connections')
    @ns['admin_login_required']
    def connections():
        path = current_app.config.get('VAULT_ARCHIVE_STAGING_PATH')
        enabled = current_app.config.get('VAULT_ARCHIVE_STAGING_REVIEW_ENABLED') is True
        if 'vault_archive_graph_csrf' not in session:
            session['vault_archive_graph_csrf'] = secrets.token_urlsafe(32)
        # The current site uses shared administrator authentication. This records
        # a signed, server-validated admin session, not a claimed individual name.
        if 'vault_archive_graph_reviewer' not in session:
            session['vault_archive_graph_reviewer'] = 'admin-session:' + secrets.token_urlsafe(18)
        if request.method == 'POST':
            if not path or not enabled:
                abort(403, description='Staging review is not enabled')
            if not secrets.compare_digest(session['vault_archive_graph_csrf'], request.form.get('csrf_token', '')):
                abort(400, description='Invalid review token')
            try:
                reviewer = session['vault_archive_graph_reviewer']
                action = request.form.get('action')
                if action == 'propose':
                    details = {}
                    relation = request.form.get('relation')
                    fields = {'member_of': ('from', 'until', 'date_certainty'),
                              'participated_in': ('role',),
                              'documented_by': ('start_seconds', 'end_seconds')}.get(relation, ())
                    for field in fields:
                        value = request.form.get(field, '').strip()
                        if value:
                            details[field] = int(value) if field.endswith('_seconds') else value
                    propose_connection(path, request.form.get('subject_id'), request.form.get('relation'),
                                       request.form.get('object_id'), int(request.form.get('evidence_revision_id', '')),
                                       reviewer, request.form.get('reason'), details)
                elif action in ('approve', 'reject', 'reverse', 'reopen'):
                    decide_connection(path, request.form.get('link_id'), action,
                                      int(request.form.get('expected_version', '')), reviewer,
                                      request.form.get('reason'))
                else:
                    abort(400, description='Unknown review action')
            except ReviewConflict as error:
                abort(409, description=str(error))
            except (ValueError, TypeError) as error:
                abort(400, description=str(error))
            except sqlite3.Error:
                abort(503, description='Staging database unavailable; no public records changed')
            flash('Staging review saved. Public records are unchanged.')
            return redirect(url_for('vault_archive_connections'), code=303)
        workspace = None
        path_result = None
        path_requested = bool(request.args.get('start_id') or request.args.get('end_id'))
        if path:
            try:
                workspace = graph_workspace(path, status=request.args.get('status', 'pending'),
                                            page=int(request.args.get('page', '1')), query=request.args.get('q', ''))
                if path_requested:
                    path_result = connected_path(path, request.args.get('start_id'), request.args.get('end_id'))
            except ValueError as error:
                abort(400, description=str(error))
            except sqlite3.Error:
                abort(503, description='Staging database unavailable')
        return render_template('admin_archive_connections.html', workspace=workspace, review_enabled=enabled,
                               csrf_token=session['vault_archive_graph_csrf'], relations=sorted(RELATIONS),
                               path_requested=path_requested, path_result=path_result)
