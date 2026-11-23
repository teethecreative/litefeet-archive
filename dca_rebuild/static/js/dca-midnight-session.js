/* DCA email forms carry the visitor's IANA timezone when logging in.
   Automatic midnight logout is handled sitewide, independently of nomination
   cooldowns and records, by sitewide-midnight-logout.js. */
(function () {
  'use strict';
  function timezone() {
    try { return Intl.DateTimeFormat().resolvedOptions().timeZone || 'UTC'; }
    catch (_) { return 'UTC'; }
  }
  function setFields() {
    document.querySelectorAll('input[name="timezone"]').forEach(function (field) {
      field.value = timezone();
    });
  }
  document.addEventListener('DOMContentLoaded', function () {
    setFields();
    document.querySelectorAll('form').forEach(function (form) {
      if (form.querySelector('input[name="timezone"]')) {
        form.addEventListener('submit', setFields);
      }
    });
  });
})();
