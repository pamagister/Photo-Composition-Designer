/* Editor interactions: drag-and-drop assignment and keyboard alternatives.
 *
 * The server confirms every mutation; the browser only initiates requests and
 * swaps the returned fragment. Keyboard users use the select+button form that
 * is always present in empty slots, and the remove button on occupied slots.
 */
(function () {
  "use strict";

  const canvas = document.querySelector(".editor-canvas");
  if (!canvas) return;

  const projectId = canvas.dataset.projectId;
  const pageId = canvas.dataset.pageId;

  function refresh() {
    window.htmx.ajax("GET", `/projects/${projectId}/pages/${pageId}/unused`, {
      target: "#unused-area",
      swap: "innerHTML",
    });
  }

  document.addEventListener("dragstart", function (event) {
    const item = event.target.closest(".unused-item, .slot img");
    if (!item) return;
    event.dataTransfer.setData("text/plain", item.dataset.photoId || "");
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
    if (!photoId) return;

    const occupied = slot.classList.contains("occupied");
    const action = occupied ? "replace" : "assign";
    window.htmx.ajax("POST", `/projects/${projectId}/pages/${pageId}/${action}`, {
      values: { slot_id: slot.dataset.slotId, photo_id: photoId },
      target: canvas,
      swap: "outerHTML",
    }).then(refresh);
  });

  /* Keyboard: Enter on a focused empty slot opens the select dropdown. */
  document.addEventListener("keydown", function (event) {
    if (event.key !== "Enter") return;
    const slot = event.target.closest(".slot");
    if (!slot || slot.classList.contains("occupied")) return;
    const select = slot.querySelector("select");
    if (select) {
      event.preventDefault();
      select.focus();
    }
  });
})();