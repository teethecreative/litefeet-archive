/* Category selection uses real links/forms; no scripted heading focus. */
(function () {
  'use strict';
  document.addEventListener('DOMContentLoaded', function () {
    const root = document.querySelector('.lf9e');
    if (!root) return;
    const draftKey = 'lf9e-future-nomination-ideas';
    function drafts() {
      try { const rows = JSON.parse(localStorage.getItem(draftKey) || '[]'); return Array.isArray(rows) ? rows : []; }
      catch (_) { return []; }
    }
    const fields = ['name', 'team', 'location', 'instagram', 'reason'];
    const form = root.querySelector('form[data-lf9e-entry]');
    const list = document.getElementById('lf9e-saved-list');
    function renderDrafts() {
      if (!list) return;
      list.replaceChildren();
      const rows = drafts();
      if (!rows.length) { list.textContent = 'No ideas saved in this browser.'; return; }
      rows.forEach(function (idea, i) {
        const row = document.createElement('div'); row.className = 'lf9e-saved-row';
        const title = document.createElement('span'); title.textContent = idea.name || 'Untitled';
        const load = document.createElement('a'); load.className = 'lf9e-secondary'; load.textContent = 'LOAD';
        const destination = new URL(location.pathname, location.origin);
        destination.searchParams.set('category', idea.category_id); destination.searchParams.set('nominate', '1'); destination.searchParams.set('draft', i);
        load.href = destination.href;
        const remove = document.createElement('button'); remove.type = 'button';
        remove.textContent = 'REMOVE'; remove.className = 'lf9e-secondary';
        remove.addEventListener('click', function () {
          const saved = drafts(); saved.splice(i, 1);
          try { localStorage.setItem(draftKey, JSON.stringify(saved)); renderDrafts(); }
          catch (_) { window.alert('Browser storage is unavailable.'); }
        });
        row.append(title, load, remove); list.append(row);
      });
    }
    renderDrafts();
    if (form) {
      const index = new URLSearchParams(location.search).get('draft');
      const idea = index !== null ? drafts()[Number(index)] : null;
      if (idea && String(idea.category_id) === form.elements.category_id.value) {
        fields.forEach(field => { form.elements.namedItem(field).value = idea[field] || ''; });
      }
      root.querySelectorAll('[data-add-later]').forEach(function (button) {
        button.addEventListener('click', function () {
          if (!form.elements.name.value.trim()) { form.elements.name.focus(); return; }
          const idea = {category_id: form.elements.category_id.value};
          fields.forEach(field => { idea[field] = form.elements.namedItem(field).value.trim(); });
          const rows = drafts(); rows.push(idea);
          try { localStorage.setItem(draftKey, JSON.stringify(rows.slice(-30))); }
          catch (_) { window.alert('Browser storage unavailable; idea was not saved.'); return; }
          window.alert('Saved in this browser. This has not been submitted.');
        });
      });
    }
    function updateCooldowns() {
      root.querySelectorAll('[data-cooldown-until]').forEach(function (timer) {
        const seconds = Math.max(0, Math.ceil((Date.parse(timer.dataset.cooldownUntil) - Date.now()) / 1000));
        if (!seconds) {
          timer.textContent = '0s — refresh this page to check eligibility';
          return;
        }
        timer.textContent = Math.floor(seconds / 3600) + 'h ' + Math.floor(seconds % 3600 / 60) + 'm ' + seconds % 60 + 's';
      });
    }
    updateCooldowns(); window.setInterval(updateCooldowns, 1000);
  });
})();
