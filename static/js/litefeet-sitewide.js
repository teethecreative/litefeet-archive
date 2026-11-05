/* The LiteFeet Vault — shared, accessible navigation layer.
   Discovers existing route links from legacy navigation; does not invent routes. */
(function () {
  'use strict';
  var BOOT = 'lfv-sitewide-v1';
  function boot() {
    if (document.getElementById(BOOT) || !document.body) return;
    document.documentElement.classList.add('lfv-sitewide');
    var original = findOriginalNavigation();
    if (!original) {
      /* Fail open: never replace existing navigation when its structure is unknown. */
      return;
    }
    var links = collectLinks(original);
    if (!links.length) return;
    var first = document.body.firstChild;
    var wrapper = document.createElement('div');
    wrapper.id = BOOT;
    wrapper.className = 'lfv-shell';
    wrapper.innerHTML = '<div class="lfv-shell-bar">' +
      '<a class="lfv-shell-brand" href="/">THE LITEFEET <span>VAULT</span></a>' +
      '<div class="lfv-shell-actions">' +
      '<button type="button" class="lfv-nav-button lfv-theme-button" aria-label="Toggle color theme"><span class="lfv-theme-label">THEME</span><span aria-hidden="true">◐</span></button>' +
      '<button type="button" class="lfv-nav-button lfv-menu-open" aria-controls="lfv-menu-panel" aria-expanded="false" aria-label="Open site navigation"><span class="lfv-hamburger" aria-hidden="true"><i></i><i></i><i></i></span></button>' +
      '</div></div>';
    var backdrop = document.createElement('div');
    backdrop.className = 'lfv-menu-backdrop';
    backdrop.hidden = true;
    var panel = document.createElement('aside');
    panel.id = 'lfv-menu-panel';
    panel.className = 'lfv-menu-panel';
    panel.setAttribute('role', 'dialog');
    panel.setAttribute('aria-modal', 'true');
    panel.setAttribute('aria-label', 'Site navigation');
    panel.hidden = true;
    panel.innerHTML = '<div class="lfv-menu-top"><span class="lfv-menu-title">' +
      (location.pathname.indexOf('/admin') === 0 ? 'ADMIN CONTROL ROOM' : 'EXPLORE THE VAULT') +
      '</span><button type="button" class="lfv-menu-close" aria-label="Close navigation">×</button></div>' +
      '<nav class="lfv-menu-list" aria-label="Site navigation links"></nav>';
    var list = panel.querySelector('.lfv-menu-list');
    links.forEach(function (link) {
      var a = document.createElement('a');
      a.href = link.href;
      a.textContent = link.label;
      if (new URL(a.href, location.href).pathname === location.pathname) a.setAttribute('aria-current', 'page');
      list.appendChild(a);
    });
    document.body.insertBefore(wrapper, first);
    document.body.appendChild(backdrop);
    document.body.appendChild(panel);
    document.documentElement.classList.add('lfv-sitewide');
    // Only after successful construction, hide the legacy navigation container.
    original.setAttribute('data-lfv-original-navigation', '');
    original.hidden = true;
    original.style.setProperty('display', 'none', 'important');
    // Existing theme toggle can still run globally; avoid a second floating control.
    document.querySelectorAll('.theme-toggle').forEach(function (node) {
      if (!wrapper.contains(node)) node.setAttribute('data-lfv-legacy-toggle', '');
    });
    var openButton = wrapper.querySelector('.lfv-menu-open');
    var closeButton = panel.querySelector('.lfv-menu-close');
    var themeButton = wrapper.querySelector('.lfv-theme-button');
    var previousFocus = null;
    var savedOverflow = '';
    function setOpen(isOpen) {
      if (isOpen) {
        previousFocus = document.activeElement;
        savedOverflow = document.body.style.overflow;
        panel.hidden = false;
        backdrop.hidden = false;
        document.body.style.overflow = 'hidden';
        openButton.setAttribute('aria-expanded', 'true');
        closeButton.focus();
      } else {
        panel.hidden = true;
        backdrop.hidden = true;
        document.body.style.overflow = savedOverflow;
        openButton.setAttribute('aria-expanded', 'false');
        if (previousFocus && typeof previousFocus.focus === 'function') previousFocus.focus();
      }
    }
    openButton.addEventListener('click', function () { setOpen(true); });
    closeButton.addEventListener('click', function () { setOpen(false); });
    backdrop.addEventListener('click', function () { setOpen(false); });
    panel.addEventListener('click', function (event) {
      if (event.target.closest('a')) setOpen(false);
    });
    document.addEventListener('keydown', function (event) {
      if (panel.hidden) return;
      if (event.key === 'Escape') { event.preventDefault(); setOpen(false); return; }
      if (event.key === 'Tab') {
        var tabbable = Array.from(panel.querySelectorAll('a[href],button:not([disabled])'));
        if (!tabbable.length) return;
        var firstEl = tabbable[0], lastEl = tabbable[tabbable.length - 1];
        if (event.shiftKey && document.activeElement === firstEl) { event.preventDefault(); lastEl.focus(); }
        else if (!event.shiftKey && document.activeElement === lastEl) { event.preventDefault(); firstEl.focus(); }
      }
    });
    function dark() {
      return document.documentElement.dataset.theme === 'dark' || document.documentElement.classList.contains('dark');
    }
    function themeLabel() { themeButton.setAttribute('aria-label', 'Switch to ' + (dark() ? 'light' : 'dark') + ' mode'); }
    themeButton.addEventListener('click', function () {
      var next = dark() ? 'light' : 'dark';
      try { if (typeof window.setTheme === 'function') window.setTheme(next); } catch (e) { /* use fallback */ }
      document.documentElement.dataset.theme = next;
      document.documentElement.classList.toggle('dark', next === 'dark');
      try { localStorage.setItem('litefeet-ledger-theme', next); } catch (e) { /* storage can be disabled */ }
      themeLabel();
    });
    try {
      var savedTheme = localStorage.getItem('litefeet-ledger-theme');
      if (savedTheme === 'light' || savedTheme === 'dark') document.documentElement.dataset.theme = savedTheme;
    } catch (_) { /* Theme remains usable without browser storage. */ }
    themeLabel();
  }
  function findOriginalNavigation() {
    var priority = [
      '.ledger-admin-nav', 'header.site-header', '.site-header',
      '#site-header', '.main-nav', '.site-nav', '#site-nav',
      'nav[aria-label="Main navigation"]', 'nav[aria-label="Primary navigation"]',
      'header nav', 'body > nav'
    ];
    for (var i = 0; i < priority.length; i++) {
      var node = document.querySelector(priority[i]);
      if (node && node.querySelector('a[href]') && !node.closest('.lfv-shell')) return node;
    }
    // A single nav outside the main content is a safe last resort.
    var candidates = Array.from(document.querySelectorAll('nav')).filter(function (node) {
      return !node.closest('main,footer,aside') && node.querySelectorAll('a[href]').length >= 2;
    });
    return candidates.length === 1 ? candidates[0] : null;
  }
  function collectLinks(node) {
    var result = [{href: location.origin + '/', label: 'Home'}];
    var seen = {'/': true};
    node.querySelectorAll('a[href]').forEach(function (anchor) {
      var href = anchor.getAttribute('href');
      if (!href || href.charAt(0) === '#' || href.indexOf('javascript:') === 0) return;
      var parsed;
      try { parsed = new URL(href, location.href); } catch (e) { return; }
      if (parsed.origin !== location.origin || !/^https?:$/.test(parsed.protocol)) return;
      var key = parsed.pathname + parsed.search + parsed.hash;
      if (seen[key] || parsed.pathname === '/awards/dancers-choice/nominations') return;
      var label = (anchor.getAttribute('aria-label') || anchor.textContent || '').replace(/\s+/g, ' ').trim();
      if (!label || label.length > 85) return;
      seen[key] = true;
      result.push({href: parsed.href, label: label});
    });
    return result;
  }
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', boot);
  else boot();
})();
