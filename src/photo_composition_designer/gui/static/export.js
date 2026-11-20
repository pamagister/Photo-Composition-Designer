(function () {
  "use strict";

  var jpg = document.getElementById("export-jpg");
  var pdf = document.getElementById("export-pdf");
  var button = document.getElementById("export-submit");
  var qualityFields = document.querySelectorAll(".export-quality-field input");
  var form = document.getElementById("export-form");
  var progressLabel = document.querySelector("[data-export-progress]");
  if (!jpg || !pdf || !button) {
    return;
  }

  var project = form ? form.dataset.projectId : "";
  var progressTimer = null;
  var progressActive = false;

  function stopProgress() {
    progressActive = false;
    if (progressTimer !== null) {
      window.clearTimeout(progressTimer);
      progressTimer = null;
    }
  }

  function pollProgress() {
    if (!progressActive || !project) return;
    window.fetch(`/projects/${project}/export/progress`, {
      headers: { Accept: "application/json" },
      cache: "no-store",
    })
      .then(function (response) {
        return response.ok ? response.json() : null;
      })
      .then(function (data) {
        if (!progressActive) return;
        if (data && typeof data.percent === "number" && progressLabel) {
          progressLabel.textContent = `${data.percent}%`;
        }
        progressTimer = window.setTimeout(pollProgress, 500);
      })
      .catch(function () {
        if (!progressActive) return;
        progressTimer = window.setTimeout(pollProgress, 1000);
      });
  }

  function startProgress() {
    stopProgress();
    if (progressLabel) progressLabel.textContent = "0%";
    progressActive = true;
    pollProgress();
  }

  if (form && progressLabel && project) {
    form.addEventListener("htmx:beforeRequest", startProgress);
    document.addEventListener("htmx:afterRequest", function (event) {
      if (!event.detail || event.detail.elt === form) stopProgress();
    });
    document.addEventListener("htmx:sendError", stopProgress);
  }

  function sync() {
    button.disabled = !(jpg.checked || pdf.checked);
    qualityFields.forEach(function (field) {
      field.disabled = !jpg.checked;
    });
  }

  jpg.addEventListener("change", sync);
  pdf.addEventListener("change", sync);
  sync();
})();
