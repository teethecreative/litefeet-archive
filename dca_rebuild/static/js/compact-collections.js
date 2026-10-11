/* LiteFeet Vault — compact collection navigator; no remote dependencies. */
(function () {
  "use strict";
  function setup(section) {
    var selector = section.getAttribute("data-lf-compact");
    var rows = Array.prototype.slice.call(section.querySelectorAll(selector));
    if (rows.length <= 15) return;
    var size = 15, page = 1, query = "";
    var tools = document.createElement("div");
    tools.className = "lf-compact-tools";
    var search = document.createElement("input");
    search.type = "search"; search.placeholder = "Search this section";
    search.setAttribute("aria-label", "Search this section");
    var previous = document.createElement("button"); previous.type = "button";
    previous.textContent = "← Previous";
    var next = document.createElement("button"); next.type = "button";
    next.textContent = "Next →";
    var count = document.createElement("span"); count.setAttribute("aria-live", "polite");
    tools.appendChild(search); tools.appendChild(previous);
    tools.appendChild(count); tools.appendChild(next);
    section.insertBefore(tools, section.firstChild);
    function render() {
      var matched = rows.filter(function (row) {
        return row.textContent.toLocaleLowerCase().indexOf(query) !== -1;
      });
      var pages = Math.max(1, Math.ceil(matched.length / size));
      page = Math.max(1, Math.min(page, pages));
      rows.forEach(function (row) { row.hidden = true; row.style.setProperty("display", "none", "important"); });
      matched.slice((page-1)*size, page*size).forEach(function (row) {
        row.hidden = false; row.style.removeProperty("display");
      });
      previous.disabled = page <= 1; next.disabled = page >= pages;
      count.textContent = matched.length + " results · " + page + " / " + pages;
    }
    search.addEventListener("input", function () { query = search.value.trim().toLocaleLowerCase(); page = 1; render(); });
    previous.addEventListener("click", function () { page -= 1; render(); });
    next.addEventListener("click", function () { page += 1; render(); });
    render();
  }
  function boot() {
    document.querySelectorAll("[data-lf-compact]").forEach(setup);
  }
  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", boot);
  else boot();
})();
