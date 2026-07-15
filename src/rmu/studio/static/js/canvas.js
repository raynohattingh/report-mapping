/* Canvas orchestration (US1): geometry fetch, pane mounting, tri-directional
   selection (source ↔ link list ↔ target, FR-018), click-source-then-target
   link drawing (FR-013), jump-to-next-blocking (FR-019). No business logic —
   every decision is a POST to a route that calls the CLI's code path. */

import { mountPdfPane } from "/static/js/viewer.js";
import { drawBoxes } from "/static/js/overlay.js";
import { drawWire, clearWire } from "/static/js/wires.js";

const root = document.getElementById("canvas-root");
if (root) init(root);

async function init(root) {
  const sessionId = root.dataset.sessionId;
  const readOnly = Boolean(root.dataset.readOnly);
  const geo = await (await fetch(`/sessions/${sessionId}/geometry`)).json();
  const tierByField = new Map(geo.links.map((l) => [l.target_field, l.tier]));
  const tagByField = new Map(geo.links.map((l) => [l.target_field, l.tag]));

  let pendingSource = null; // click source → click target = new link (FR-013)

  const sourcePaneEl = root.querySelector('[data-pdf-pane="source"]');
  if (sourcePaneEl && geo.source.pdf_sha) {
    mountPdfPane(sourcePaneEl, geo.source.pdf_sha, (pageNo, holder, layer, scale) => {
      drawBoxes(layer, scale, geo.source.boxes.filter((b) => b.page === pageNo), {
        keyAttr: "sourceKey",
        onSelect: (box) => selectSource(box.key),
      });
    }, root.querySelector('[data-page-indicator="source"]'));
  }

  const targetPaneEl = root.querySelector('[data-pdf-pane="target"]');
  if (targetPaneEl && geo.target.pdf_sha) {
    mountPdfPane(targetPaneEl, geo.target.pdf_sha, (pageNo, holder, layer, scale) => {
      drawBoxes(layer, scale, geo.target.boxes.filter((b) => b.page === pageNo), {
        keyAttr: "targetField",
        tierOf: (b) => tierByField.get(b.field) || "T3",
        tagOf: (b) => tagByField.get(b.field),
        onSelect: (box) => selectTarget(box.field),
      });
    }, root.querySelector('[data-page-indicator="target"]'));
  }

  function selectSource(key) {
    if (readOnly) return focusLinkBySource(key);
    pendingSource = key;
    document.querySelectorAll(".source-el").forEach((el) =>
      el.classList.toggle("focused", el.dataset.sourceKey === key));
  }

  function selectTarget(field) {
    if (!readOnly && pendingSource) {
      const hash = document.getElementById("draft-hash")?.dataset.hash;
      window.htmx.ajax("POST", `/sessions/${sessionId}/routes`, {
        values: { field, source: pendingSource, base_hash: hash },
        target: "#link-list",
        swap: "outerHTML",
      });
      pendingSource = null;
      return;
    }
    focusLinkByField(field);
  }

  function focusLinkByField(field) {
    const row = document.querySelector(`.link-row[data-field="${field}"]`);
    focusRow(row);
  }
  function focusLinkBySource(key) {
    const row = document.querySelector(`.link-row[data-source="${key}"]`);
    focusRow(row);
  }
  function focusRow(row) {
    document.querySelectorAll(".link-row.focused").forEach((r) =>
      r.classList.remove("focused"));
    if (!row) return clearWire();
    row.classList.add("focused");
    row.scrollIntoView({ block: "nearest" });
    const sourceEl =
      document.querySelector(`.source-el[data-source-key="${row.dataset.source}"]`) ||
      document.querySelector(`[data-source-key="${row.dataset.source}"]`);
    const targetEl =
      document.querySelector(`.target-el[data-target-field="${row.dataset.field}"]`) ||
      document.querySelector(`[data-target-field="${row.dataset.field}"]`);
    drawWire(sourceEl, targetEl, row.dataset.tier);
  }

  // tri-directional selection from panels and the link list
  document.addEventListener("click", (evt) => {
    const sourceRow = evt.target.closest(".source-el");
    if (sourceRow) return selectSource(sourceRow.dataset.sourceKey);
    const targetRow = evt.target.closest(".target-el");
    if (targetRow) return selectTarget(targetRow.dataset.targetField);
    const linkRow = evt.target.closest(".link-row[data-field]");
    if (linkRow && !evt.target.closest("button, a")) return focusRow(linkRow);
    const next = evt.target.closest("[data-focus-field]");
    if (next) return focusLinkByField(next.dataset.focusField);
  });
  document.addEventListener("mouseover", (evt) => {
    const row = evt.target.closest(".link-row[data-field]");
    if (row) focusRow(row);
  });
}
