/* DCA verification belongs to one local calendar day, not a seven-day cookie.
   The server performs the authoritative expiry check on every request.
   This file sends the browser's IANA timezone at verification and refreshes
   open nomination pages immediately after the next local midnight. */
(function () {
  'use strict';
  function timezone() {
    try {
      return Intl.DateTimeFormat().resolvedOptions().timeZone || 'UTC';
    } catch (_) {
      return 'UTC';
    }
  }
  function setFields() {
    document.querySelectorAll('input[name="timezone"]').forEach(function (field) {
      field.value = timezone();
    });
  }
  let activeLocalDate = new Date().toDateString();
  function updateAfterMidnight() {
    const today = new Date().toDateString();
    if (today !== activeLocalDate) {
      window.location.reload();
      return true;
    }
    return false;
  }
  function scheduleNextMidnight() {
    if (updateAfterMidnight()) return;
    const now = new Date();
    const next = new Date(now.getFullYear(), now.getMonth(), now.getDate() + 1);
    const duration = Math.max(1000, next.getTime() - now.getTime() + 200);
    setTimeout(function () {
      if (!updateAfterMidnight()) scheduleNextMidnight();
    }, duration);
  }
  document.addEventListener('DOMContentLoaded', function () {
    setFields();
    document.querySelectorAll('form').forEach(function (form) {
      if (form.querySelector('input[name="timezone"]')) {
        form.addEventListener('submit', setFields);
      }
    });
    scheduleNextMidnight();
  });
  document.addEventListener('visibilitychange', function () {
    if (!document.hidden) updateAfterMidnight();
  });
  window.addEventListener('pageshow', updateAfterMidnight);
})();
