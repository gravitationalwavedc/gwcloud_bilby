/*
 * Shared lifecycle controller for HTMX-backed list regions.
 *
 * Regions declare their persistent loading UI and inner swap target through
 * data-list-* attributes. Request ownership is token based so a superseded
 * request can never clear the state of the current request.
 */
(function () {
  "use strict";

  var regions = [];
  var requestState = new WeakMap();

  function findRegisteredRegion(element) {
    var region;
    var i;

    if (!element || element.nodeType !== 1) {
      return null;
    }

    region = element.closest("[data-list-region]");
    if (!region) {
      return null;
    }

    for (i = 0; i < regions.length; i += 1) {
      if (regions[i].element === region) {
        return regions[i];
      }
    }
    return null;
  }

  function registerRegion(element) {
    var i;
    var targetId;

    for (i = 0; i < regions.length; i += 1) {
      if (regions[i].element === element) {
        return;
      }
    }

    targetId = element.getAttribute("data-list-target");
    if (!targetId) {
      return;
    }
    targetId = targetId.replace(/^#/, "");

    for (i = 0; i < regions.length; i += 1) {
      if (regions[i].targetId === targetId &&
          !regions[i].element.isConnected) {
        regions[i].element = element;
        return;
      }
    }

    var indicatorId = element.getAttribute("data-list-indicator");
    var indicator = indicatorId ? document.getElementById(indicatorId) : null;
    var indicatorText = indicator &&
      indicator.querySelector(".list-loading-indicator__text");
    var defaultText = indicator &&
      indicator.getAttribute("data-default-text");

    if (!defaultText && indicatorText) {
      defaultText = indicatorText.textContent;
    }
    if (!defaultText) {
      defaultText = "Updating results\u2026";
    }

    regions.push({
      element: element,
      targetId: targetId,
      nextToken: 0,
      activeToken: null,
      timer: null,
      pendingPagination: null,
      historyFocus: null,
      historyRepairPending: false,
      lastFocusedElement: null,
      defaultText: defaultText
    });
  }

  function discoverRegions(root) {
    var elements;
    var i;

    if (root && root.nodeType === 1 && root.matches("[data-list-region]")) {
      registerRegion(root);
    }

    elements = (root || document).querySelectorAll("[data-list-region]");
    for (i = 0; i < elements.length; i += 1) {
      registerRegion(elements[i]);
    }
  }

  function elementTargetsRegion(element, state) {
    var target;
    var selector;

    if (!element || element.nodeType !== 1) {
      return false;
    }

    target = element.getAttribute("hx-target") ||
      element.getAttribute("data-hx-target");
    if (target) {
      selector = target.replace(/^#/, "");
      if (selector === state.targetId) {
        return true;
      }
    }

    if (element.id === state.targetId) {
      return true;
    }

    target = element.closest("#" + state.targetId);
    return Boolean(target);
  }

  function resolveRegion(detail) {
    var target = detail && detail.target;
    var trigger = detail && detail.elt;
    var state;
    var i;

    state = findRegisteredRegion(target) || findRegisteredRegion(trigger);
    if (state &&
        (elementTargetsRegion(target, state) ||
         elementTargetsRegion(trigger, state))) {
      return state;
    }

    for (i = 0; i < regions.length; i += 1) {
      state = regions[i];
      if (elementTargetsRegion(target, state) ||
          elementTargetsRegion(trigger, state)) {
        return state;
      }
    }
    return null;
  }

  function requestIdentity(detail) {
    return detail && (detail.xhr || detail.elt);
  }

  function childFor(state, attribute) {
    var id = state.element.getAttribute(attribute);
    return id ? document.getElementById(id) : null;
  }

  function setIndicatorText(indicator, text) {
    var textElement;

    if (!indicator) {
      return;
    }

    textElement = indicator.querySelector(".list-loading-indicator__text");
    if (textElement) {
      textElement.textContent = text;
    } else {
      indicator.textContent = text;
    }
  }

  function clearTimer(state) {
    if (state.timer !== null) {
      window.clearTimeout(state.timer);
      state.timer = null;
    }
  }

  function clearPendingPagination(state) {
    state.pendingPagination = null;
  }

  function paginationTrigger(element) {
    if (!element || element.nodeType !== 1) {
      return null;
    }
    return element.closest("[data-pagination-focus='true']");
  }

  function syncScope(element) {
    if (!element || element.nodeType !== 1 ||
        typeof element.closest !== "function") {
      return "";
    }
    var holder = element.closest("[hx-sync]");
    return holder ? holder.getAttribute("hx-sync") : "";
  }

  function beginRequest(event) {
    var detail = event.detail || {};
    var identity = requestIdentity(detail);
    var state = resolveRegion(detail);
    var indicator;
    var status;
    var config;
    var pagination;
    var page;
    var token;

    if (!state || !identity ||
        (typeof identity !== "object" && typeof identity !== "function")) {
      return;
    }

    state.nextToken += 1;
    token = state.nextToken;
    state.activeToken = token;
    clearTimer(state);

    config = detail.requestConfig || {};
    state.retry = {
      verb: (config.verb || "get").toLowerCase(),
      path: config.path || window.location.pathname,
      parameters: config.parameters || null
    };
    state.sync = syncScope(detail.elt);

    requestState.set(identity, {
      token: token,
      region: state,
      settled: false
    });

    state.element.setAttribute("aria-busy", "true");
    indicator = childFor(state, "data-list-indicator");
    status = childFor(state, "data-list-status");

    if (status) {
      status.textContent = "";
    }

    pagination = paginationTrigger(detail.elt);
    if (pagination) {
      page = pagination.getAttribute("data-page");
      state.pendingPagination = {page: page, token: token};
      if (indicator && page) {
        setIndicatorText(indicator, "Loading page " + page + "\u2026");
      }
    } else {
      clearPendingPagination(state);
      setIndicatorText(indicator, state.defaultText);
    }

    if (indicator) {
      indicator.hidden = false;
      indicator.setAttribute("aria-hidden", "false");
    }

    state.timer = window.setTimeout(function () {
      var metadata = requestState.get(identity);
      if (!metadata ||
          metadata.settled ||
          state.activeToken !== token) {
        return;
      }
      state.timer = null;
      status = childFor(state, "data-list-status");
      if (status) {
        status.textContent = "Updating results\u2026";
      }
    }, 1000);
  }

  function fragmentMetadata(state) {
    var target = state.element.querySelector("#" + state.targetId);
    var settled;

    if (!target) {
      return null;
    }

    settled = target.querySelector("[data-settled-kind]");
    return settled || target.querySelector("[data-document-title]");
  }

  function settledMessage(state) {
    var settled = fragmentMetadata(state);
    var kind;
    var message;

    if (!settled) {
      return "";
    }

    kind = settled.getAttribute("data-settled-kind");
    message = settled.getAttribute("data-settled-message");
    if ((kind === "content" || kind === "empty" || kind === "stale") &&
        message) {
      return message;
    }
    return "";
  }

  function restoreDocumentTitle(state) {
    var settled = fragmentMetadata(state);
    var title = settled && settled.getAttribute("data-document-title");

    if (title) {
      document.title = title;
    }
  }

  function focusHeading(state) {
    var heading = childFor(state, "data-list-heading");
    var rect;
    var probe;
    var probeX;
    var probeY;

    if (!heading) {
      return;
    }

    heading.focus({preventScroll: true});
    rect = heading.getBoundingClientRect();
    probeX = Math.max(0, Math.min(
      window.innerWidth - 1,
      rect.left + Math.max(1, rect.width / 2)
    ));
    probeY = Math.max(0, Math.min(
      window.innerHeight - 1,
      rect.top + Math.max(1, Math.min(rect.height || 1, 2))
    ));
    probe = document.elementFromPoint(probeX, probeY);

    if (rect.top < 0 ||
        (probe && probe !== heading && !heading.contains(probe))) {
      heading.scrollIntoView({block: "start"});
    }
  }

  function buildRetryUrl(state) {
    var retry = state.retry || {};
    var parameters = retry.parameters;
    var query = [];
    var key;

    if (retry.verb !== "get" || !retry.path) {
      return "";
    }

    if (parameters && typeof parameters === "object") {
      Object.keys(parameters).forEach(function (parameter) {
        var values = Array.isArray(parameters[parameter])
          ? parameters[parameter]
          : [parameters[parameter]];

        values.forEach(function (value) {
          if (value === null || value === undefined || value === "") {
            return;
          }
          query.push(
            encodeURIComponent(parameter) + "=" + encodeURIComponent(value)
          );
        });
      });
    }

    key = retry.path.indexOf("?") === -1 ? "?" : "&";
    return retry.path + (query.length ? key + query.join("&") : "");
  }

  function renderTransportError(state) {
    var target = document.getElementById(state.targetId);
    var indicatorId = state.element.getAttribute("data-list-indicator");
    var heading = state.element.getAttribute("aria-label") || "";
    var url = buildRetryUrl(state);
    var wrapper;
    var alertBox;
    var message;
    var prefix;
    var retryButton;

    if (!target) {
      return;
    }

    wrapper = document.createElement("div");
    wrapper.className = "list-fragment";
    wrapper.setAttribute("data-settled-kind", "error");

    alertBox = document.createElement("div");
    alertBox.className = "async-error";
    alertBox.setAttribute("role", "alert");
    if (heading) {
      alertBox.setAttribute("aria-label", heading);
    }

    message = document.createElement("p");
    message.className = "async-error-message mb-0";
    prefix = document.createElement("span");
    prefix.className = "sr-only";
    prefix.textContent = "Error: ";
    message.appendChild(prefix);
    message.appendChild(document.createTextNode(
      "Couldn't load the results because the service is temporarily unavailable."
    ));

    retryButton = document.createElement("button");
    retryButton.type = "button";
    retryButton.className = "btn btn-primary";
    retryButton.textContent = "Retry";
    retryButton.setAttribute("hx-get", url);
    retryButton.setAttribute("hx-target", "#" + state.targetId);
    retryButton.setAttribute("hx-swap", "innerHTML");
    if (indicatorId) {
      retryButton.setAttribute("hx-indicator", "#" + indicatorId);
    }
    if (state.sync) {
      retryButton.setAttribute("hx-sync", state.sync);
    }

    alertBox.appendChild(message);
    alertBox.appendChild(retryButton);
    wrapper.appendChild(alertBox);
    target.textContent = "";
    target.appendChild(wrapper);

    if (window.htmx && typeof window.htmx.process === "function") {
      window.htmx.process(wrapper);
    } else {
      retryButton.addEventListener("click", function () {
        if (url) {
          window.location.href = url;
        } else {
          window.location.reload();
        }
      });
    }
  }

  function finishRequest(event, publishSettledMessage) {
    var detail = event.detail || {};
    var identity = requestIdentity(detail);
    var metadata;
    var state;
    var indicator;
    var status;
    var message;
    var pagination;

    if (!identity ||
        (typeof identity !== "object" && typeof identity !== "function")) {
      return null;
    }

    metadata = requestState.get(identity);
    if (!metadata || metadata.settled) {
      return null;
    }

    state = metadata.region;
    if (state.activeToken !== metadata.token) {
      metadata.settled = true;
      requestState.delete(identity);
      return null;
    }

    metadata.settled = true;
    clearTimer(state);

    status = childFor(state, "data-list-status");
    if (status) {
      status.textContent = "";
    }

    state.element.setAttribute("aria-busy", "false");
    indicator = childFor(state, "data-list-indicator");
    if (indicator) {
      indicator.hidden = true;
      indicator.setAttribute("aria-hidden", "true");
    }

    pagination = state.pendingPagination &&
      state.pendingPagination.token === metadata.token
      ? state.pendingPagination
      : null;

    state.activeToken = null;
    clearPendingPagination(state);
    requestState.delete(identity);

    if (publishSettledMessage) {
      restoreDocumentTitle(state);
      if (status) {
        message = settledMessage(state);
        if (message) {
          status.textContent = message;
        }
      }
      if (pagination) {
        focusHeading(state);
      }
    }
    return state;
  }

  function finishFailure(event) {
    var state = finishRequest(event, false);
    if (state) {
      renderTransportError(state);
    }
  }

  function rememberFocusedElement(event) {
    var focused = event.target;
    var i;

    if (!focused || focused.nodeType !== 1 ||
        focused === document.body ||
        focused === document.documentElement) {
      return;
    }

    for (i = 0; i < regions.length; i += 1) {
      regions[i].lastFocusedElement = focused;
    }
  }

  function snapshotHistoryFocus() {
    var active = document.activeElement;

    var i;
    var state;
    var target;
    var focused;

    for (i = 0; i < regions.length; i += 1) {
      state = regions[i];
      target = document.getElementById(state.targetId);
      focused = active;
      if (!focused ||
          focused === document.body ||
          focused === document.documentElement) {
        focused = state.lastFocusedElement;
      }
      state.historyFocus = {
        element: focused,
        elementId: focused && focused.id || "",
        wasInsideTarget: Boolean(
          target && focused && target.contains(focused)
        )
      };
      state.historyRepairPending = false;
      clearPendingPagination(state);
    }
  }

  function historyFocusTarget(
    state,
    candidate,
    candidateId,
    wasInsideTarget
  ) {
    var currentCandidate = candidate;
    var headingId;

    if ((!currentCandidate || !currentCandidate.isConnected) && candidateId) {
      currentCandidate = document.getElementById(candidateId);
    }

    if (!wasInsideTarget &&
        currentCandidate &&
        currentCandidate.isConnected) {
      return currentCandidate;
    }

    if (wasInsideTarget) {
      headingId = state.element.getAttribute("data-list-heading");
      return headingId ? document.getElementById(headingId) : null;
    }

    return null;
  }

  function restoreHistoryFocus(
    state,
    candidate,
    candidateId,
    wasInsideTarget,
    force
  ) {
    var active = document.activeElement;
    var target = historyFocusTarget(
      state,
      candidate,
      candidateId,
      wasInsideTarget
    );

    restoreDocumentTitle(state);
    if (target &&
        target.isConnected &&
        (force ||
         active === document.body ||
         active === document.documentElement)) {
      target.focus({preventScroll: true});
    }
  }

  function finishHistoryFocusRepair(state) {
    state.historyFocus = null;
    state.historyRepairPending = false;
  }

  function restoreHistory() {
    var i;
    var state;
    var snapshot;
    var candidate;
    var candidateId;
    var wasInsideTarget;

    for (i = 0; i < regions.length; i += 1) {
      state = regions[i];
      clearPendingPagination(state);
      restoreDocumentTitle(state);

      if (state.historyRepairPending) {
        continue;
      }

      snapshot = state.historyFocus;
      candidate = snapshot && snapshot.element;
      candidateId = snapshot && snapshot.elementId || "";
      wasInsideTarget = Boolean(snapshot && snapshot.wasInsideTarget);
      state.historyRepairPending = true;

      (function (
        historyState,
        historyCandidate,
        historyCandidateId,
        candidateWasInsideTarget
      ) {
        window.setTimeout(function () {
          restoreHistoryFocus(
            historyState,
            historyCandidate,
            historyCandidateId,
            candidateWasInsideTarget,
            true
          );
        }, 0);

        [50, 100, 175, 250].forEach(function (delay) {
          window.setTimeout(function () {
            restoreHistoryFocus(
              historyState,
              historyCandidate,
              historyCandidateId,
              candidateWasInsideTarget,
              false
            );
          }, delay);
        });

        window.setTimeout(function () {
          restoreHistoryFocus(
            historyState,
            historyCandidate,
            historyCandidateId,
            candidateWasInsideTarget,
            false
          );
          finishHistoryFocusRepair(historyState);
        }, 325);
      })(state, candidate, candidateId, wasInsideTarget);
    }
  }

  function onReady() {
    discoverRegions(document);
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", onReady);
  } else {
    onReady();
  }

  document.addEventListener("focusin", rememberFocusedElement);
  document.addEventListener("htmx:load", function (event) {
    discoverRegions((event.detail && event.detail.elt) || document);
  });
  document.addEventListener("htmx:beforeRequest", beginRequest);
  document.addEventListener("htmx:afterSwap", function (event) {
    finishRequest(event, true);
  });
  document.addEventListener("htmx:responseError", finishFailure);
  document.addEventListener("htmx:sendError", finishFailure);
  document.addEventListener("htmx:timeout", finishFailure);
  document.addEventListener("htmx:abort", function (event) {
    finishRequest(event, false);
  });
  document.addEventListener("bilbyui:listRequestSuppressed", function (event) {
    finishRequest(event, false);
  });
  document.addEventListener("htmx:historyRestore", restoreHistory);
  window.addEventListener("popstate", snapshotHistoryFocus);
})();
