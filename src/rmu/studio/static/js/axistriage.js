/* Axis triage (006 Phase 2 Task 4): keyboard review of the projected
   criteria/towers axis pair + row/column band highlights on the rendered
   exemplar. Display + POSTs only — every decision goes through the same
   /axis/{element}/entries/{index} routes the rail buttons post to.

   Script-loading contract (pinned in tests/studio/test_matrix_rail_template.py):
   this module COEXISTS with triage.js on matrix proposals. triage.js keeps the
   PDF mount, cell overlay boxes and the generic rail; it disables its own
   document keydown handler when #axis-rail is present, so this module owns the
   keyboard: arrows move the cursor, A accept / R reject suggestion, E rename,
   Y confirm the focused axis element once no entry still carries a suggestion.
   Read-only proposals attach no key handlers — highlight only.

   Band geometry: y_band/x_range are min/max over the member cells' registered
   visual-space bboxes ([x0, top, x1, bottom], same space overlay.js draws in),
   so the client multiplies by the page's zoom scale and nothing else (SC-007).
   Pages render lazily: we chain onto window.__regionsHook (called by triage.js
   for every page it mounts) WITHOUT clobbering regions.js's editor. */

const SVG = "http://www.w3.org/2000/svg";
const root = document.getElementById("triage-root");
const rail = document.getElementById("axis-rail");
if (root && rail) initAxisTriage(root);

