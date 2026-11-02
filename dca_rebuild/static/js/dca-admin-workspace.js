/* Phase 9C: accessible client-side table search, filters, sorting and paging.
   Rows are hidden visually, not disabled or removed, so selections on other
   pages still submit with Save Category Draft. */
(function () {
  'use strict';
  function initTable(prefix, size, match) {
    const table = document.getElementById('lf-' + prefix + '-table');
    const search = document.getElementById('lf-' + prefix + '-search');
    const filter = document.getElementById('lf-' + prefix + '-filter');
    const empty = document.getElementById('lf-' + prefix + '-empty');
    const pager = document.querySelector('[data-pager="' + prefix + '"]');
    const range = document.getElementById('lf-' + prefix + '-range');
    const pageLabel = document.getElementById('lf-' + prefix + '-page');
    if (!table || !search || !filter || !pager || !range || !pageLabel) return;
    const tbody = table.tBodies[0];
    const rows = Array.from(tbody.rows);
    const sort = document.getElementById('lf-' + prefix + '-sort');
    let page = 1;
    const stateKey = 'lf-dca-9d-table-' + prefix;
    try {
      const saved = JSON.parse(sessionStorage.getItem(stateKey) || 'null');
      if (saved && typeof saved === 'object') {
        search.value = typeof saved.search === 'string' ? saved.search : '';
        if (Array.from(filter.options).some(opt => opt.value === saved.filter)) filter.value = saved.filter;
        if (sort && Array.from(sort.options).some(opt => opt.value === saved.sort)) sort.value = saved.sort;
        page = Math.max(1, Number(saved.page) || 1);
      }
    } catch (_) { /* A disabled store should never block the table. */ }
    function matches(row) {
      const q = search.value.trim().toLocaleLowerCase();
      const f = filter.value;
      return (!q || (row.dataset.search || '').includes(q)) && match(row, f);
    }
    function ordered(list) {
      if (prefix !== 'category' || !sort) return list;
      const value = sort.value;
      return list.sort(function (a, b) {
        if (value === 'yes' || value === 'no') {
          const diff = Number(b.dataset[value] || 0) - Number(a.dataset[value] || 0);
          if (diff) return diff;
        } else if (value === 'selected') {
          const diff = Number(!!b.querySelector('input[name="category_key"]:checked')) - Number(!!a.querySelector('input[name="category_key"]:checked'));
          if (diff) return diff;
        }
        return (a.dataset.name || '').localeCompare(b.dataset.name || '');
      });
    }
    function render() {
      const visible = ordered(rows.filter(matches));
      const total = visible.length;
      const pages = Math.max(1, Math.ceil(total / size));
      page = Math.min(Math.max(1, page), pages);
      rows.forEach(function (row) { row.hidden = true; });
      if (prefix === 'category') visible.forEach(function (row) { tbody.appendChild(row); });
      const start = (page - 1) * size;
      visible.slice(start, start + size).forEach(function (row) { row.hidden = false; });
      if (empty) empty.hidden = total !== 0;
      range.textContent = total ? (start + 1) + '–' + Math.min(start + size, total) + ' of ' + total : '0 results';
      pageLabel.textContent = 'Page ' + page + ' of ' + pages;
      try { sessionStorage.setItem(stateKey, JSON.stringify({
        search: search.value, filter: filter.value, sort: sort ? sort.value : null, page: page
      })); } catch (_) {}
      pager.querySelectorAll('button[data-page-action]').forEach(function (button) {
        const action = button.dataset.pageAction;
        button.disabled = total === 0 || ((action === 'first' || action === 'prev') && page === 1) || ((action === 'next' || action === 'last') && page === pages);
      });
    }
    search.addEventListener('input', function () { page = 1; render(); });
    filter.addEventListener('change', function () { page = 1; render(); });
    if (sort) sort.addEventListener('change', function () { page = 1; render(); });
    pager.addEventListener('click', function (event) {
      const button = event.target.closest('button[data-page-action]');
      if (!button || button.disabled) return;
      const pages = Math.max(1, Math.ceil(rows.filter(matches).length / size));
      if (button.dataset.pageAction === 'first') page = 1;
      if (button.dataset.pageAction === 'prev') page--;
      if (button.dataset.pageAction === 'next') page++;
      if (button.dataset.pageAction === 'last') page = pages;
      render();
    });
    table.addEventListener('change', function (event) {
      if (event.target.matches('input[name="category_key"]')) {
        const count = document.getElementById('lf-selected-count');
        if (count) count.textContent = String(rows.filter(r => !!r.querySelector('input[name="category_key"]:checked')).length);
        if (prefix === 'category' && (filter.value === 'selected' || filter.value === 'unselected' || (sort && sort.value === 'selected'))) render();
      }
    });
    render();
    return { search, filter, render, reset: function () { page = 1; render(); } };
  }
  document.addEventListener('DOMContentLoaded', function () {
    initTable('email', 5, function (row, filter) {
      const count = Number(row.dataset.count || 0);
      return filter === 'all' || (filter === 'multiple' && count > 1) || (filter === 'single' && count === 1);
    });
    const categories = initTable('category', 10, function (row, filter) {
      const checked = !!row.querySelector('input[name="category_key"]:checked');
      return filter === 'all' || filter === row.dataset.source || filter === row.dataset.status ||
        (filter === 'selected' && checked) || (filter === 'unselected' && !checked) ||
        (filter === 'missing' && row.dataset.missing === 'true');
    });

    // The category table has two independent selection types: Round 2 draft
    // inclusion and bulk moderation of new-category suggestions only.
    // Modal editors sit above the table rather than expanding individual
    // card-like rows to different heights.
    document.querySelectorAll('.lf-ws-open-editor').forEach(function (button) {
      const dlg = button.parentElement.querySelector('dialog');
      if (!dlg) return;
      button.addEventListener('click', function () { dlg.showModal(); });
      dlg.querySelector('.lf-ws-dialog-close')?.addEventListener('click', function () { dlg.close(); });
      dlg.addEventListener('click', function (event) { if (event.target === dlg) dlg.close(); });
    });
    const section = document.getElementById('lf-categories-section');
    const toggle = document.getElementById('lf-edit-toggle');
    const tools = document.getElementById('lf-bulk-tools');
    const bulkForm = document.getElementById('lf-bulk-form');
    const bulkCount = document.getElementById('lf-bulk-count');
    const target = document.getElementById('lf-merge-target');
    const mergeButton = document.getElementById('lf-merge-selected');
    const selection = function () {
      return Array.from(document.querySelectorAll('input[name="suggestion_id"]:checked'));
    };
    function refreshBulk() {
      const selected = selection();
      if (bulkCount) bulkCount.textContent = String(selected.length);
      if (!target || !mergeButton) return;
      const oldTarget = target.value;
      target.replaceChildren(new Option('Select primary category', ''));
      selected.forEach(function (input) {
        const tr = input.closest('tr');
        if (!tr || tr.dataset.status === 'rejected') return;
        target.add(new Option(input.dataset.suggestionName || input.value, input.value));
      });
      if (selected.some(input => input.value === oldTarget)) target.value = oldTarget;
      mergeButton.disabled = selected.length < 2 || !target.value;
    }
    if (toggle && section && tools) {
      toggle.addEventListener('click', function () {
        const editing = section.dataset.editing !== 'true';
        section.dataset.editing = String(editing);
        toggle.setAttribute('aria-pressed', String(editing));
        toggle.textContent = editing ? 'DONE EDITING' : 'EDIT / BULK ACTIONS';
        tools.hidden = !editing;
        if (!editing) document.querySelectorAll('input[name="suggestion_id"]').forEach(input => input.checked = false);
        refreshBulk();
      });
    }
    document.getElementById('lf-category-table')?.addEventListener('change', function (event) {
      if (event.target.matches('input[name="suggestion_id"]')) refreshBulk();
    });
    if (target) target.addEventListener('change', refreshBulk);
    if (bulkForm) bulkForm.addEventListener('submit', function (event) {
      const selected = selection();
      const action = event.submitter && event.submitter.value;
      if (!selected.length || !['approved', 'rejected', 'merged'].includes(action) ||
          (action === 'merged' && (selected.length < 2 || !target.value))) {
        event.preventDefault(); alert('Select valid suggestions and a primary category if merging.'); return;
      }
      const meaning = action === 'rejected' ? 'remove from consideration' :
        action === 'merged' ? 'merge into the selected primary category' : 'approve';
      if (!confirm('Confirm: ' + meaning + ' ' + selected.length + ' selected suggestion(s)? Original votes will be preserved.')) {
        event.preventDefault();
      }
    });
    const form = document.getElementById('lf-draft-form');
    if (form && categories) {
      form.addEventListener('submit', function () {
        // Deliberately do not disable/serialize only visible rows.
        // Native form-associated checkboxes include selections on every page.
      });
    }
  });
})();

