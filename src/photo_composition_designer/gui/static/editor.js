/* Editor interactions: drag-and-drop assignment, replacement and swapping.
 *
 * The server confirms every mutation; the browser only initiates requests and
 * swaps the returned fragment. Every drag-and-drop action has a keyboard
 * alternative in the slot itself: assign and replace selects, the remove
 * button and the move-to-slot select.
 */
(function () {
  "use strict";

  const scrollKey = "pcd-project-scroll";
  document.addEventListener("click", function (event) {
    if (!event.target.closest(".page-thumb")) return;
    const sidebar = document.querySelector(".editor-sidebar");
    sessionStorage.setItem(
      scrollKey,
      JSON.stringify({
        pageY: window.scrollY,
        sidebarY: sidebar ? sidebar.scrollTop : 0,
      })
    );
  });

  window.addEventListener("pageshow", function () {
    const saved = sessionStorage.getItem(scrollKey);
    if (!saved) return;
    sessionStorage.removeItem(scrollKey);
    const position = JSON.parse(saved);
    window.scrollTo(0, position.pageY);
    const sidebar = document.querySelector(".editor-sidebar");
    if (sidebar) sidebar.scrollTop = position.sidebarY;
  });

  if (!document.querySelector(".editor-canvas")) return;

  const SOURCE_SLOT_TYPE = "application/x-pcd-slot";

  document.addEventListener("dragstart", function (event) {
    const item = event.target.closest(".unused-item, .slot img");
    if (!item) return;
    const slot = item.closest(".slot");
    event.dataTransfer.setData("text/plain", item.dataset.photoId || "");
    if (slot) {
      event.dataTransfer.setData(SOURCE_SLOT_TYPE, slot.dataset.slotId || "");
    } else {
      event.dataTransfer.setData(SOURCE_SLOT_TYPE, "");
    }
    event.dataTransfer.effectAllowed = "copyMove";
  });

  document.addEventListener("dragover", function (event) {
    const slot = event.target.closest(".slot");
    if (!slot) return;
    event.preventDefault();
    slot.classList.add("drag-over");
  });

  document.addEventListener("dragleave", function (event) {
    const slot = event.target.closest(".slot");
    if (slot) slot.classList.remove("drag-over");
  });

  document.addEventListener("drop", function (event) {
    const slot = event.target.closest(".slot");
    if (!slot) return;
    event.preventDefault();
    slot.classList.remove("drag-over");

    const photoId = event.dataTransfer.getData("text/plain");
    const sourceSlotId = event.dataTransfer.getData(SOURCE_SLOT_TYPE);
    if (!photoId) return;

    const canvas = document.querySelector(".editor-canvas");
    if (!canvas) return;
    const base = `/projects/${canvas.dataset.projectId}/pages/${canvas.dataset.pageId}`;

    /* A photo dragged from another slot moves or swaps instead of replacing
     * itself with a copy. Dropping onto its own slot is a no-op. */
    if (sourceSlotId) {
      if (sourceSlotId === slot.dataset.slotId) return;
      window.htmx.ajax("POST", `${base}/swap`, {
        values: { slot_a: sourceSlotId, slot_b: slot.dataset.slotId },
        target: canvas,
        swap: "outerHTML",
      });
      return;
    }

    const action = slot.classList.contains("occupied") ? "replace" : "assign";
    window.htmx.ajax("POST", `${base}/${action}`, {
      values: { slot_id: slot.dataset.slotId, photo_id: photoId },
      target: canvas,
      swap: "outerHTML",
    });
  });
})();
