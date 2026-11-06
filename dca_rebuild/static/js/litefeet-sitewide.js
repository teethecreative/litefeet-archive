/* The LiteFeet Vault: progressive navigation; no page or business-rule rewrites. */
(function () {
  'use strict';
  function boot() {
    if (document.getElementById('lfv-sitewide-v1')) return;
    const original = document.querySelector('.awards-global-nav, .ledger-admin-nav');
    if (!original) return;
    let items;
    try { items = JSON.parse(document.getElementById('lfv-navigation-data').textContent); }
    catch (_) {
      // Older standalone templates retain their original navigation.
      return;
    }
    if (!Array.isArray(items) || !items.length) return;
    document.documentElement.classList.add('lfv-sitewide');
    const shell = document.createElement('div');
    shell.id = 'lfv-sitewide-v1'; shell.className = 'lfv-shell';
    shell.innerHTML = '<div class="lfv-shell-bar"><a class="lfv-shell-brand" href="/">THE LITEFEET <span>VAULT</span></a><div class="lfv-shell-actions"><button type="button" class="lfv-nav-button lfv-theme-button" aria-label="Toggle color theme"><span class="lfv-theme-label">THEME</span><span aria-hidden="true">◐</span></button><button type="button" class="lfv-nav-button lfv-menu-open" aria-label="Open site navigation" aria-controls="lfv-menu-panel" aria-expanded="false"><span class="lfv-hamburger" aria-hidden="true"><i></i><i></i><i></i></span></button></div></div>';
    const backdrop = document.createElement('div'); backdrop.className = 'lfv-menu-backdrop'; backdrop.hidden = true;
    const panel = document.createElement('aside');
    panel.id = 'lfv-menu-panel'; panel.className = 'lfv-menu-panel'; panel.hidden = true;
    panel.setAttribute('role', 'dialog'); panel.setAttribute('aria-modal', 'true'); panel.setAttribute('aria-label', 'Site navigation');
    panel.innerHTML = '<div class="lfv-menu-top"><span class="lfv-menu-title">EXPLORE THE VAULT</span><button type="button" class="lfv-menu-close" aria-label="Close navigation">×</button></div><nav class="lfv-menu-list" aria-label="Site navigation links"></nav>';
    document.body.prepend(shell); document.body.append(backdrop, panel);
    if (original.classList.contains('ledger-admin-nav')) original.setAttribute('data-lfv-admin-toolbar', '');
    else { original.hidden = true; original.style.setProperty('display', 'none', 'important'); }
    const openButton = shell.querySelector('.lfv-menu-open');
    const closeButton = panel.querySelector('.lfv-menu-close');
    const themeButton = shell.querySelector('.lfv-theme-button');
    const list = panel.querySelector('.lfv-menu-list');
    const title = panel.querySelector('.lfv-menu-title');
    let previousFocus, savedOverflow, opened = false;
    const inertBefore = new Map();
    function current(href) {
      const url = new URL(href, location.href);
      return url.pathname === location.pathname && url.search === location.search && (!url.hash || url.hash === location.hash);
    }
    function addLink(label, href) {
      const link = document.createElement('a'); link.textContent = label; link.href = href;
      if (current(href)) link.setAttribute('aria-current', 'page');
      list.append(link); return link;
    }
    function renderRoot(focusKey) {
      list.replaceChildren(); title.textContent = 'EXPLORE THE VAULT';
      items.forEach(function (item) {
        let control;
        if (item.children && item.children.length) {
          control = document.createElement('button'); control.type = 'button'; control.textContent = item.label;
          control.className = 'lfv-menu-section'; control.setAttribute('aria-haspopup', 'true');
          control.addEventListener('click', function () { renderSection(item); }); list.append(control);
        } else control = addLink(item.label, item.href);
        control.dataset.section = item.key;
        if (item.active) { control.dataset.active = 'true'; control.setAttribute('aria-label', item.label + ', current section'); }
        if (focusKey === item.key) control.focus();
      });
    }
    function renderSection(item) {
      list.replaceChildren(); title.textContent = item.label;
      const back = document.createElement('button'); back.type = 'button'; back.className = 'lfv-menu-back';
      back.textContent = 'Back'; back.setAttribute('aria-label', 'Back to main menu');
      back.addEventListener('click', function () { renderRoot(item.key); }); list.append(back);
      addLink(item.label + ' overview', item.href);
      item.children.forEach(child => addLink(child.label, child.href));
      back.focus();
    }
    function setOpen(next) {
      if (opened === next) return;
      opened = next;
      if (next) {
        previousFocus = document.activeElement; savedOverflow = document.body.style.overflow;
        renderRoot(); panel.hidden = backdrop.hidden = false;
        Array.from(document.body.children).forEach(function (node) {
          if (node !== panel && node !== backdrop) { inertBefore.set(node, node.inert); node.inert = true; }
        });
        document.body.style.overflow = 'hidden'; openButton.setAttribute('aria-expanded', 'true'); closeButton.focus();
      } else {
        panel.hidden = backdrop.hidden = true;
        inertBefore.forEach((value, node) => { node.inert = value; }); inertBefore.clear();
        document.body.style.overflow = savedOverflow; openButton.setAttribute('aria-expanded', 'false');
        if (previousFocus && previousFocus.isConnected) previousFocus.focus();
      }
    }
    openButton.addEventListener('click', () => setOpen(true)); closeButton.addEventListener('click', () => setOpen(false));
    backdrop.addEventListener('click', () => setOpen(false));
    panel.addEventListener('click', event => { if (event.target.closest('a')) setOpen(false); });
    document.addEventListener('keydown', function (event) {
      if (!opened) return;
      if (event.key === 'Escape') { event.preventDefault(); setOpen(false); }
      if (event.key === 'Tab') {
        const controls = Array.from(panel.querySelectorAll('a[href],button')).filter(node => node.getClientRects().length);
        const first = controls[0], last = controls[controls.length - 1];
        if (event.shiftKey && document.activeElement === first) { event.preventDefault(); last.focus(); }
        else if (!event.shiftKey && document.activeElement === last) { event.preventDefault(); first.focus(); }
      }
    });
    function applyTheme(theme) {
      document.documentElement.dataset.theme = theme;
      document.documentElement.classList.toggle('dark', theme === 'dark');
      themeButton.setAttribute('aria-label', 'Switch to ' + (theme === 'dark' ? 'light' : 'dark') + ' mode');
    }
    let saved = 'light'; try { saved = localStorage.getItem('litefeet-ledger-theme') || 'light'; } catch (_) {}
    applyTheme(saved === 'dark' ? 'dark' : 'light');
    themeButton.addEventListener('click', function () {
      const next = document.documentElement.dataset.theme === 'dark' ? 'light' : 'dark'; applyTheme(next);
      try { localStorage.setItem('litefeet-ledger-theme', next); } catch (_) {}
    });
  }
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', boot); else boot();
})();
