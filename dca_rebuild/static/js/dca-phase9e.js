/* One category per screen. Navigation is browser-side; daily claim is server-enforced. */
(function () {
  'use strict';
  document.addEventListener('DOMContentLoaded', function () {
    const root = document.querySelector('.lf9e');
    if (!root) return;
    const screens = Array.from(root.querySelectorAll('[data-screen]'));
    const available = new Set(screens.map(s => s.dataset.screen));
    const key = 'lf9e-skipped-v1';
    let skipped = new Set();
    try { skipped = new Set(JSON.parse(sessionStorage.getItem(key) || '[]')); } catch (_) {}
    function go(dest) {
      if (!available.has(dest)) dest = 'welcome';
      screens.forEach(screen => { screen.hidden = screen.dataset.screen !== dest; });
      const skippedLabel = document.getElementById('lf9e-skipped-count');
      if (skippedLabel) skippedLabel.textContent = String(skipped.size);
      if (history.replaceState) history.replaceState(null, '', location.pathname + '?step=' + encodeURIComponent(dest));
      window.scrollTo(0, 0);
      const target = screens.find(s => s.dataset.screen === dest);
      const title = target && target.querySelector('h1');
      if (title) { title.setAttribute('tabindex','-1'); title.focus({preventScroll:true}); }
    }
    root.addEventListener('click', function(event) {
      const btn = event.target.closest('[data-go]');
      if (!btn) return;
      if (btn.dataset.skip) {
        skipped.add(btn.dataset.skip);
        try { sessionStorage.setItem(key, JSON.stringify(Array.from(skipped))); } catch (_) {}
      }
      go(btn.dataset.go);
    });
    go(root.dataset.initialStep || 'welcome');
    const draftKey = 'lf9e-future-nomination-ideas';
    function loadDrafts() {
      const list = document.getElementById('lf9e-saved-list');
      if (!list) return;
      list.replaceChildren();
      let drafts = [];
      try { drafts = JSON.parse(localStorage.getItem(draftKey) || '[]'); } catch (_) {}
      if (!Array.isArray(drafts) || !drafts.length) { list.textContent = 'No ideas saved in this browser.'; return; }
      drafts.forEach(function (idea, i) {
        const row = document.createElement('div');
        row.className = 'lf9e-saved-row';
        const text = document.createElement('span');
        text.textContent = idea.name || 'Untitled';
        const use = document.createElement('button');
        use.type = 'button'; use.textContent = 'LOAD'; use.className = 'lf9e-secondary';
        use.addEventListener('click', function () {
          const form = Array.from(root.querySelectorAll('form[data-lf9e-entry]')).find(f =>
            f.elements.namedItem('category_id').value === idea.category_id);
          if (!form) { window.alert('That category is not currently available.'); return; }
          ['name','team','location','instagram','reason'].forEach(field => {
            form.elements.namedItem(field).value = idea[field] || '';
          });
          go(form.closest('[data-screen]').dataset.screen);
          drafts.splice(i, 1);
          try { localStorage.setItem(draftKey, JSON.stringify(drafts)); } catch (_) {}
          loadDrafts();
        });
        const remove = document.createElement('button');
        remove.type = 'button'; remove.textContent = 'REMOVE'; remove.className = 'lf9e-secondary';
        remove.addEventListener('click', function () {
          drafts.splice(i, 1);
          try { localStorage.setItem(draftKey, JSON.stringify(drafts)); } catch (_) {}
          loadDrafts();
        });
        row.append(text, use, remove); list.append(row);
      });
    }
    loadDrafts();
    root.querySelectorAll('[data-add-later]').forEach(function(btn) {
      btn.addEventListener('click', function () {
        const form = btn.closest('form');
        const name = form.elements.namedItem('name');
        if (!name.value.trim()) { name.focus(); return; }
        const category = form.elements.namedItem('category_id').value;
        const idea = {category_id: category, name: name.value.trim(),
                      team: form.elements.namedItem('team').value.trim(),
                      location: form.elements.namedItem('location').value.trim(),
                      instagram: form.elements.namedItem('instagram').value.trim(),
                      reason: form.elements.namedItem('reason').value.trim()};
        let previous = [];
        try { previous = JSON.parse(localStorage.getItem(draftKey) || '[]'); } catch (_) {}
        if (!Array.isArray(previous)) previous = [];
        previous.push(idea);
        try { localStorage.setItem(draftKey, JSON.stringify(previous.slice(-30))); }
        catch (_) { window.alert('Browser storage unavailable; idea was not saved.'); return; }
        loadDrafts();
        window.alert('Saved locally for a future day. This did NOT submit a nomination.');
        ['name','team','location','instagram','reason'].forEach(field => { form.elements.namedItem(field).value = ''; });
      });
    });
  });
})();
