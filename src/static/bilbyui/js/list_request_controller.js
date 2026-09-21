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
      targetId: targetId.replace(/^#/, ""),
      nextToken: 0,
      activeToken: null,
      timer: null,
      pendingPagination: null,
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

  function beginRequest(event) {
    var detail = event.detail || {};
    var identity = requestIdentity(detail);
    var state = resolveRegion(detail);
    var indicator;
    var status;
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
      state.pendingPagination = {page: page};
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

  function settledMessage(state) {
    var target = state.element.querySelector("#" + state.targetId);
    var settled;
    var kind;
    var message;

    if (!target) {
      return "";
    }

    settled = target.querySelector(
      "[data-settled-kind][data-settled-message]"
    );
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

  function finishRequest(event, publishSettledMessage) {
    var detail = event.detail || {};
    var identity = requestIdentity(detail);
    var metadata;
    var state;
    var indicator;
    var status;
    var message;

    if (!identity ||
        (typeof identity !== "object" && typeof identity !== "function")) {
      return;
    }

    metadata = requestState.get(identity);
    if (!metadata || metadata.settled) {
      return;
    }

    state = metadata.region;
    if (state.activeToken !== metadata.token) {
      metadata.settled = true;
      requestState.delete(identity);
      return;
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

    state.activeToken = null;
    clearPendingPagination(state);
    requestState.delete(identity);

    if (publishSettledMessage && status) {
      message = settledMessage(state);
      if (message) {
        status.textContent = message;
      }
    }
  }

  function clearHistoryPending() {
    var i;
    for (i = 0; i < regions.length; i += 1) {
      clearPendingPagination(regions[i]);
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

  document.addEventListener("htmx:load", function (event) {
    discoverRegions((event.detail && event.detail.elt) || document);
  });
  document.addEventListener("htmx:beforeRequest", beginRequest);
  document.addEventListener("htmx:afterSwap", function (event) {
    finishRequest(event, true);
  });
  document.addEventListener("htmx:responseError", function (event) {
    finishRequest(event, false);
  });
  document.addEventListener("htmx:sendError", function (event) {
    finishRequest(event, false);
  });
  document.addEventListener("htmx:timeout", function (event) {
    finishRequest(event, false);
  });
  document.addEventListener("htmx:abort", function (event) {
    finishRequest(event, false);
  });
  document.addEventListener("bilbyui:listRequestSuppressed", function (event) {
    finishRequest(event, false);
  });
  document.addEventListener("htmx:historyRestore", clearHistoryPending);
  window.addEventListener("popstate", clearHistoryPending);
})();
