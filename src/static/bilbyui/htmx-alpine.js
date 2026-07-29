(function () {
  // Alpine only walks the DOM on first load. Re-init any HTMX-injected subtrees
  // (including OOB) so x-data / x-show work on swapped fragments.
  function initAlpine(elt) {
    if (typeof Alpine === "undefined" || !elt || !elt.querySelectorAll) {
      return;
    }
    Alpine.initTree(elt);
  }

  if (typeof htmx !== "undefined" && typeof htmx.onLoad === "function") {
    htmx.onLoad(initAlpine);
  } else {
    document.body.addEventListener("htmx:load", function (event) {
      initAlpine(event.detail.elt);
    });
  }
})();