/* LITEFEET_PHASE9D_RESTORE_AND_FIRST25 */
(function () {
  'use strict';
  document.addEventListener('DOMContentLoaded', function () {
    var form = document.getElementById('lf-first25-form');
    if (form) {
      var count = document.getElementById('lf-first25-count');
      var button = document.getElementById('lf-first25-submit');
      var phrase = form.elements.namedItem('confirmation');
      function refresh() {
        var total = form.querySelectorAll('input[name="category_key"]:checked').length;
        count.textContent = String(total);
        button.disabled = total !== 25 || !phrase || phrase.value.trim() !== 'PUBLISH FIRST 25';
      }
      form.addEventListener('change', refresh);
      form.addEventListener('input', refresh);
      refresh();
    }
    var restored = sessionStorage.getItem('lf-dca-9d-scroll');
    if (restored !== null) {
      sessionStorage.removeItem('lf-dca-9d-scroll');
      var y = Number(restored);
      if (Number.isFinite(y) && y >= 0) {
        window.requestAnimationFrame(function () { window.scrollTo(0, y); });
      }
    }
    document.querySelectorAll('#lf-category-table form, #lf-draft-form, #lf-bulk-form').forEach(function (editForm) {
      editForm.addEventListener('submit', function () {
        sessionStorage.setItem('lf-dca-9d-scroll', String(window.scrollY));
      });
    });
  });
})();
