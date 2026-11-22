// Auto-close other top navigation dropdowns when one opens.
//
// The menus are native <details class="nav-dropdown"> elements. Listening for
// their `toggle` event keeps the markup and keyboard/ARIA behaviour untouched
// while ensuring at most one top menu is open at a time.
(function () {
  "use strict";

  function closeOthers(opened) {
    document.querySelectorAll("details.nav-dropdown[open]").forEach(function (menu) {
      if (menu !== opened) {
        menu.open = false;
      }
    });
  }

  function attach() {
    document.querySelectorAll("details.nav-dropdown").forEach(function (menu) {
      menu.addEventListener("toggle", function () {
        if (menu.open) {
          closeOthers(menu);
        }
      });
    });
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", attach);
  } else {
    attach();
  }
})();