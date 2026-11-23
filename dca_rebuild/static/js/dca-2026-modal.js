/* 2026 Dancer's Choice: category modal and inline nominations.
   Uses existing verified session, CSRF token, name checks and server cooldowns. */
(function () {
  'use strict';
  document.addEventListener('DOMContentLoaded', function () {
    const root = document.querySelector('main#nominations.lf9e');
    let dialog = document.getElementById('lfv-dca-category-dialog');
    if (!root || !dialog) return;
    const draftKey = 'lf9e-future-nomination-ideas';
    const url = new URL(root.dataset.dcaGridUrl || window.location.pathname, window.location.origin);
    let activeCategory = null;
    let returnFocus = null;
    let pending = false;

    function drafts() {
      try { const value = JSON.parse(localStorage.getItem(draftKey) || '[]'); return Array.isArray(value) ? value : []; }
      catch (_) { return []; }
    }
    function showFeedback(message) {
      const feedback = dialog.querySelector('[data-dca-global-feedback]');
      if (!feedback) return;
      feedback.textContent = message;
      feedback.hidden = !message;
    }
    function formFor(panel) {
      return panel && panel.querySelector('[data-dca-nomination-form]');
    }
    function activePanel() {
      return dialog.querySelector('[data-dca-modal-category="' + activeCategory + '"]');
    }
    function resetForm(panel) {
      const wrap = panel.querySelector('[data-dca-form-wrap]');
      const form = formFor(panel);
      if (form) form.reset();
      if (wrap) wrap.hidden = true;
      const check = panel.querySelector('[data-dca-name-check]');
      const distinct = panel.querySelector('[data-dca-name-distinct]');
      if (check) check.hidden = true;
      if (distinct) distinct.hidden = true;
      setReasonRequired(panel, true);
    }
    function openCategory(id, focusTarget) {
      const panel = dialog.querySelector('[data-dca-modal-category="' + id + '"]');
      if (!panel) return;
      returnFocus = focusTarget || document.activeElement;
      activeCategory = String(id);
      dialog.querySelectorAll('[data-dca-modal-category]').forEach(item => {
        item.hidden = item !== panel;
        if (item !== panel) resetForm(item);
      });
      showFeedback('');
      resetForm(panel);
      if (!dialog.open) {
        if (typeof dialog.showModal === 'function') dialog.showModal();
        else dialog.setAttribute('open', '');
      }
      dialog.scrollTop = 0;
      const heading = panel.querySelector('h2');
      if (heading) { heading.setAttribute('tabindex', '-1'); heading.focus({preventScroll: true}); }
    }
    function closeDialog() {
      if (dialog.open && typeof dialog.close === 'function') dialog.close();
      else dialog.removeAttribute('open');
      if (returnFocus && returnFocus.isConnected) returnFocus.focus();
      activeCategory = null;
    }
    function displayForm(panel, existingName) {
      const wrap = panel.querySelector('[data-dca-form-wrap]');
      const form = formFor(panel);
      if (!wrap || !form) return;
      wrap.hidden = false;
      const title = wrap.querySelector('[data-dca-form-title]');
      if (title) title.textContent = existingName ? 'Nominate ' + existingName : 'Add a new nomination';
      const input = form.elements.namedItem('name');
      if (input) { input.value = existingName || ''; input.focus(); if (existingName) checkNominee(panel); }
    }
    function setReasonRequired(panel, isRequired) {
      const form = formFor(panel);
      if (!form) return;
      const reason = form.elements.namedItem('reason');
      const indicator = panel.querySelector('[data-dca-reason-label]');
      const help = panel.querySelector('[data-dca-reason-help]');
      if (reason) reason.required = isRequired;
      if (indicator) indicator.textContent = isRequired ? '(required for a new nominee)' : '(optional — reason already on file)';
      if (help) help.textContent = isRequired ?
        'An explanation is required unless this nominee already has one on file.' :
        'A reason is already on file. Additional information is optional.';
    }
    async function checkNominee(panel) {
      const form = formFor(panel);
      if (!form) return null;
      const input = form.elements.namedItem('name');
      const status = panel.querySelector('[data-dca-name-check]');
      const distinct = panel.querySelector('[data-dca-name-distinct]');
      const distinctInput = form.elements.namedItem('confirm_distinct');
      if (!input || input.value.trim().length < 2) {
        if (status) status.hidden = true;
        if (distinct) distinct.hidden = true;
        if (distinctInput) distinctInput.checked = false;
        setReasonRequired(panel, true);
        return null;
      }
      const nomineeName = input.value.trim();
      const checkUrl = new URL('/awards/dancers-choice/nominee-name-check', location.origin);
      checkUrl.searchParams.set('category_id', String(form.elements.namedItem('category_id').value));
      checkUrl.searchParams.set('name', nomineeName);
      try {
        const response = await fetch(checkUrl.href, {credentials: 'same-origin', headers: {'Accept': 'application/json'}, cache: 'no-store'});
        if (!response.ok) throw new Error('Unable to check nominee');
        const result = await response.json();
        if (input.value.trim() !== nomineeName || activeCategory !== panel.dataset.dcaModalCategory) return null;
        setReasonRequired(panel, result.reason_required !== false);
        if (result.already_listed) {
          status.textContent = 'Already nominated as ' + result.canonical_name + '. Your nomination will support the existing nominee.';
          status.hidden = false; distinct.hidden = true; distinctInput.checked = false;
        } else if (result.requires_confirmation) {
          const matches = (result.matches || []).filter(x => x.type === 'similar').map(x => x.name);
          status.textContent = 'Similar nominee listed: ' + matches.join(', ') + '. Confirm this is a different nominee if necessary.';
          status.hidden = false; distinct.hidden = false;
        } else {
          status.hidden = true; distinct.hidden = true; distinctInput.checked = false;
        }
        return result;
      } catch (_) {
        if (status) {status.textContent = 'Name check unavailable. Please try again.';status.hidden = false;}
        return null;
      }
    }
    async function refreshGrid() {
      const response = await fetch(url.href, {credentials:'same-origin',cache:'no-store',headers:{'Accept':'text/html'}});
      if (!response.ok) return false;
      const html = await response.text();
      const documentCopy = new DOMParser().parseFromString(html, 'text/html');
      const newGrid = documentCopy.querySelector('.lfv-dca-main .lf9e-category-grid');
      const oldGrid = root.querySelector('.lfv-dca-main .lf9e-category-grid');
      const newDialog = documentCopy.querySelector('#lfv-dca-category-dialog');
      if (!newGrid || !oldGrid || !newDialog) return false;
      oldGrid.replaceWith(newGrid);
      dialog.querySelector('.lfv-dca-dialog-shell').replaceWith(newDialog.querySelector('.lfv-dca-dialog-shell'));
      return true;
    }
    function renderDrafts() {
      const list = document.getElementById('lf9e-saved-list');
      if (!list) return;
      const items = drafts();
      list.replaceChildren();
      if (!items.length) {list.textContent = 'No saved ideas.'; return;}
      items.forEach((idea, index) => {
        const row = document.createElement('div'); row.className = 'lf9e-saved-row';
        const name = document.createElement('span'); name.textContent = idea.name || 'Untitled';
        const open = document.createElement('button'); open.type = 'button'; open.className = 'lf9e-secondary'; open.textContent = 'OPEN';
        open.addEventListener('click', () => {
          openCategory(idea.category_id, open);
          const panel = activePanel(); if (!panel) return;
          displayForm(panel, '');
          const form = formFor(panel);
          for (const field of ['name','team','location','instagram','reason']) {
            const input = form.elements.namedItem(field);
            if (input) input.value = idea[field] || '';
          }
          checkNominee(panel);
        });
        const remove = document.createElement('button'); remove.type='button'; remove.className='lf9e-secondary'; remove.textContent='REMOVE';
        remove.addEventListener('click', () => {
          const next = drafts(); next.splice(index, 1);
          try {localStorage.setItem(draftKey, JSON.stringify(next));renderDrafts();}
          catch (_) {list.textContent='Could not update saved ideas.';}
        });
        row.append(name, open, remove);list.appendChild(row);
      });
    }

    root.addEventListener('click', event => {
      const trigger = event.target.closest('[data-dca-open-category]');
      if (trigger && root.contains(trigger)) {
        event.preventDefault();
        openCategory(trigger.dataset.dcaOpenCategory, trigger);
      }
    });
    dialog.addEventListener('click', event => {
      if (event.target === dialog || event.target.closest('[data-dca-close]')) {
        closeDialog(); return;
      }
      const panel = activePanel(); if (!panel) return;
      const nominate = event.target.closest('[data-dca-select-nominee]');
      if (nominate) { displayForm(panel, nominate.dataset.dcaSelectNominee); return; }
      if (event.target.closest('[data-dca-add-new]')) {
        resetForm(panel); displayForm(panel, '');return;
      }
      if (event.target.closest('[data-dca-save-draft]')) {
        const form = formFor(panel);
        if (!form) return;
        const name = form.elements.namedItem('name').value.trim();
        if (!name) {form.elements.namedItem('name').focus();return;}
        const idea = {category_id:form.elements.namedItem('category_id').value};
        ['name','team','location','instagram','reason'].forEach(key => {
          const field = form.elements.namedItem(key); idea[key] = field ? field.value.trim() : '';
        });
        try {
          const all = drafts(); all.push(idea);
          localStorage.setItem(draftKey,JSON.stringify(all.slice(-30)));
          renderDrafts();showFeedback('Idea saved to this browser. It has not been submitted.');
        } catch (_) { showFeedback('Browser storage is unavailable. This idea was not saved.'); }
      }
    });
    dialog.addEventListener('input', event => {
      if (event.target.name !== 'name') return;
      const panel = event.target.closest('[data-dca-modal-category]');
      if (!panel) return;
      clearTimeout(panel._checkTimer);
      setReasonRequired(panel, true);
      const status = panel.querySelector('[data-dca-name-check]');
      const distinct = panel.querySelector('[data-dca-name-distinct]');
      if (status) status.hidden = true;
      if (distinct) distinct.hidden = true;
      const checkbox = formFor(panel).elements.namedItem('confirm_distinct');
      if (checkbox) checkbox.checked = false;
      panel._checkTimer = setTimeout(() => checkNominee(panel), 350);
    });
    dialog.addEventListener('focusout', event => {
      if (event.target.name === 'name') {
        const panel = event.target.closest('[data-dca-modal-category]');
        if (panel) { clearTimeout(panel._checkTimer);checkNominee(panel); }
      }
    });
    dialog.addEventListener('submit', async event => {
      const form = event.target.closest('[data-dca-nomination-form]');
      if (!form || pending) {event.preventDefault();return;}
      event.preventDefault();
      const panel = form.closest('[data-dca-modal-category]');
      clearTimeout(panel._checkTimer);
      const result = await checkNominee(panel);
      if (!result) {showFeedback('Check the nominee name and try again.');return;}
      const distinct = form.elements.namedItem('confirm_distinct');
      if (result.requires_confirmation && !distinct.checked) {
        showFeedback('Confirm whether this is a different nominee before submitting.');
        distinct.focus();return;
      }
      if (!form.reportValidity()) return;
      pending = true;
      const submit = form.querySelector('[type="submit"]');
      if (submit) submit.disabled = true;
      showFeedback('Submitting nomination…');
      try {
        const response = await fetch(form.action, {
          method:'POST', body:new FormData(form), credentials:'same-origin',
          redirect:'follow',headers:{'Accept':'application/json','X-DCA-Modal':'1'}
        });
        if (!response.ok) throw new Error('Nomination could not be submitted. Check your details and try again.');
        const data = await response.json();
        if (!data.success) {
          showFeedback(data.message || 'Nomination could not be submitted.'); return;
        }
        const selected = activeCategory;
        const refreshed = await refreshGrid();
        if (refreshed) {
          const updated = dialog.querySelector('[data-dca-modal-category="' + selected + '"]');
          if (updated) {
            dialog.querySelectorAll('[data-dca-modal-category]').forEach(x=>x.hidden = x!==updated);
          }
        }
        showFeedback(data.message || 'Nomination submitted!');
        const updatedPanel = activePanel();
        if (updatedPanel) {
          const wrap = updatedPanel.querySelector('[data-dca-form-wrap]');
          if (wrap) wrap.hidden = true;
        }
        renderDrafts();
      } catch (error) {
        showFeedback(error.message || 'Unable to submit nomination. Try again.');
      } finally {
        pending = false;
        if (submit && submit.isConnected) submit.disabled = false;
      }
    });
    dialog.addEventListener('close', () => {
      if (returnFocus && returnFocus.isConnected) returnFocus.focus();
      activeCategory = null;
    });
    dialog.addEventListener('cancel', event => {event.preventDefault();closeDialog();});
    renderDrafts();
  });
})();
