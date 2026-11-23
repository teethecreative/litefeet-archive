/* The entire Vault signs out authenticated visitors at local midnight.
   This is independent from the DCA rolling 24-hour nomination cooldown.
   The server performs the authoritative session-clear on the next request. */
(function () {
  'use strict';
  function timezone() {
    try { return Intl.DateTimeFormat().resolvedOptions().timeZone || 'UTC'; }
    catch (_) { return 'UTC'; }
  }
  function stampBrowserTimezone() {
    const secure = window.location.protocol === 'https:' ? '; Secure' : '';
    document.cookie = 'lfv_user_timezone=' + encodeURIComponent(timezone()) +
      '; Path=/; SameSite=Lax' + secure;
  }
  stampBrowserTimezone();
  const openedOn = new Date().toDateString();
  function checkMidnight() {
    if (new Date().toDateString() !== openedOn) {
      // Refresh causes the server to clear the site login immediately;
      // the visitor is no longer authenticated on this page.
      window.location.reload();
      return true;
    }
    return false;
  }
  function schedule() {
    if (checkMidnight()) return;
    const now = new Date();
    const midnight = new Date(now.getFullYear(), now.getMonth(), now.getDate() + 1);
    setTimeout(function () { if (!checkMidnight()) schedule(); },
      Math.max(1000, midnight.getTime() - now.getTime() + 200));
  }
  schedule();
  document.addEventListener('visibilitychange', function () {
    if (!document.hidden) checkMidnight();
  });
  window.addEventListener('pageshow', checkMidnight);
})();
