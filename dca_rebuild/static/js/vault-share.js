(() => {
  const dialog = document.getElementById("lfv-share-dialog");
  const open = document.getElementById("lfv-share-open");
  if (!dialog || !open || typeof dialog.showModal !== "function") return;
  const status = document.getElementById("lfv-share-status");
  const preview = document.getElementById("lfv-share-preview");
  const formats = Array.from(dialog.querySelectorAll("[data-lfv-format]"));
  const awardPanel = document.getElementById("lfv-awards-controls");
  const scope = document.getElementById("lfv-awards-scope");
  const category = document.getElementById("lfv-awards-category");
  const nominee = document.getElementById("lfv-awards-nominee");
  const pageHint = document.getElementById("lfv-share-pages");
  const reasonPanel = document.getElementById("lfv-nominee-reason-controls");
  const reasonChoice = document.getElementById("lfv-reason-choice");
  const customReason = document.getElementById("lfv-reason-custom");
  const customReasonLabel = document.getElementById("lfv-reason-custom-label");
  const canonical = document.querySelector('link[rel="canonical"]');
  const cleanLink = canonical?.href || location.origin + location.pathname;
  const currentPath = location.pathname;
  const awardPage = currentPath.startsWith("/awards/dancers-choice") || currentPath.startsWith("/awards/2026/") || currentPath === "/write-ins";
  const context = new URLSearchParams(location.search);
  let format = "story";
  let data = null;
  let previewRequest = 0;
  const regularCard = currentPath === "/" ? "home" : currentPath.replace(/^\/+|\/+$/g, "").replaceAll("/", "--");

  const settings = () => {
    const mode = dialog.querySelector('input[name="lfv-share-theme"]:checked')?.value || "light";
    const s = scope.value;
    const c = category.value;
    const n = nominee.value;
    const params = new URLSearchParams();
    if (s !== "awards") params.set("category", c);
    if (s === "nominee") {
      params.set("nominee", n);
      if (reasonChoice.value !== "none" && reasonChoice.value !== "custom") params.set("reason", reasonChoice.value);
    }
    return {mode, s, c, n, params};
  };
  const graphicUrl = () => {
    if (awardPage && data) {
      const {mode,s,params} = settings();
      return location.origin + "/social/awards/" + format + "/" + mode + "/" + s + ".png" + (params.size ? "?" + params : "");
    }
    return location.origin + "/social/instagram/" + format + "/" + encodeURIComponent(regularCard) + ".png";
  };
  const publicLink = () => {
    if (!awardPage || !data) return cleanLink;
    const {s,c,n} = settings();
    if (s === "awards") return location.origin + "/awards/dancers-choice/2026";
    const selected = data.categories.find(x => String(x.id) === c);
    const selectedNominee = selected?.nominees?.find(x => String(x.id) === n);
    if (s === "nominee" && selectedNominee?.href) return location.origin + selectedNominee.href;
    if (selected?.href) return location.origin + selected.href;
    const params = new URLSearchParams({view:"results",category:c});
    if (s === "nominee") params.set("suggestion",n);
    return location.origin + "/awards/dancers-choice/nominations?" + params;
  };
  const count = () => {
    if (!data || scope.value !== "nominees") return 1;
    const selected = data.categories.find(x => String(x.id) === category.value);
    const capacity = format === "story" ? 10 : 5;
    return Math.max(1, Math.ceil((selected?.nominees?.length || 0) / capacity));
  };
  const updatePreview = () => {
    const pages = count();
    if (awardPage && data) {
      pageHint.hidden = pages <= 1;
      pageHint.textContent = pages > 1 ? pages + " graphics will be generated to include all nominees." : "";
    }
    const ready = !awardPage || (data && (scope.value === "awards" || (category.value && (scope.value !== "nominee" || nominee.value))));
    preview.hidden = !ready;
    if (ready) {
      if (awardPage && data && scope.value === "nominee" && reasonChoice.value === "custom") {
        if (!customReason.value.trim()) {preview.hidden = true; status.textContent = "Enter a short reason to preview your graphic."; return;}
        const body = new FormData();
        body.set("category", category.value);
        body.set("nominee", nominee.value);
        body.set("reason_mode", "custom");
        body.set("reason_text", customReason.value);
        const requestId = ++previewRequest;
        fetch(graphicUrl(), {method:"POST",body}).then(async response => {
          if(!response.ok) throw Error("Could not generate the message graphic");
          return response.blob();
        }).then(blob => {
          if (requestId !== previewRequest) return;
          if (preview.dataset.objectUrl) URL.revokeObjectURL(preview.dataset.objectUrl);
          const objectUrl = URL.createObjectURL(blob);
          preview.dataset.objectUrl = objectUrl;
          preview.src = objectUrl;
          preview.hidden = false;
        }).catch(() => {status.textContent = "Could not preview that message.";});
      } else {previewRequest += 1;preview.src = graphicUrl();}
    } else {
      previewRequest += 1;
      preview.removeAttribute("src");
    }
    status.textContent = "";
  };
  const fill = (select, items, placeholder) => {
    select.replaceChildren();
    const empty = new Option(placeholder, "");
    select.add(empty);
    items.forEach(x => select.add(new Option(x.name, String(x.id))));
  };
  const updateSuggestedReasons = () => {
    const cat = data?.categories.find(x => String(x.id) === category.value);
    const selected = cat?.nominees?.find(x => String(x.id) === nominee.value);
    const previous = reasonChoice.value;
    reasonChoice.replaceChildren(new Option("No explanation", "none"));
    const suggestions = selected?.suggestions || [];
    if (suggestions.length) {
      const group = document.createElement("optgroup");
      group.label = "Previously verified explanations";
      suggestions.forEach(reason => group.append(new Option(reason.text, "verified-" + reason.id)));
      reasonChoice.append(group);
    }
    reasonChoice.add(new Option("Write my own explanation", "custom"));
    if ([...reasonChoice.options].some(x => x.value === previous)) reasonChoice.value = previous;
    else if (suggestions.length) reasonChoice.value = "verified-" + suggestions[0].id;
    else reasonChoice.value = "none";
    const showCustom = reasonChoice.value === "custom";
    customReason.hidden = customReasonLabel.hidden = !showCustom;
    const helper = reasonPanel.querySelector(".lfv-reason-helper");
    if (helper) helper.textContent = suggestions.length
      ? "Only previously verified explanations are listed. Your choice appears on the graphic, not as a new nomination."
      : "No verified explanation is available for this nominee yet. You can write your own for the graphic.";
  };
  const refresh = () => {
    const chosen = data?.categories?.find(x => String(x.id) === category.value);
    const needsCategory = scope.value !== "awards";
    const needsNominee = scope.value === "nominee";
    reasonPanel.hidden = !needsNominee;
    category.hidden = document.getElementById("lfv-awards-category-label").hidden = !needsCategory;
    nominee.hidden = document.getElementById("lfv-awards-nominee-label").hidden = !needsNominee;
    if (needsNominee) {
      const previous = nominee.value;
      fill(nominee, chosen?.nominees || [], chosen ? "Select nominee" : "Choose a category first");
      if ([...nominee.options].some(o => o.value === previous)) nominee.value = previous;
      else if (nominee.options.length > 1) nominee.selectedIndex = 1;
      updateSuggestedReasons();
    }
    updatePreview();
  };
  const getAwardOptions = async () => {
    if (!awardPage) return;
    awardPanel.hidden = false;
    const response = await fetch("/social/awards/options.json");
    if (!response.ok) throw Error("Couldn't retrieve public award categories");
    const payload = await response.json();
    if (!Array.isArray(payload.categories) || !payload.categories.length) throw Error("No published award categories are available yet.");
    data = payload;
    fill(category, data.categories, "Select category");
    const fromUrl = context.get("category");
    const cleanPreset = data.categories.find(x => x.href === currentPath ||
      x.nominees?.some(n => n.href === currentPath));
    const preset = cleanPreset || data.categories.find(x => String(x.id) === fromUrl);
    if (preset) category.value = String(preset.id);
    else if (category.options.length > 1) category.selectedIndex = 1;
    if (preset) {
      scope.value = context.get("suggestion") || preset.nominees?.some(n => n.href === currentPath)
        ? "nominee" : "category";
      if (context.get("share") === "nominees") scope.value = "nominees";
    }
    refresh();
    const fromNominee = preset?.nominees?.find(n => n.href === currentPath);
    const nomineeId = fromNominee ? String(fromNominee.id) : context.get("suggestion");
    if (nomineeId && scope.value === "nominee") {
      const found = [...nominee.options].find(x => x.value === nomineeId);
      if (found) nominee.value = found.value;
    }
    updatePreview();
  };

  scope.addEventListener("change", refresh);
  category.addEventListener("change", refresh);
  nominee.addEventListener("change", () => { updateSuggestedReasons(); updatePreview(); });
  const updateReason = () => {
    const isCustom = reasonChoice.value === "custom";
    customReason.hidden = customReasonLabel.hidden = !isCustom;
    updatePreview();
  };
  reasonChoice.addEventListener("change", updateReason);
  customReason.addEventListener("input", updatePreview);
  dialog.querySelectorAll('input[name="lfv-share-theme"]').forEach(x => x.addEventListener("change", updatePreview));
  formats.forEach(x => x.addEventListener("click", () => {
    format = x.dataset.lfvFormat;
    formats.forEach(b => b.setAttribute("aria-pressed", String(b === x)));
    updatePreview();
  }));
  open.addEventListener("click", async () => {
    dialog.showModal();
    try { if (awardPage && !data) await getAwardOptions(); }
    catch (error) { status.textContent = error.message || "Award options could not load. Please try again."; }
    if (!awardPage) updatePreview();
  });
  document.getElementById("lfv-share-close").addEventListener("click", () => dialog.close());
  dialog.addEventListener("click", e => { if (e.target === dialog) dialog.close(); });

  const files = async () => {
    if (awardPage && !data) throw Error("Award options are not loaded");
    if (awardPage && scope.value !== "awards" && !category.value) throw Error("Choose a category");
    if (awardPage && scope.value === "nominee" && !nominee.value) throw Error("Choose a nominee");
    const n = count();
    const output = [];
    for (let page = 1; page <= n; page++) {
      const url = new URL(graphicUrl());
      if (n > 1) url.searchParams.set("page", String(page));
      const isCustom = awardPage && data && scope.value === "nominee" && reasonChoice.value === "custom";
      const body = isCustom ? new FormData() : null;
      if (body) {
        body.set("category", category.value);
        body.set("nominee", nominee.value);
        body.set("reason_mode", "custom");
        body.set("reason_text", customReason.value);
      }
      const response = await fetch(url.href, isCustom ? {method:"POST",body} : {credentials:"omit"});
      if (!response.ok) throw Error("Could not generate this image");
      output.push(new File([await response.blob()], "litefeet-" + scope.value + "-" + format + "-" + page + ".png", {type:"image/png"}));
    }
    return output;
  };
  document.getElementById("lfv-share-image").addEventListener("click", async () => {
    try {
      const result = await files();
      if (navigator.share && navigator.canShare?.({files: result})) {
        await navigator.share({files:result});
      } else {
        status.textContent = "Direct image sharing isn't available here. Save the graphic and upload it to Instagram.";
      }
    } catch(e) { if (e.name !== "AbortError") status.textContent = e.message || "Unable to share this graphic."; }
  });
  document.getElementById("lfv-save-image").addEventListener("click", async () => {
    try {
      if (awardPage && data && count() > 1) {
        const {mode,s,params} = settings();
        const query = new URLSearchParams({format,theme:mode,scope:s,category:settings().c});
        const bundle = await fetch("/social/awards/bundle.zip?" + query);
        if (!bundle.ok) throw Error("Couldn't prepare all nominee graphics");
        const url = URL.createObjectURL(await bundle.blob());
        const anchor = document.createElement("a");
        anchor.href = url; anchor.download = "litefeet-awards-nominees.zip";
        document.body.append(anchor); anchor.click(); anchor.remove();
        setTimeout(() => URL.revokeObjectURL(url), 5000);
        status.textContent = "All nominee graphics are ready as a ZIP.";
        return;
      }
      const [file] = await files();
      const url = URL.createObjectURL(file);
      const anchor = document.createElement("a");
      anchor.href = url; anchor.download = file.name;
      document.body.append(anchor); anchor.click(); anchor.remove();
      setTimeout(() => URL.revokeObjectURL(url), 5000);
      status.textContent = "Graphic ready to post on Instagram.";
    } catch (e) { status.textContent = e.message || "Could not save graphic."; }
  });
  document.getElementById("lfv-copy-link").addEventListener("click", async () => {
    const url = publicLink();
    try { await navigator.clipboard.writeText(url); status.textContent = "Link copied."; }
    catch { status.textContent = "Copy this link: " + url; }
  });
})();
