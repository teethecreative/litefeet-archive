(() => {
  "use strict";
  const dialog = document.getElementById("lfv-share-dialog");
  const opener = document.getElementById("lfv-share-open");
  if (!dialog || !opener || typeof dialog.showModal !== "function") return;

  const options = document.getElementById("lfv-page-options");
  const count = document.getElementById("lfv-page-count");
  const status = document.getElementById("lfv-share-status");
  const preview = document.getElementById("lfv-share-preview");
  const controls = dialog.querySelectorAll("[data-lfv-format]");
  const canonical = document.querySelector('link[rel="canonical"]');
  const pageLink = canonical && canonical.href ? canonical.href : location.origin + location.pathname;
  const page = document.querySelector("main") || document.querySelector('[role="main"]');
  const MAX_ITEMS = 6;
  const MAX_OPTIONS = 100;
  const EXCERPT_LIMIT = 170;
  const clean = (value) => (value || "").replace(/\s+/g, " ").trim();
  const title = clean(page?.querySelector("h1")?.textContent) || clean(document.title).replace(/\s*\|.*$/, "") || "The LiteFeet Vault";
  let fields = [];
  let selected = new Set();
  let format = "story";
  let theme = "light";
  let graphic = null;
  let renderId = 0;

  const visible = (element) => !!element && !element.closest("form, dialog, nav, footer, [hidden], [aria-hidden='true'], script, style") &&
    getComputedStyle(element).display !== "none" && getComputedStyle(element).visibility !== "hidden" &&
    !!element.getClientRects().length;
  const excerpt = (value, max = EXCERPT_LIMIT) => {
    const text = clean(value);
    if (text.length <= max) return text;
    const shortened = text.slice(0, max - 1).replace(/\s+\S*$/, "");
    return (shortened || text.slice(0, max - 1)) + "…";
  };
  const add = (label, value, type = "text", source = null) => {
    label = clean(label);
    value = clean(value);
    if (!label || !value || fields.length >= MAX_OPTIONS) return;
    const identity = label.toLowerCase() + "|" + value.toLowerCase();
    if (fields.some(item => item.identity === identity)) return;
    fields.push({id: "field-" + fields.length, label: excerpt(label, 75), value: excerpt(value), type, source, identity});
  };
  const addFacts = (root) => {
    root.querySelectorAll("dl").forEach(dl => {
      if (!visible(dl)) return;
      dl.querySelectorAll(":scope > div").forEach(div => {
        const dt = div.querySelector("dt"), dd = div.querySelector("dd");
        if (visible(dt) && visible(dd)) add(dt.textContent, dd.textContent);
      });
    });
  };
  const addSections = (root) => {
    root.querySelectorAll("section").forEach(section => {
      if (!visible(section) || section.closest("aside, .lfv-archive-verify")) return;
      const heading = section.querySelector("h2, h3");
      if (!visible(heading)) return;
      const paragraph = [...section.querySelectorAll("p")].find(el => visible(el) && clean(el.textContent).length > 18);
      if (paragraph) add(heading.textContent, paragraph.textContent);
    });
  };
  const addListings = (root) => {
    const lists = [
      ".lfv-archive-battles li",
      ".lfv-archive-notes li",
      ".lfv-archive-findings li",
      ".lfv-archive-entry h3",
      ".lfv-unified-item h3",
      ".lfv-calendar-full-event h4",
      ".lfv5-calendar-event h3",
      ".lfv-music-table tbody tr",
      ".lfv-music-track-list tbody tr",
      ".lfv-people-wordcloud a",
      ".lfv5-category-disclosure summary",
      ".lfv5-category-disclosure tbody tr",
      ".lf9e-suggestion-detail",
      ".lfv-about-block h3",
      ".dca23-results li",
      ".dca23-results h3"
    ];
    root.querySelectorAll(lists.join(",")).forEach(node => {
      if (!visible(node)) return;
      if (node.matches(".lfv-music-table tbody tr")) {
        const cells = node.querySelectorAll("td");
        if (cells.length >= 3) add("Music release: " + clean(cells[1].textContent), clean(cells[2].textContent) + " · " + clean(cells[0].textContent));
      } else if (node.matches(".lfv-music-track-list tbody tr")) {
        const cells = node.querySelectorAll("td");
        if (cells.length >= 2) add("Track: " + clean(cells[1].textContent), clean(cells[2]?.textContent) || "Listed on this release");
      } else if (node.matches(".lfv5-category-disclosure tbody tr")) {
        const cells = node.querySelectorAll("th, td");
        if (cells.length >= 2) add("Nominee: " + clean(cells[0].textContent), clean(cells[1].textContent) + " nominations");
      } else {
        const label = node.closest(".lfv-archive-battles") ? "Advertised battle (result unconfirmed)" :
          node.closest(".lfv-archive-notes") ? "Event highlight" :
          node.closest(".lfv-archive-findings") ? "Sourced finding" :
          node.closest(".lfv-people-wordcloud") ? "Profile" :
          node.closest(".lfv-calendar-full-event, .lfv5-calendar-event") ? "Listed event" :
          node.closest(".lfv-archive-entry, .lfv-unified-item") ? "Archive entry" :
          node.closest(".lfv5-category-disclosure") ? "Award category" : "Page item";
        add(label, node.textContent);
      }
    });
  };
  const collect = () => {
    fields = [];
    if (!page) return;
    const subtitle = [...page.querySelectorAll("header p, .lfv-about-page-body p, .lfv-event-recurrence")]
      .find(el => visible(el) && clean(el.textContent).length > 18);
    if (subtitle) add("Page introduction", subtitle.textContent);
    addFacts(page);
    addSections(page);
    addListings(page);
    // Other visible text details, such as source status, are optional.
    page.querySelectorAll("main > p, .lfv-archive-record-hero .lfv-archive-tags, .lfv-calendar-detail-note, .lfv-event-recurrence, .lfv-music-record > p").forEach(el => {
      if (visible(el) && clean(el.textContent).length > 8) add("Additional page detail", el.textContent);
    });
    // Offer only a real image shown in this page's main content. No placeholder artwork.
    const image = [...page.querySelectorAll("img")].find(el => visible(el) &&
      el.complete && el.naturalWidth > 100 && el.naturalHeight > 100 &&
      !!el.currentSrc && new URL(el.currentSrc, location.href).origin === location.origin);
    if (image) add("Photo / artwork", clean(image.alt) || "Image shown on this page", "image", image.currentSrc);

    // If the page has nothing else to select, make its actual heading available.
    if (!fields.length) add("Page heading", title);
    const defaults = fields.slice(0, Math.min(4, MAX_ITEMS)).map(f => f.id);
    selected = new Set(defaults);
    options.replaceChildren();
    fields.forEach(field => {
      const label = document.createElement("label");
      label.className = "lfv-page-option";
      const box = document.createElement("input");
      box.type = "checkbox";
      box.value = field.id;
      box.checked = selected.has(field.id);
      const body = document.createElement("span");
      const heading = document.createElement("strong");
      heading.textContent = field.label;
      const detail = document.createElement("small");
      detail.textContent = field.value;
      body.append(heading, detail);
      label.append(box, body);
      options.append(label);
      box.addEventListener("change", () => {
        if (box.checked && selected.size >= MAX_ITEMS) {
          box.checked = false;
          status.textContent = "Choose up to " + MAX_ITEMS + " details.";
          return;
        }
        if (box.checked) selected.add(field.id);
        else selected.delete(field.id);
        update();
      });
    });
    update();
  };

  const wrap = (ctx, text, maxWidth) => {
    const words = clean(text).split(" ");
    const lines = [];
    let line = "";
    for (const word of words) {
      if (!word) continue;
      if (ctx.measureText(word).width > maxWidth) {
        if (line) {lines.push(line); line = "";}
        let part = "";
        for (const ch of word) {
          if (ctx.measureText(part + ch).width > maxWidth && part) {
            lines.push(part); part = ch;
          } else part += ch;
        }
        line = part;
        continue;
      }
      const candidate = line ? line + " " + word : word;
      if (ctx.measureText(candidate).width > maxWidth && line) {
        lines.push(line); line = word;
      } else line = candidate;
    }
    if (line) lines.push(line);
    return lines;
  };
  const render = async () => {
    const id = ++renderId;
    if (!selected.size) {
      preview.hidden = true;
      if (graphic) URL.revokeObjectURL(graphic);
      graphic = null;
      return;
    }
    const width = 1080, height = format === "story" ? 1920 : 1350;
    const canvas = document.createElement("canvas");
    canvas.width = width; canvas.height = height;
    const ctx = canvas.getContext("2d");
    if (!ctx) throw Error("Image preview is unavailable in this browser");
    const dark = theme === "dark";
    const ink = dark ? "#f8f7f2" : "#071d3b";
    const muted = dark ? "#c6d2df" : "#40566e";
    ctx.fillStyle = dark ? "#071d3b" : "#f8f7f2";
    ctx.fillRect(0, 0, width, height);
    ctx.fillStyle = "#102f57"; ctx.fillRect(0, 0, width, 216);
    ctx.fillStyle = "#d9ac47"; ctx.fillRect(0, 210, width, 8);
    ctx.fillStyle = "#ffffff"; ctx.font = "bold 46px system-ui, sans-serif";
    ctx.fillText("THE LITEFEET VAULT", 72, 117);
    ctx.fillStyle = "#d9ac47"; ctx.font = "bold 26px system-ui, sans-serif";
    ctx.fillText("SHARED FROM THE VAULT", 74, 172);

    let y = 310;
    ctx.fillStyle = ink;
    ctx.font = "bold 64px system-ui, sans-serif";
    let headings = wrap(ctx, title, 930).slice(0, 3);
    for (const line of headings) {ctx.fillText(line, 74, y); y += 78;}
    y += 25;
    ctx.fillStyle = "#d9ac47"; ctx.fillRect(76, y, 900, 6);
    y += 74;
    const picked = fields.filter(f => selected.has(f.id));
    const contentBottom = height - 255;
    const contentSpace = Math.max(180, contentBottom - y);
    const perItem = Math.min(format === "story" ? 205 : 145, contentSpace / picked.length);
    for (const field of picked) {
      if (id !== renderId) return;
      const top = y;
      ctx.fillStyle = dark ? "#d9ac47" : "#143f80";
      ctx.font = "bold 24px system-ui, sans-serif";
      ctx.fillText(field.label.toUpperCase().slice(0, 49), 76, y);
      y += 42;
      if (field.type === "image" && field.source && perItem > 100) {
        try {
          const loaded = await new Promise((resolve, reject) => {
            const img = new Image();
            img.onload = () => resolve(img);
            img.onerror = reject;
            img.src = field.source;
          });
          if (id !== renderId) return;
          const targetHeight = perItem - 52;
          const scale = Math.min(850 / loaded.naturalWidth, targetHeight / loaded.naturalHeight);
          ctx.drawImage(loaded, 76, y, loaded.naturalWidth * scale, loaded.naturalHeight * scale);
          y += targetHeight;
        } catch { y += 8; }
      } else {
        ctx.fillStyle = ink;
        ctx.font = (perItem < 145 ? "29px" : "34px") + " system-ui, sans-serif";
        const maxLines = Math.max(1, Math.min(3, Math.floor((perItem - 50) / 42)));
        const lines = wrap(ctx, field.value, 915).slice(0, maxLines);
        for (const line of lines) {ctx.fillText(line, 77, y); y += 42;}
      }
      y = Math.min(contentBottom, top + perItem);
    }
    ctx.fillStyle = "#102f57"; ctx.fillRect(0, height - 215, width, 215);
    ctx.fillStyle = "#d9ac47"; ctx.fillRect(0, height - 215, width, 6);
    ctx.fillStyle = "#ffffff"; ctx.font = "bold 35px system-ui, sans-serif";
    ctx.fillText("EXPLORE THE CULTURE", 76, height - 130);
    ctx.fillStyle = "#d9ac47"; ctx.font = "29px system-ui, sans-serif";
    ctx.fillText("THELITEFEETVAULT.COM", 76, height - 67);

    const blob = await new Promise(resolve => canvas.toBlob(resolve, "image/png"));
    if (id !== renderId || !blob) return;
    const url = URL.createObjectURL(blob);
    if (graphic) URL.revokeObjectURL(graphic);
    graphic = url;
    preview.src = url;
    preview.hidden = false;
  };
  const update = () => {
    count.textContent = selected.size + " selected";
    status.textContent = selected.size ? "" : "Select at least one detail to create a graphic.";
    dialog.querySelector("#lfv-share-image").disabled = !selected.size;
    dialog.querySelector("#lfv-save-image").disabled = !selected.size;
    render().catch(() => { status.textContent = "Could not generate a graphic from these details."; });
  };
  const imageFile = async () => {
    if (!graphic) throw Error("Choose details to generate a graphic first.");
    const response = await fetch(graphic);
    if (!response.ok) throw Error("The graphic is unavailable.");
    return new File([await response.blob()], "litefeet-page-" + format + ".png", {type: "image/png"});
  };

  controls.forEach(button => button.addEventListener("click", () => {
    format = button.dataset.lfvFormat;
    controls.forEach(item => item.setAttribute("aria-pressed", String(item === button)));
    update();
  }));
  dialog.querySelectorAll('input[name="lfv-share-theme"]').forEach(input => {
    input.addEventListener("change", () => {theme = input.value; update();});
  });
  opener.addEventListener("click", () => { dialog.showModal(); collect(); });
  document.getElementById("lfv-share-close").addEventListener("click", () => dialog.close());
  dialog.addEventListener("click", event => { if (event.target === dialog) dialog.close(); });
  dialog.addEventListener("close", () => {
    renderId += 1;
    if (graphic) URL.revokeObjectURL(graphic);
    graphic = null;
    preview.removeAttribute("src");
  });
  document.getElementById("lfv-copy-link").addEventListener("click", async () => {
    try {await navigator.clipboard.writeText(pageLink); status.textContent = "Page link copied.";}
    catch {status.textContent = "Copy this link: " + pageLink;}
  });
  document.getElementById("lfv-save-image").addEventListener("click", async () => {
    try {
      const file = await imageFile();
      const link = document.createElement("a");
      link.href = URL.createObjectURL(file);
      link.download = file.name;
      document.body.append(link); link.click(); link.remove();
      setTimeout(() => URL.revokeObjectURL(link.href), 5000);
      status.textContent = "Your selected details are ready as an image.";
    } catch(error) {status.textContent = error.message || "Could not save the graphic.";}
  });
  document.getElementById("lfv-share-image").addEventListener("click", async () => {
    try {
      const file = await imageFile();
      if (navigator.share && navigator.canShare?.({files:[file]})) {
        await navigator.share({files:[file], title:title, text:"From The LiteFeet Vault"});
      } else {
        status.textContent = "Direct sharing is unavailable here. Save the graphic to share it.";
      }
    } catch(error) {if (error.name !== "AbortError") status.textContent = error.message || "Could not share the graphic.";}
  });
})();