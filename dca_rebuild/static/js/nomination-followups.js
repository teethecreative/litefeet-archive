(() => {
  "use strict";
  const dismissedKey = "lfv-nomination-followup-dismissed-v1";
  try {
    if (sessionStorage.getItem(dismissedKey) === "yes") return;
  } catch (_) {
    // The reminder still works if browser storage is disabled.
  }
  fetch("/awards/dancers-choice/followup-status", {
    credentials: "same-origin",
    cache: "no-store",
    headers: { "Accept": "application/json" }
  }).then(response => {
    if (!response.ok) return null;
    return response.json();
  }).then(payload => {
    if (!payload || !Number.isSafeInteger(payload.needs_details) || payload.needs_details < 1) return;
    if (document.getElementById("lfv-nom-followup-dialog")) return;
    const dialog = document.createElement("dialog");
    dialog.id = "lfv-nom-followup-dialog";
    dialog.className = "lfv-nom-followup-dialog";
    dialog.setAttribute("aria-labelledby", "lfv-nom-followup-title");
    dialog.setAttribute("aria-describedby", "lfv-nom-followup-description");
    dialog.innerHTML = `
      <div class="lfv-nom-followup-dialog-inner">
        <button type="button" class="lfv-nom-followup-close" aria-label="Dismiss reminder">×</button>
        <p class="lfv-nom-followup-kicker">The LiteFeet Vault</p>
        <h2 id="lfv-nom-followup-title">Complete your nominations</h2>
        <p id="lfv-nom-followup-description">Some of your 2026 Dancer's Choice Awards nominations need a little more information before they can be reviewed. Your original nominations are saved.</p>
        <a class="lfv-nom-followup-action" href="/awards/dancers-choice/my-nomination-followups">Review my nominations</a>
        <button type="button" class="lfv-nom-followup-later">Not now</button>
      </div>`;
    document.body.appendChild(dialog);
    const dismiss = () => {
      try { sessionStorage.setItem(dismissedKey, "yes"); } catch (_) {}
      if (dialog.open) dialog.close();
      dialog.remove();
    };
    dialog.querySelector(".lfv-nom-followup-close").addEventListener("click", dismiss);
    dialog.querySelector(".lfv-nom-followup-later").addEventListener("click", dismiss);
    dialog.addEventListener("cancel", event => { event.preventDefault(); dismiss(); });
    if (typeof dialog.showModal === "function") dialog.showModal();
  }).catch(() => {
    // The rest of the website remains usable if the reminder cannot load.
  });
})();
