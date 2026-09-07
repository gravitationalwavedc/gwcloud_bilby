/*
 * search_stale_guard.js — stale-history suppression for the coordinated
 * search/filter form (issue #75 / UX-17).
 *
 * A search request whose captured input revision is older than the current
 * revision (the user kept typing while it was in flight) is obsolete: it must
 * not swap into the list region nor promote its URL to history. The live
 * input is the sole authority during editing; the URL is authoritative only
 * on initial navigation and genuine Back/Forward restoration.
 *
 * Only search-input edits bump the revision. Filter-select changes are
 * discrete user actions already coordinated by form-level hx-sync:replace
 * (last-request-wins); bumping on a select's change event would race with
 * htmx's own change-triggered request (which fires first) and wrongly mark
 * that request obsolete.
 *
 * This is the conditional revision protocol from issue #75: it is added only
 * because the race regression proved that an older search response can still
 * complete inside a newer edit's debounce window and promote stale history.
 */
(function () {
  "use strict";

  var revision = 0;
  var requestRevisions = new WeakMap();

  function bumpRevision() {
    revision += 1;
  }

  var searchInput = document.querySelector("form input[name='search']");
  if (!searchInput || !searchInput.form) {
    return;
  }

  // Search inputs (basic + advanced mirror): bump on each completed edit,
  // respecting IME composition. A text input does not fire a change event
  // per keystroke, so input + compositionend are the relevant signals.
  var searchControls = [searchInput];
  var advanced = document.getElementById("advanced-search");
  if (advanced) {
    searchControls.push(advanced);
  }
  searchControls.forEach(function (el) {
    el.addEventListener("input", function (event) {
      if (event.isComposing) {
        return;
      }
      bumpRevision();
    });
    el.addEventListener("compositionend", bumpRevision);
  });

  // Capture the current revision when a request is about to be sent.
  document.addEventListener("htmx:beforeRequest", function (event) {
    var xhr = event.detail && event.detail.xhr;
    if (xhr) {
      requestRevisions.set(xhr, revision);
    }
  });

  // Suppress obsolete responses: neither swap nor URL promotion. Setting
  // shouldSwap=false in htmx:beforeSwap also prevents hx-push-url and the
  // htmx:pushedIntoHistory event for that response.
  document.addEventListener("htmx:beforeSwap", function (event) {
    var xhr = event.detail && event.detail.xhr;
    var reqRev = xhr && requestRevisions.get(xhr);
    if (reqRev !== undefined && reqRev !== revision) {
      event.detail.shouldSwap = false;
    }
  });
})();
