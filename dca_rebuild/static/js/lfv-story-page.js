/* One expandable story topic at a time; no auto-scroll or navigation. */
(function () {
  "use strict";
  const root = document.getElementById("vault-story");
  if (!root) return;
  const triggers = Array.from(root.querySelectorAll("[data-story-toggle]"));
  const panels = Array.from(root.querySelectorAll("[data-story-panel]"));
  if (!triggers.length || !panels.length) return;

  function showPanel(id) {
    triggers.forEach(function (trigger) {
      const active = trigger.getAttribute("aria-controls") === id;
      trigger.setAttribute("aria-expanded", active ? "true" : "false");
      const symbol = trigger.querySelector(".lfv-story-topic-symbol");
      if (symbol) symbol.textContent = active ? "−" : "+";
    });
    panels.forEach(function (panel) {
      panel.hidden = panel.id !== id;
    });
  }

  triggers.forEach(function (trigger) {
    trigger.addEventListener("click", function () {
      const id = trigger.getAttribute("aria-controls");
      const wasOpen = trigger.getAttribute("aria-expanded") === "true";
      if (!document.getElementById(id)) return;
      showPanel(wasOpen ? null : id);
    });
  });
}());
