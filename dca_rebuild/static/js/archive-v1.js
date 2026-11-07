/* The LiteFeet Vault — accessible, progressive Archive browsing.
   Only requested pages are fetched; search includes all public catalog records.
   All dynamic text is inserted via textContent, never HTML. */
(() => {
  "use strict";
  const browser = document.querySelector("[data-archive-browser]");
  if (browser && typeof window.fetch === "function") {
    const form = browser.querySelector("[data-archive-filter]");
    const list = browser.querySelector("[data-archive-list]");
    const button = browser.querySelector("[data-archive-load]");
    const state = browser.querySelector("[data-archive-state]");
    const count = browser.querySelector("[data-archive-count]");
    const empty = browser.querySelector("[data-archive-empty]");
    const timeline = browser.getAttribute("data-timeline") === "1";
    const urlParams = new URLSearchParams(window.location.search);
    let lastPage = Math.max(1, Number(urlParams.get("page") || 1) || 1);
    let hasMore = !button.hidden;
    let busy = false;
    let observer = null;

    function itemNode(item) {
      const row = document.createElement("article");
      row.className = "lfv-archive-entry";
      row.setAttribute("role", "listitem");
      const body = document.createElement("div");
      body.className = "lfv-archive-entry-main";
      const meta = document.createElement("p");
      meta.className = "lfv-archive-row-meta";
      const date = document.createElement("time");
      date.className = "lfv-archive-entry-date";
      date.textContent = item.date ? item.date.slice(0, 4) : "RESEARCH";
      if (item.date) date.dateTime = item.date;
      const divider = document.createElement("span");
      divider.textContent = "/";
      divider.setAttribute("aria-hidden", "true");
      const category = document.createElement("span");
      category.className = "lfv-archive-entry-type";
      category.textContent = item.collection.toUpperCase();
      meta.append(date, divider, category);
      const h = document.createElement("h3");
      const name = document.createElement("a");
      const dest = "/archive/records/" + encodeURIComponent(item.slug);
      name.href = dest;
      name.textContent = item.title;
      h.appendChild(name);
      const description = document.createElement("p");
      description.textContent = item.summary;
      body.append(meta, h, description);
      const link = document.createElement("a");
      link.className = "lfv-archive-open";
      link.href = dest;
      link.textContent = "→";
      link.setAttribute("aria-label", "View " + item.title);
      row.append(body, link);
      return row;
    }

    function criteria() {
      const formData = new FormData(form);
      return {
        q: String(formData.get("q") || "").trim().slice(0, 120),
        collection: timeline ? "all" : String(formData.get("collection") || "all")
      };
    }

    async function load(page, replace) {
      if (busy || (!hasMore && !replace)) return;
      busy = true;
      button.disabled = true;
      state.textContent = "Loading more records…";
      const current = criteria();
      const params = new URLSearchParams({
        page: String(page),
        q: current.q,
        collection: current.collection,
        timeline: timeline ? "1" : "0"
      });
      try {
        const response = await fetch("/archive/api/records?" + params.toString(), {
          credentials: "same-origin", headers: {Accept: "application/json"}
        });
        if (!response.ok) throw new Error("Archive request failed");
        const payload = await response.json();
        if (replace) list.replaceChildren();
        const fragment = document.createDocumentFragment();
        for (const item of payload.records) fragment.appendChild(itemNode(item));
        list.appendChild(fragment);
        lastPage = payload.page;
        hasMore = Boolean(payload.has_more);
        button.hidden = !hasMore;
        empty.hidden = payload.total !== 0;
        count.textContent = String(payload.total) + (payload.total === 1 ? " entry" : " entries");
        state.textContent = hasMore ? "SCROLL FOR MORE" : "ALL RECORDS LOADED";
        if (replace) {
          const dest = new URL(window.location.href);
          dest.searchParams.delete("page");
          current.q ? dest.searchParams.set("q", current.q) : dest.searchParams.delete("q");
          if (timeline) dest.searchParams.delete("collection");
          else current.collection !== "all" ? dest.searchParams.set("collection", current.collection) : dest.searchParams.delete("collection");
          window.history.replaceState({}, "", dest.toString());
        }
      } catch (_) {
        state.textContent = "Could not load more records. Try again.";
        button.hidden = false;
        hasMore = true;
      } finally {
        busy = false;
        button.disabled = false;
      }
    }

    button.addEventListener("click", () => load(lastPage + 1, false));
    form.addEventListener("submit", event => {
      event.preventDefault();
      hasMore = true;
      load(1, true);
    });
    if ("IntersectionObserver" in window) {
      observer = new IntersectionObserver(entries => {
        if (entries.some(entry => entry.isIntersecting) && hasMore && !busy) {
          load(lastPage + 1, false);
        }
      }, {rootMargin: "160px 0px", threshold: 0});
      observer.observe(button);
    }
  }

  document.querySelectorAll("[data-archive-verify]").forEach(form => {
    const radios = Array.from(form.querySelectorAll('input[name="choice"]'));
    const explain = form.querySelector("[data-archive-explain]");
    const textarea = form.querySelector('textarea[name="explanation"]');
    const submit = form.querySelector('button[type="submit"]');
    function sync() {
      const selected = radios.find(r => r.checked);
      const debatable = Boolean(selected && selected.value === "debatable");
      explain.hidden = !debatable;
      if (!debatable && textarea) textarea.value = "";
      submit.hidden = !selected;
    }
    radios.forEach(r => r.addEventListener("change", sync));
    sync();
  });
})();
