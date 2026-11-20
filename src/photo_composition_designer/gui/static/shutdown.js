/* Shutdown button: persist pending editor changes, stop the local server and
 * close the tab.
 *
 * Every editor mutation is already persisted by the server. The client only
 * waits for requests it initiated (including the debounced keyboard crop) and
 * warns before discarding unsaved form edits. The server is only stoppable
 * when the CLI started uvicorn; otherwise the endpoint reports the situation
 * and the page stays open.
 */
(function () {
  "use strict";

  const button = document.querySelector("[data-shutdown]");
  if (!button) return;

  const REQUEST_TIMEOUT_MS = 5000;
  const STOP_TIMEOUT_MS = 15000;
  const POLL_INTERVAL_MS = 250;
  let inFlight = 0;

  document.addEventListener("htmx:beforeRequest", function () {
    inFlight += 1;
  });

  document.addEventListener("htmx:afterRequest", function () {
    inFlight = Math.max(0, inFlight - 1);
  });

  /* Forms that persist settings keep their server-rendered defaults in the
   * DOM. Action forms (assign, move, replace, ...) only use selects as
   * command pickers, so their selects are excluded from the dirty check. */
  function dirtyFields() {
    const selector = [
      "form input:not([type='hidden']):not([type='file']):not([type='submit'])"
        + ":not([type='button']):not([type='reset'])",
      "form textarea",
      "form.settings-form select",
    ].join(",");
    return Array.from(document.querySelectorAll(selector)).filter(function (field) {
      if (field.disabled) return false;
      if (field.tagName === "SELECT") {
        return Array.from(field.options).some(function (option) {
          return option.selected !== option.defaultSelected;
        });
      }
      if (field.type === "checkbox" || field.type === "radio") {
        return field.checked !== field.defaultChecked;
      }
      return field.value !== field.defaultValue;
    });
  }

  function hasUnsavedChanges() {
    const state = document.querySelector("[data-save-state]");
    const stateIsUnsaved =
      state !== null && state.textContent.trim().toLowerCase() === "unsaved";
    return stateIsUnsaved || dirtyFields().length > 0;
  }

  /* The keyboard crop path debounces its request for 120 ms. Flush it and
   * wait until every htmx request that was in flight has settled. */
  function waitForPendingRequests() {
    if (window.pcdFlushPending) window.pcdFlushPending();
    if (inFlight === 0 && !document.querySelector(".htmx-request")) {
      return Promise.resolve();
    }
    return new Promise(function (resolve) {
      const started = Date.now();
      const timer = window.setInterval(function () {
        if (
          (inFlight === 0 && !document.querySelector(".htmx-request")) ||
          Date.now() - started > REQUEST_TIMEOUT_MS
        ) {
          window.clearInterval(timer);
          resolve();
        }
      }, 50);
    });
  }

  function restoreButton() {
    button.disabled = false;
    button.removeAttribute("aria-busy");
  }

  function showStopped() {
    const message = document.createElement("main");
    message.className = "shutdown-message";
    const heading = document.createElement("h1");
    heading.textContent = "Server stopped";
    const hint = document.createElement("p");
    hint.textContent = "You can close this tab now.";
    message.append(heading, hint);
    document.body.replaceChildren(message);
    window.close();
  }

  /* Once the shutdown request is sent, the health endpoint starts failing.
   * Network errors therefore mean success: the process is gone. */
  function pollUntilStopped() {
    const started = Date.now();
    function poll() {
      fetch("/health", { cache: "no-store" })
        .then(function (response) {
          if (!response.ok) throw new Error("server stopped");
          if (Date.now() - started > STOP_TIMEOUT_MS) {
            restoreButton();
            window.alert("The server did not stop. Please try again.");
            return;
          }
          window.setTimeout(poll, POLL_INTERVAL_MS);
        })
        .catch(function () {
          showStopped();
        });
    }
    poll();
  }

  function requestShutdown() {
    fetch("/shutdown", { method: "POST", cache: "no-store" })
      .then(function (response) {
        return response.json().catch(function () {
          return null;
        });
      })
      .then(function (data) {
        if (data && data.stopping === false) {
          restoreButton();
          window.alert(data.message || "The server cannot be stopped.");
          return;
        }
        pollUntilStopped();
      })
      .catch(function () {
        /* The connection may close before the response arrives. */
        pollUntilStopped();
      });
  }

  button.addEventListener("click", function () {
    if (hasUnsavedChanges() && !window.confirm(
      "There are unsaved changes. Stop the server and discard them?"
    )) {
      return;
    }
    button.disabled = true;
    button.setAttribute("aria-busy", "true");
    waitForPendingRequests().then(requestShutdown);
  });
})();