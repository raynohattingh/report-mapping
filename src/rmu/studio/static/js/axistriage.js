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

   Band geometry: each criterion/tower's `band` is the union bbox
   ([x0, y0, x1, y1], same registered visual-space coords overlay.js draws
   in) of ONLY that entry's own cells — never a full-width/full-height band.
   On /Rotate 90|270 pages (the real Eskom case) a logical row renders as a
   narrow VERTICAL strip and a logical column as a narrow HORIZONTAL strip,
   so a full-axis band would smear across unrelated rows/columns; the client
   just multiplies the union bbox by the page's zoom scale and draws that
   rect (SC-007) — no orientation assumption anywhere in this file.
   Pages render lazily: we chain onto window.__regionsHook (called by triage.js
   for every page it mounts) WITHOUT clobbering regions.js's editor. */

const SVG = "http://www.w3.org/2000/svg";
const root = document.getElementById("triage-root");
const rail = document.getElementById("axis-rail");
if (root && rail) initAxisTriage(root);

function initAxisTriage(root) {
  const proposalId = root.dataset.proposalId;
  const readOnly = Boolean(root.dataset.readOnly);
  let geo = null; // set once the geometry fetch resolves; guards all handlers

  const layers = new Map(); // pageNo -> { layer, scale } (current mount only)
  // selection: primary cursor + optional companion (cell click focuses BOTH
  // its criterion and tower rows); companion clears on any cursor move.
  let sel = null;
  let companion = null;
  let wantAdvance = false;

  // ---- lazy-page hook: chain, never replace (regions.js registered first).
  // Installed SYNCHRONOUSLY, before the geometry fetch: triage.js mounts the
  // PDF independently and pages mount exactly once, so a wrapper installed
  // after an await could miss early pages (fast/cached PDFs) — losing their
  // band-layer registration and cell-click listener. Geometry-dependent work
  // (cellClick, redraw) is deferred via the `geo` guard instead. ------------
  const prior = window.__regionsHook;
  window.__regionsHook = (pageNo, holder, layer, scale, exemplar) => {
    if (prior) prior(pageNo, holder, layer, scale, exemplar);
    layers.set(pageNo, { layer, scale });
    layer.addEventListener("click", (evt) => cellClick(evt, pageNo, layer, scale));
    if (geo && geo.matrix) redraw();
  };

  fetch(`/proposals/${proposalId}/geometry`).then((r) => r.json()).then((g) => {
    if (!g.matrix) return; // geo stays null — every handler stays inert
    geo = g;
    sel = firstPending(geo.matrix) || { kind: "criteria", index: 0 };
    redraw(); // pages that mounted before the fetch resolved get their band now
  });

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
    if (!entry || !entry.page || !entry.band) return null;
    const axis = pick.kind === "criteria" ? "row" : "col";
    return { page: entry.page, axis, band: entry.band };
  }
  function drawBand(pick) {
    const b = bandFor(pick);
    if (!b) return;
    const mounted = layers.get(b.page);
    if (!mounted) return; // page not rendered yet — hook will redraw on mount
    const { layer, scale } = mounted;
    const rect = document.createElementNS(SVG, "rect");
    const [x0, y0, x1, y1] = b.band;
    rect.setAttribute("x", x0 * scale);
    rect.setAttribute("y", y0 * scale);
    rect.setAttribute("width", (x1 - x0) * scale);
    rect.setAttribute("height", (y1 - y0) * scale);
    rect.setAttribute("class", b.axis === "row" ? "axis-band" : "axis-band col");
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
    if (!sel) return; // geometry not loaded yet
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
    if (!geo || !geo.matrix) return; // listener attaches pre-fetch; inert until then
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
    if (!geo || !geo.matrix) return;
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
      if (!geo || !geo.matrix || !sel) return;
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
        if (!sel) sel = firstPending(geo.matrix) || { kind: "criteria", index: 0 };
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
}
