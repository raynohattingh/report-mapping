/* Onboarding keyboard triage (FR-034): Y confirm · E rename · X remove, with
   auto-advance to the next proposed element and a spotlight on the current
   one. Every action is a POST to the same review-state write path the CLI
   YAML hand-edit uses. State filter narrows the working set. */

import { mountPdfPane } from "/static/js/viewer.js";
import { drawBoxes } from "/static/js/overlay.js";

const root = document.getElementById("triage-root");
if (root) initTriage(root);

const STATE_TIER = { confirmed: "T0", corrected: "T0", removed: "T3", proposed: "T2" };

async function initTriage(root) {
  const proposalId = root.dataset.proposalId;
  const readOnly = Boolean(root.dataset.readOnly);
  const geo = await (await fetch(`/proposals/${proposalId}/geometry`)).json();
  window.__proposalGeo = geo; // regions.js reads this
  let exemplarIdx = 0;
  let cursor = 0;

  const pane = root.querySelector('[data-pdf-pane="proposal"]');
  const indicator = root.querySelector('[data-page-indicator="proposal"]');

  function mount(idx) {
    pane.replaceChildren();
    const ex = geo.exemplars[idx];
    if (!ex || !ex.sha) return;
    mountPdfPane(pane, ex.sha, (pageNo, holder, layer, scale) => {
      const boxes = ex.boxes.filter((b) => b.page === pageNo);
      drawBoxes(layer, scale, boxes, {
        keyAttr: "elementId",
        tierOf: (b) => STATE_TIER[stateOf(b.id)] || "T2",
        onSelect: (b) => focusElement(b.id),
      });
      if (window.__regionsHook) window.__regionsHook(pageNo, holder, layer, scale, ex);
    }, indicator);
  }
  mount(exemplarIdx);

  const switcher = document.getElementById("exemplar-switcher");
  if (switcher) switcher.addEventListener("change", (e) => {
    exemplarIdx = Number(e.target.value);
    mount(exemplarIdx);
  });

  function stateOf(id) {
    const row = document.querySelector(`.triage-el[data-element-id="${id}"]`);
    return row ? row.dataset.state : "proposed";
  }
  function proposedRows() {
    return [...document.querySelectorAll('.triage-el[data-state="proposed"]')];
  }
  function focusElement(id) {
    document.querySelectorAll(".triage-el.focused").forEach((r) =>
      r.classList.remove("focused"));
    const row = document.querySelector(`.triage-el[data-element-id="${id}"]`);
    if (row) { row.classList.add("focused"); row.scrollIntoView({ block: "nearest" }); }
  }
  function advance() {
    const rows = proposedRows();
    if (rows.length) focusElement(rows[Math.min(cursor, rows.length - 1)].dataset.elementId);
  }
  advance();

  function act(action, extra = {}) {
    const rows = proposedRows();
    const row = document.querySelector(".triage-el.focused") || rows[0];
    if (!row) return;
    const id = row.dataset.elementId;
    window.htmx.ajax("POST", `/proposals/${proposalId}/elements/${id}`, {
      values: { action, ...extra },
      target: "#triage-root",
      swap: "none",
    });
  }

  // Matrix proposals (#axis-rail present) hand the document keyboard to
  // axistriage.js — Y/E here would race the axis-entry meaning of the same
  // keys. Contract pinned in tests/studio/test_matrix_rail_template.py:
  // cells keep their hx-post buttons; axis rows get keyboard triage.
  if (!readOnly && !document.getElementById("axis-rail")) {
    document.addEventListener("keydown", (evt) => {
      if (evt.target.matches("input, select, textarea")) return;
      if (evt.key === "y" || evt.key === "Y") { act("confirm"); advance(); }
      else if (evt.key === "x" || evt.key === "X") { act("remove"); advance(); }
      else if (evt.key === "e" || evt.key === "E") {
        const row = document.querySelector(".triage-el.focused");
        if (row && window.__renameElement) window.__renameElement(row.dataset.elementId);
      }
    });
  }

  const filter = document.getElementById("triage-filter");
  if (filter) filter.addEventListener("change", (e) => {
    const want = e.target.value;
    document.querySelectorAll(".triage-el").forEach((r) =>
      r.style.display = (!want || r.dataset.state === want) ? "" : "none");
  });

  // refresh geometry + spotlight after each htmx swap of the rail
  document.body.addEventListener("htmx:afterRequest", (evt) => {
    if (evt.detail.pathInfo && evt.detail.pathInfo.requestPath &&
        evt.detail.pathInfo.requestPath.includes(`/proposals/${proposalId}/`)) {
      fetch(`/proposals/${proposalId}/geometry`).then((r) => r.json()).then((g) => {
        window.__proposalGeo = g;
        geo.exemplars = g.exemplars;
        mount(exemplarIdx);
        advance();
      });
    }
  });
}
