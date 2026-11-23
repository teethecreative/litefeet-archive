/* The LiteFeet Vault — one theme state for public and admin views.
   Runs before page CSS when in head; fallback works with blocked storage. */
(function (window, document) {
  'use strict';
  if (window.LFVTheme) return;
  var KEY = 'litefeet-ledger-theme'; // Keep existing preferences compatible.
  function valid(value) { return value === 'dark' ? 'dark' : 'light'; }
  function current() { return valid(document.documentElement.dataset.theme); }
  function apply(value, persist) {
    var theme = valid(value);
    var root = document.documentElement;
    root.dataset.theme = theme;
    root.classList.toggle('dark', theme === 'dark');
    root.style.colorScheme = theme;
    if (persist) {
      try { window.localStorage.setItem(KEY, theme); } catch (_) {}
    }
    root.dispatchEvent(new CustomEvent('lfv:themechange', {detail: {theme: theme}}));
    return theme;
  }
  var saved;
  try { saved = window.localStorage.getItem(KEY); } catch (_) {}
  var initial = saved === 'light' || saved === 'dark'
    ? saved
    : (document.documentElement.dataset.theme === 'dark' ? 'dark' : 'light');
  apply(initial, false);
  window.LFVTheme = {
    get: current,
    set: function (theme) { return apply(theme, true); },
    apply: function (theme) { return apply(theme, false); }
  };
  window.addEventListener('storage', function (event) {
    if (event.key === KEY) apply(event.newValue, false);
  });
})(window, document);
