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

  /* Page thumbnails: ArrowUp/ArrowDown move to the previous/next page. The
   * handler stops propagation so the crop keyboard controls below do not also
   * consume the arrow keys while a thumbnail is focused. */
  const pageThumbs = Array.from(
    document.querySelectorAll(".editor-sidebar .page-thumb")
  );
  const sidebar = document.querySelector(".editor-sidebar");
  if (sidebar && pageThumbs.length > 1) {
    sidebar.addEventListener("keydown", function (event) {
      if (event.key !== "ArrowDown" && event.key !== "ArrowUp") return;
      const current = event.target.closest(".page-thumb");
      if (!current) return;
      event.preventDefault();
      event.stopPropagation();
      const currentIndex = pageThumbs.indexOf(current);
      if (currentIndex < 0) return;
      const nextIndex = currentIndex + (event.key === "ArrowDown" ? 1 : -1);
      if (nextIndex < 0 || nextIndex >= pageThumbs.length) return;
      const next = pageThumbs[nextIndex];
      next.focus();
      next.click();
    });
  }

  if (!document.querySelector(".editor-canvas")) return;

  const SOURCE_SLOT_TYPE = "application/x-pcd-slot";

  /* A drop target is either a right-hand slot card or a preview dropzone; both
   * expose data-slot-id and an occupied/empty state. */
  function dropTarget(element) {
    return element.closest(".slot, .slot-dropzone");
  }

  function isOccupied(target) {
    return target.classList.contains("occupied");
  }

  document.addEventListener("dragstart", function (event) {
    /* Dragging from an occupied preview dropzone behaves like dragging from an
     * occupied right-hand slot. */
    const dropzone = event.target.closest(".slot-dropzone.occupied");
    const item = event.target.closest(".unused-item, .slot img");
    const source = item || dropzone;
    if (!source) return;
    const slot = source.closest(".slot");
    event.dataTransfer.setData("text/plain", source.dataset.photoId || "");
    if (slot) {
      event.dataTransfer.setData(SOURCE_SLOT_TYPE, slot.dataset.slotId || "");
    } else if (dropzone) {
      event.dataTransfer.setData(SOURCE_SLOT_TYPE, dropzone.dataset.slotId || "");
    } else {
      event.dataTransfer.setData(SOURCE_SLOT_TYPE, "");
    }
    event.dataTransfer.effectAllowed = "copyMove";
    if (dropzone) dropzone.classList.add("dragging");
  });

  document.addEventListener("dragover", function (event) {
    const target = dropTarget(event.target);
    if (!target) return;
    event.preventDefault();
    target.classList.add("drag-over");
  });

  document.addEventListener("dragleave", function (event) {
    const target = dropTarget(event.target);
    if (target) target.classList.remove("drag-over");
  });

  document.addEventListener("drop", function (event) {
    const target = dropTarget(event.target);
    if (!target) return;
    event.preventDefault();
    target.classList.remove("drag-over");

    const photoId = event.dataTransfer.getData("text/plain");
    const sourceSlotId = event.dataTransfer.getData(SOURCE_SLOT_TYPE);
    if (!photoId) return;

    const canvas = document.querySelector(".editor-canvas");
    if (!canvas) return;
    const base = `/projects/${canvas.dataset.projectId}/pages/${canvas.dataset.pageId}`;

    /* A photo dragged from another slot (or occupied dropzone) moves or swaps
     * instead of replacing itself with a copy. Dropping onto its own slot is a
     * no-op. */
    if (sourceSlotId) {
      if (sourceSlotId === target.dataset.slotId) return;
      window.htmx.ajax("POST", `${base}/swap`, {
        values: { slot_a: sourceSlotId, slot_b: target.dataset.slotId },
        target: canvas,
        swap: "outerHTML",
      });
      return;
    }

    const selectedPhotos = Array.from(
      document.querySelectorAll(".unused-item-checkbox:checked")
    ).map((checkbox) => checkbox.value);
    if (selectedPhotos.includes(photoId) && selectedPhotos.length > 1) {
      const orderedPhotos = [
        photoId,
        ...selectedPhotos.filter((selectedId) => selectedId !== photoId),
      ];
      window.htmx.ajax("POST", `${base}/assign-selected`, {
        values: { slot_id: target.dataset.slotId, photo_id: orderedPhotos },
        target: canvas,
        swap: "outerHTML",
      });
      return;
    }

    const action = isOccupied(target) ? "replace" : "assign";
    window.htmx.ajax("POST", `${base}/${action}`, {
      values: { slot_id: target.dataset.slotId, photo_id: photoId },
      target: canvas,
      swap: "outerHTML",
    });
  });

  document.addEventListener("dragend", function (event) {
    const dropzone = event.target.closest(".slot-dropzone");
    if (dropzone) dropzone.classList.remove("dragging");
    document
      .querySelectorAll(".slot-dropzone.drag-over, .slot.drag-over")
      .forEach((node) => node.classList.remove("drag-over"));
  });

  /* Multi-select in the photo strip: track checked photos, keep the toolbar
   * count and button states in sync, and clear the selection after a bulk
   * assign. Every checkbox is keyboard accessible.
   *
   * The strip is replaced wholesale when it refreshes (pcd:refresh-unused), so
   * all wiring uses document-level event delegation and re-queries the toolbar
   * each time instead of capturing nodes at load time. */
  document.addEventListener("change", function (event) {
    if (!event.target.classList.contains("unused-item-checkbox")) return;
    syncSelection();
  });

  document.addEventListener("click", function (event) {
    if (event.target.closest(".clear-selection-btn")) {
      document
        .querySelectorAll(".unused-item-checkbox:checked")
        .forEach((box) => (box.checked = false));
      syncSelection();
    }
  });

  document.addEventListener("htmx:afterSwap", function (event) {
    if (event.target instanceof Element && event.target.closest(".photo-strip")) {
      syncSelection();
    }
  });

  function syncSelection() {
    const toolbar = document.querySelector(".photo-strip-header");
    if (!toolbar) return;
    const selected = document.querySelectorAll(".unused-item-checkbox:checked");
    const countLabel = toolbar.querySelector("[data-selection-count]");
    const assignBtn = toolbar.querySelector(".assign-selected-btn");
    const clearBtn = toolbar.querySelector(".clear-selection-btn");
    if (countLabel) countLabel.textContent = `${selected.length} selected`;
    if (assignBtn) assignBtn.disabled = selected.length === 0;
    if (clearBtn) clearBtn.disabled = selected.length === 0;
  }

  syncSelection();

  /* Slot selection is shared between a preview dropzone and its matching
   * right-hand slot, keyed by data-slot-id. Selecting is presentation only and
   * never triggers a server request. The crop keyboard handler (below) reads
   * the current selection. */
  let selectedSlotId = null;

  function slotNodes(slotId) {
    return document.querySelectorAll(
      `.slot[data-slot-id="${slotId}"], .slot-dropzone[data-slot-id="${slotId}"]`
    );
  }

  function clearSlotSelection() {
    document
      .querySelectorAll(".slot.selected, .slot-dropzone.selected")
      .forEach((node) => node.classList.remove("selected"));
  }

  function selectSlot(slotId, source) {
    const id = String(slotId);
    if (selectedSlotId === id) {
      clearSlotSelection();
      selectedSlotId = null;
      return;
    }
    clearSlotSelection();
    selectedSlotId = id;
    slotNodes(id).forEach((node) => node.classList.add("selected"));
    /* Scroll the right-hand slot into view without scrolling dropzones. */
    const panelSlot = document.querySelector(`.slot[data-slot-id="${id}"]`);
    if (panelSlot && source !== panelSlot) {
      panelSlot.scrollIntoView({ block: "nearest", behavior: "smooth" });
    }
  }

  document.addEventListener("click", function (event) {
    const dropzone = event.target.closest(".slot-dropzone");
    if (dropzone) {
      selectSlot(dropzone.dataset.slotId, dropzone);
      return;
    }
    /* Clicking a right-hand slot mirrors the highlight onto its dropzone. Guard
     * against clicks on interactive controls inside the slot card. */
    if (event.target.closest("button, select, input, textarea, summary, a")) return;
    const slot = event.target.closest(".slot");
    if (slot) selectSlot(slot.dataset.slotId, slot);
  });

  document.addEventListener("keydown", function (event) {
    const slot = event.target.closest(".slot, .slot-dropzone");
    if (
      slot &&
      (event.key === "Enter" || event.key === " ") &&
      !event.target.closest("button, select, input, textarea, summary, a")
    ) {
      event.preventDefault();
      selectSlot(slot.dataset.slotId, slot);
    }
  });

  /* Keep the shared selection consistent after a canvas swap replaces nodes. */
  document.addEventListener("htmx:afterSwap", function (event) {
    if (!(event.target instanceof Element)) return;
    if (!event.target.closest(".editor-canvas")) return;
    if (
      selectedSlotId &&
      document.querySelectorAll(`.slot-dropzone[data-slot-id="${selectedSlotId}"]`).length === 0
    ) {
      selectedSlotId = null;
      return;
    }
    if (selectedSlotId) {
      slotNodes(selectedSlotId).forEach((node) => node.classList.add("selected"));
    }
  });

  let retainedPreviews = null;

  function snapshotPreview(image) {
    if (!image || image.naturalWidth <= 1) return null;
    const snapshot = document.createElement("canvas");
    snapshot.width = image.naturalWidth;
    snapshot.height = image.naturalHeight;
    const context = snapshot.getContext("2d");
    if (!context) return null;
    try {
      context.drawImage(image, 0, 0);
      return snapshot.toDataURL("image/jpeg", 0.9);
    } catch (error) {
      console.warn("Could not retain the current page preview:", error);
      return null;
    }
  }

  document.addEventListener("htmx:beforeSwap", function (event) {
    const target = event.detail ? event.detail.target : null;
    if (!(target instanceof Element) || !target.matches(".editor-canvas")) return;
    const image = target.querySelector(".page-preview-image");
    const thumbnail = document.getElementById(
      `page-thumb-preview-${target.dataset.pageId}`
    );
    retainedPreviews = {
      projectId: target.dataset.projectId,
      pageId: target.dataset.pageId,
      revision: target.dataset.renderRevision,
      image: snapshotPreview(image),
      thumbnail: snapshotPreview(thumbnail),
    };
  });

  /* Keyboard crop: with an occupied slot selected, arrow keys nudge the focal
   * point and +/- nudge the zoom. Changes are debounced and sent to the live
   * crop endpoint; the preview image and sliders update in place so selection,
   * scroll and focus survive. Arrow keys inside form fields are ignored. */
  const PAN_STEP = 0.02;
  const ZOOM_STEP = 0.02;
  const ZOOM_MIN = 1.0;
  const ZOOM_MAX = 3.0;
  let cropTimer = null;
  let pendingCrop = null;
  let lastCropSlotId = null;

  function clamp(value, min, max) {
    return Math.min(max, Math.max(min, value));
  }

  function clampFocus(value) {
    return clamp(value, 0, 1);
  }

  function selectedCropInputs() {
    if (!selectedSlotId) return null;
    const slot = document.querySelector(`.slot[data-slot-id="${selectedSlotId}"]`);
    if (!slot) return null;
    const zoom = slot.querySelector('input[name="crop_zoom"]');
    const focusX = slot.querySelector('input[name="crop_focus_x"]');
    const focusY = slot.querySelector('input[name="crop_focus_y"]');
    if (!zoom || !focusX || !focusY) return null;
    return { slot, zoom, focusX, focusY };
  }

  function nudgeCrop(event) {
    const inputs = selectedCropInputs();
    if (!inputs) return;
    const key = event.key;
    let handled = true;
    let zoom = parseFloat(inputs.zoom.value);
    let focusX = parseFloat(inputs.focusX.value);
    let focusY = parseFloat(inputs.focusY.value);

    const sourceRatio = parseFloat(inputs.slot.dataset.cropSourceRatio);
    const targetRatio = parseFloat(inputs.slot.dataset.cropTargetRatio);
    const horizontalCrop = sourceRatio > targetRatio;
    const verticalCrop = sourceRatio < targetRatio;

    if (key === "ArrowLeft" && (zoom > ZOOM_MIN || horizontalCrop)) focusX -= PAN_STEP;
    else if (key === "ArrowRight" && (zoom > ZOOM_MIN || horizontalCrop)) focusX += PAN_STEP;
    else if (key === "ArrowUp" && (zoom > ZOOM_MIN || verticalCrop)) focusY -= PAN_STEP;
    else if (key === "ArrowDown" && (zoom > ZOOM_MIN || verticalCrop)) focusY += PAN_STEP;
    else if (key.startsWith("Arrow")) {
      event.preventDefault();
      return;
    }
    else if (key === "+" || key === "=" || event.code === "NumpadAdd") {
      zoom = clamp(zoom + ZOOM_STEP, ZOOM_MIN, ZOOM_MAX);
    } else if (key === "-" || key === "_" || event.code === "NumpadSubtract") {
      zoom = clamp(zoom - ZOOM_STEP, ZOOM_MIN, ZOOM_MAX);
    } else handled = false;

    if (!handled) return;
    event.preventDefault();

    focusX = clampFocus(focusX);
    focusY = clampFocus(focusY);
    inputs.zoom.value = zoom.toFixed(2);
    inputs.focusX.value = focusX.toFixed(2);
    inputs.focusY.value = focusY.toFixed(2);

    pendingCrop = {
      slot_id: selectedSlotId,
      crop_zoom: zoom,
      crop_focus_x: focusX,
      crop_focus_y: focusY,
    };
    if (cropTimer) window.clearTimeout(cropTimer);
    cropTimer = window.setTimeout(flushCrop, 120);
  }

  function flushCrop() {
    if (!pendingCrop) return;
    const canvas = document.querySelector(".editor-canvas");
    if (!canvas) {
      pendingCrop = null;
      return;
    }
    const values = pendingCrop;
    pendingCrop = null;
    lastCropSlotId = values.slot_id;
    const base = `/projects/${canvas.dataset.projectId}/pages/${canvas.dataset.pageId}`;
    window.htmx.ajax("POST", `${base}/crop/live`, {
      values: values,
    });
  }

  /* Used by the shutdown button to persist a debounced crop adjustment. */
  window.pcdFlushPending = flushCrop;

  document.addEventListener("keydown", function (event) {
    const field = event.target.closest("input, textarea, select, [contenteditable]");
    if (field) return;
    if (!selectedSlotId) return;
    nudgeCrop(event);
  });

  /* Refresh the preview image when a live crop is persisted. The crop/live
   * endpoint returns the new revision in X-Page-Revision; read it from the
   * htmx response rather than a full canvas swap so focus and scroll survive. */
  document.addEventListener("htmx:afterRequest", function (event) {
    const xhr = event.detail ? event.detail.xhr : null;
    if (!xhr || xhr.status !== 204) return;
    const revision = xhr.getResponseHeader("X-Page-Revision");
    if (!revision) return;
    /* The live crop is persisted; keep the form defaults in sync so the
     * shutdown button does not report these values as unsaved. */
    if (lastCropSlotId !== null) {
      const slot = document.querySelector(
        `.slot[data-slot-id="${lastCropSlotId}"]`
      );
      if (slot) {
        slot
          .querySelectorAll(
            'input[name="crop_zoom"], input[name="crop_focus_x"], input[name="crop_focus_y"]'
          )
          .forEach(function (input) {
            input.defaultValue = input.value;
          });
      }
      lastCropSlotId = null;
    }
    const canvas = document.querySelector(".editor-canvas");
    if (!canvas) return;
    const image = canvas.querySelector(".page-preview-image");
    if (!image) return;
    refreshPreview(canvas.dataset.projectId, canvas.dataset.pageId, revision, image, false);
  });

  /* Poll after a cache miss, then load the completed image before replacing
   * the visible preview. The current image remains visible while rendering. */
  function refreshPreview(projectId, pageId, revision, image, showOverlay = true) {
    if (!image || !image.isConnected) return;
    const width = Number(image.dataset.previewWidth || 640);
    const isMainPreview = image.classList.contains("page-preview-image");
    const canvas = image.closest(".editor-canvas");
    const overlay = showOverlay && isMainPreview && canvas
      ? canvas.querySelector(".page-preview-refreshing")
      : null;
    if (overlay) overlay.hidden = false;

    const statusUrl =
      `/projects/${projectId}/pages/${pageId}/preview-status?max_width=${width}`;
    const pollToken = Symbol("preview-poll");
    image._previewPollToken = pollToken;
    const maxAttempts = 60; /* 30 seconds at 500 ms */
    let attempts = 0;

    function poll() {
      if (!image.isConnected || image._previewPollToken !== pollToken) return;
      attempts += 1;
      if (attempts > maxAttempts) {
        if (overlay) overlay.hidden = true;
        return;
      }
      fetch(statusUrl)
        .then(function (response) { return response.json(); })
        .then(function (data) {
          if (!image.isConnected || image._previewPollToken !== pollToken) return;
          if (data.status === "ready") {
            const readyRevision = data.revision || revision;
            const url =
              `/projects/${projectId}/pages/${pageId}/preview?max_width=${width}` +
              `&v=${readyRevision}&_=${Date.now()}`;
            const loaded = new Image();
            loaded.onload = function () {
              if (!image.isConnected || image._previewPollToken !== pollToken) return;
              if (loaded.naturalWidth <= 1) {
                setTimeout(poll, 500);
                return;
              }
              image.onload = function () {
                if (overlay) overlay.hidden = true;
              };
              image.onerror = function () {
                if (overlay) overlay.hidden = true;
              };
              image.dataset.revision = readyRevision;
              image.src = url;
            };
            loaded.onerror = function () {
              if (overlay) overlay.hidden = true;
              console.error("Preview image failed to load:", url);
            };
            loaded.src = url;
          } else if (data.status === "error") {
            if (overlay) overlay.hidden = true;
            console.error("Preview refresh failed:", data.error || "unknown error");
          } else {
            setTimeout(poll, 500);
          }
        })
        .catch(function () {
          if (!image.isConnected || image._previewPollToken !== pollToken) return;
          setTimeout(poll, 500);
        });
    }

    poll();
  }

  function watchPreviewImages() {
    const canvas = document.querySelector(".editor-canvas");
    const previous = retainedPreviews;
    if (
      canvas &&
      previous &&
      canvas.dataset.projectId === previous.projectId &&
      canvas.dataset.pageId === previous.pageId &&
      canvas.dataset.renderRevision !== previous.revision
    ) {
      retainedPreviews = null;
      const currentImages = [
        [canvas.querySelector(".page-preview-image"), previous.image],
        [
          document.getElementById(`page-thumb-preview-${previous.pageId}`),
          previous.thumbnail,
        ],
      ];
      currentImages.forEach(function ([image, snapshot]) {
        if (!image) return;
        if (snapshot) image.src = snapshot;
        refreshPreview(
          previous.projectId,
          previous.pageId,
          canvas.dataset.renderRevision,
          image,
          false
        );
      });
    }

    document
      .querySelectorAll(".page-preview-image, .page-thumb-preview[data-preview-width]")
      .forEach(function (image) {
        if (image.dataset.previewWatched) return;
        image.dataset.previewWatched = "true";
        const checkPlaceholder = function () {
          if (!image.isConnected || !image.complete || image.naturalWidth > 1) return;
          refreshPreview(
            image.dataset.projectId,
            image.dataset.pageId,
            image.dataset.revision || "0",
            image
          );
        };
        image.addEventListener("load", checkPlaceholder);
        if (image.complete) checkPlaceholder();
      });
  }

  document.addEventListener("htmx:afterSwap", watchPreviewImages);
  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", watchPreviewImages, { once: true });
  } else {
    watchPreviewImages();
  }
})();