async function initAxisTriage(root) {
  const proposalId = root.dataset.proposalId;
  const readOnly = Boolean(root.dataset.readOnly);
  let geo = await (await fetch(`/proposals/${proposalId}/geometry`)).json();
  if (!geo.matrix) return;

  const layers = new Map(); // pageNo -> { layer, scale } (current mount only)
  // selection: primary cursor + optional companion (cell click focuses BOTH
  // its criterion and tower rows); companion clears on any cursor move.
  let sel = firstPending(geo.matrix) || { kind: "criteria", index: 0 };
  let companion = null;
  let wantAdvance = false;

  // ---- lazy-page hook: chain, never replace (regions.js registered first) --
  const prior = window.__regionsHook;
  window.__regionsHook = (pageNo, holder, layer, scale, exemplar) => {
    if (prior) prior(pageNo, holder, layer, scale, exemplar);
    layers.set(pageNo, { layer, scale });
    layer.addEventListener("click", (evt) => cellClick(evt, pageNo, layer, scale));
    redraw();
  };

  // ---- panel helpers -----------------------------------------------------
  function entriesOf(kind) {
    return kind === "criteria" ? geo.matrix.criteria : geo.matrix.towers;
  }
  function elementIdOf(kind) {
    return kind === "criteria" ? geo.matrix.row_element_id
                               : geo.matrix.col_element_id;
  }
  function firstPending(matrix) {
    for (const kind of ["criteria", "towers"]) {
      const i = (kind === "criteria" ? matrix.criteria : matrix.towers)
        .findIndex((e) => e.suggested_label);
      if (i >= 0) return { kind, index: i };
    }
    return null;
  }

  // ---- band + row focus --------------------------------------------------
  function bandFor(pick) {
    const entry = entriesOf(pick.kind)[pick.index];
    if (!entry || !entry.page) return null;
    if (pick.kind === "criteria") {
      return entry.y_band ? { page: entry.page, axis: "row", band: entry.y_band } : null;
    }
    return entry.x_range ? { page: entry.page, axis: "col", band: entry.x_range } : null;
  }
  function drawBand(pick) {
    const b = bandFor(pick);
    if (!b) return;
    const mounted = layers.get(b.page);
    if (!mounted) return; // page not rendered yet — hook will redraw on mount
    const { layer, scale } = mounted;
    const rect = document.createElementNS(SVG, "rect");
    const [lo, hi] = b.band;
    if (b.axis === "row") {
      rect.setAttribute("x", 0);
      rect.setAttribute("y", lo * scale);
      rect.setAttribute("width", "100%");
      rect.setAttribute("height", (hi - lo) * scale);
      rect.setAttribute("class", "axis-band");
    } else {
      rect.setAttribute("x", lo * scale);
      rect.setAttribute("y", 0);
      rect.setAttribute("width", (hi - lo) * scale);
      rect.setAttribute("height", "100%");
      rect.setAttribute("class", "axis-band col");
    }
    layer.appendChild(rect);
  }
  function focusRow(pick) {
    const eid = elementIdOf(pick.kind);
    const row = document.querySelector(
      `[data-axis-entry="${eid}:${pick.index}"]`);
    if (row) { row.classList.add("focused"); row.scrollIntoView({ block: "nearest" }); }
  }
  function redraw() {
    document.querySelectorAll(".axis-band").forEach((r) => r.remove());
    document.querySelectorAll("#axis-rail .triage-el.focused")
      .forEach((r) => r.classList.remove("focused"));
    drawBand(sel);
    focusRow(sel);
    if (companion) { drawBand(companion); focusRow(companion); }
  }
  function select(pick, withCompanion = null) {
    sel = pick;
    companion = withCompanion;
    redraw();
  }

  // ---- cell overlay → focus BOTH axis rows (display-only, hit-test in the
  //      registered visual space: rendered px ÷ scale, inverse of drawing) --
  function cellClick(evt, pageNo, layer, scale) {
    const box = layer.getBoundingClientRect();
    const x = (evt.clientX - box.left) / scale;
    const y = (evt.clientY - box.top) / scale;
    const cell = (geo.spatial || []).find((c) =>
      c.page === pageNo && c.row_id && c.col_id &&
      c.bbox[0] <= x && x <= c.bbox[2] && c.bbox[1] <= y && y <= c.bbox[3]);
    if (!cell) return;
    const ri = geo.matrix.criteria.findIndex((e) => e.id === cell.row_id);
    const ci = geo.matrix.towers.findIndex((e) => e.id === cell.col_id);
    if (ri < 0) return;
    select({ kind: "criteria", index: ri },
           ci >= 0 ? { kind: "towers", index: ci } : null);
  }

  // ---- axis-row clicks (delegated: the rail is re-rendered by htmx OOB) ---
  document.addEventListener("click", (evt) => {
    const row = evt.target.closest("[data-axis-entry]");
    if (!row || evt.target.closest("button, input, form")) return;
    const index = Number(row.dataset.axisEntry.split(":").pop());
    select({ kind: row.dataset.kind, index });
  });

  // ---- POSTs (same window.htmx.ajax pattern as triage.js/regions.js) ------
  function post(action, extra = {}) {
    window.htmx.ajax("POST",
      `/proposals/${proposalId}/axis/${elementIdOf(sel.kind)}/entries/${sel.index}`,
      { values: { action, ...extra }, target: "#triage-root", swap: "none" });
  }
  function confirmAxis() {
    if (entriesOf(sel.kind).some((e) => e.suggested_label)) return; // pending
    window.htmx.ajax("POST",
      `/proposals/${proposalId}/axis/${elementIdOf(sel.kind)}/confirm`,
      { values: {}, target: "#triage-root", swap: "none" });
  }
  function rename() {
    const entry = entriesOf(sel.kind)[sel.index];
    if (!entry) return;
    const label = prompt("label:", entry.label || "");
    if (label === null || label === "") return;
    const extra = { label };
    if (sel.kind === "criteria") {
      const number = prompt("number:", entry.number || "");
      if (number === null) return;
      if (number) extra.number = number;
    }
    post("rename", extra);
  }

  // ---- keyboard (write path — absent entirely in read-only mode) ----------
  if (!readOnly) {
    document.addEventListener("keydown", (evt) => {
      if (evt.target.matches("input, select, textarea") ||
          evt.metaKey || evt.ctrlKey || evt.altKey) return;
      const key = evt.key.toLowerCase();
      const count = entriesOf(sel.kind).length;
      if (evt.key === "ArrowDown") {
        evt.preventDefault();
        select({ kind: sel.kind, index: Math.min(sel.index + 1, count - 1) });
      } else if (evt.key === "ArrowUp") {
        evt.preventDefault();
        select({ kind: sel.kind, index: Math.max(sel.index - 1, 0) });
      } else if (evt.key === "ArrowLeft" || evt.key === "ArrowRight") {
        const kind = evt.key === "ArrowLeft" ? "criteria" : "towers";
        if (entriesOf(kind).length && elementIdOf(kind)) {
          evt.preventDefault();
          select({ kind, index: Math.min(sel.index, entriesOf(kind).length - 1) });
        }
      } else if (key === "a") {
        const entry = entriesOf(sel.kind)[sel.index];
        if (entry && entry.suggested_label) { wantAdvance = true; post("accept_suggestion"); }
      } else if (key === "r") {
        const entry = entriesOf(sel.kind)[sel.index];
        if (entry && entry.suggested_label) { wantAdvance = true; post("reject_suggestion"); }
      } else if (key === "e") {
        rename();
      } else if (key === "y") {
        confirmAxis();
      }
    });
  }

  // ---- refresh after every proposal POST (mirrors triage.js) --------------
  document.body.addEventListener("htmx:afterRequest", (evt) => {
    if (evt.detail.pathInfo && evt.detail.pathInfo.requestPath &&
        evt.detail.pathInfo.requestPath.includes(`/proposals/${proposalId}/`)) {
      fetch(`/proposals/${proposalId}/geometry`).then((r) => r.json()).then((g) => {
        geo = g;
        if (!geo.matrix) return;
        if (wantAdvance) {
          wantAdvance = false;
          // next entry still carrying a suggestion: forward in this panel,
          // then anywhere (firstPending), else stay put
          const entries = entriesOf(sel.kind);
          let next = null;
          for (let i = sel.index + 1; i < entries.length; i++) {
            if (entries[i].suggested_label) { next = { kind: sel.kind, index: i }; break; }
          }
          sel = next || firstPending(geo.matrix) || sel;
          companion = null;
        }
        redraw();
      });
    }
  });

  redraw();
}
