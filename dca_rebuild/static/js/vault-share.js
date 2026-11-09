
(() => {
  const dialog = document.getElementById("lfv-share-dialog");
  const open = document.getElementById("lfv-share-open");
  if (!dialog || !open || typeof dialog.showModal !== "function") return;
  const close = document.getElementById("lfv-share-close");
  const preview = document.getElementById("lfv-share-preview");
  const status = document.getElementById("lfv-share-status");
  const formats = Array.from(dialog.querySelectorAll("[data-lfv-format]"));
  let format = "story";
  const canonical = document.querySelector('link[rel="canonical"]');
  const link = canonical?.href || location.origin + location.pathname;
  // The page already embeds a safe, query-free canonical. Never share email or admin tokens.
  const path = new URL(link).pathname;
  const card = path === "/" ? "home" : path.replace(/^\/+|\/+$/g, "").replaceAll("/", "--");
  const imageUrl = () => location.origin + "/social/instagram/" + format + "/" + encodeURIComponent(card) + ".png";
  const setFormat = next => {
    format = next;
    formats.forEach(button => button.setAttribute("aria-pressed", String(button.dataset.lfvFormat === next)));
    preview.src = imageUrl();
    status.textContent = "";
  };
  open.addEventListener("click", () => { setFormat("story"); dialog.showModal(); });
  close.addEventListener("click", () => dialog.close());
  dialog.addEventListener("click", event => { if (event.target === dialog) dialog.close(); });
  formats.forEach(button => button.addEventListener("click", () => setFormat(button.dataset.lfvFormat)));
  const imageFile = async () => {
    const response = await fetch(imageUrl(), {credentials:"omit"});
    if (!response.ok) throw Error("Could not generate the graphic");
    return new File([await response.blob()], "litefeet-vault-" + format + ".png", {type:"image/png"});
  };
  document.getElementById("lfv-share-image").addEventListener("click", async () => {
    status.textContent = "";
    try {
      const file = await imageFile();
      if (navigator.share && navigator.canShare?.({files:[file]})) {
        await navigator.share({files:[file]});
      } else {
        status.textContent = "Direct image sharing isn't available in this browser. Use Save image, then upload to Instagram.";
      }
    } catch (error) {
      if (error.name !== "AbortError") status.textContent = "Sharing wasn't available. You can save the graphic instead.";
    }
  });
  document.getElementById("lfv-save-image").addEventListener("click", async () => {
    try {
      const file = await imageFile();
      const objectUrl = URL.createObjectURL(file);
      const a = document.createElement("a");
      a.href = objectUrl;
      a.download = file.name;
      document.body.append(a); a.click(); a.remove();
      setTimeout(() => URL.revokeObjectURL(objectUrl), 2000);
      status.textContent = "Graphic ready. Open Instagram to post it.";
    } catch { status.textContent = "Couldn't save the graphic. Please try again."; }
  });
  document.getElementById("lfv-copy-link").addEventListener("click", async () => {
    try { await navigator.clipboard.writeText(link); status.textContent = "Page link copied."; }
    catch { status.textContent = "Copy this page link: " + link; }
  });
})();
