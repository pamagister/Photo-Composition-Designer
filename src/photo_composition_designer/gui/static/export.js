(function () {
  "use strict";

  var jpg = document.getElementById("export-jpg");
  var pdf = document.getElementById("export-pdf");
  var button = document.getElementById("export-submit");
  var qualityFields = document.querySelectorAll(".export-quality-field input");
  if (!jpg || !pdf || !button) {
    return;
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
