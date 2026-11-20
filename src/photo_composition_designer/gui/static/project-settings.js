/* Show only the holiday subdivision group that matches the selected locale. */
(function () {
  "use strict";

  var language = document.getElementById("calendar-language");
  if (!language) return;

  var groups = Array.from(document.querySelectorAll("[data-holiday-country]"));
  if (!groups.length) return;

  function selectedCountry() {
    var value = language.value || "";
    var parts = value.split("_");
    return parts.length > 1 ? parts[1].toUpperCase() : "";
  }

  function sync() {
    var country = selectedCountry();
    groups.forEach(function (group) {
      var matches = group.dataset.holidayCountry === country;
      group.hidden = !matches;
      if (!matches) {
        group.querySelectorAll('input[type="checkbox"]').forEach(function (box) {
          box.checked = false;
        });
      }
    });
  }

  language.addEventListener("change", sync);
  sync();
})();