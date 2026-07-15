/* Spatial region editing (FR-033a): drag/resize a proposed region records a
   correction; drawing a new region posts an analyst-sourced element. All
   coordinates convert from rendered pixels to the registered VISUAL space by
   dividing by the page's zoom scale (the inverse of overlay.js) — the only
   client-side coordinate math besides the highlight projection. */

const SVG = "http://www.w3.org/2000/svg";
const root = document.getElementById("triage-root");

if (root && !root.dataset.readOnly) {
  const proposalId = root.dataset.proposalId;
  let drawing = null;

  window.__regionsHook = (pageNo, holder, layer, scale, exemplar) => {
    layer.style.pointerEvents = "auto";
    layer.addEventListener("mousedown", (evt) => {
      if (evt.target !== layer) return; // empty space → draw a new region
      const origin = localPoint(evt, layer);
      const rect = document.createElementNS(SVG, "rect");
      rect.setAttribute("class", "el-box neutral");
      rect.setAttribute("x", origin.x); rect.setAttribute("y", origin.y);
      layer.appendChild(rect);
      drawing = { rect, origin, scale, pageNo };
    });
    layer.addEventListener("mousemove", (evt) => {
      if (!drawing) return;
      const p = localPoint(evt, layer);
      const x = Math.min(p.x, drawing.origin.x), y = Math.min(p.y, drawing.origin.y);
      drawing.rect.setAttribute("x", x); drawing.rect.setAttribute("y", y);
      drawing.rect.setAttribute("width", Math.abs(p.x - drawing.origin.x));
      drawing.rect.setAttribute("height", Math.abs(p.y - drawing.origin.y));
    });
    layer.addEventListener("mouseup", () => {
      if (!drawing) return;
      const { rect, scale, pageNo } = drawing;
      const bbox = [
        Number(rect.getAttribute("x")) / scale,
        Number(rect.getAttribute("y")) / scale,
        (Number(rect.getAttribute("x")) + Number(rect.getAttribute("width"))) / scale,
        (Number(rect.getAttribute("y")) + Number(rect.getAttribute("height"))) / scale,
      ].map((n) => Math.round(n * 10) / 10);
      drawing = null;
      const field = prompt("target field for the new region:");
      if (!field) { rect.remove(); return; }
      const payload = { bbox, kind: "text", label: field, page: pageNo,
                        target_field: field };
      window.htmx.ajax("POST", `/proposals/${proposalId}/elements`, {
        values: { element_kind: "overlay_region",
                  payload: toYaml(payload) },
        target: "#triage-root", swap: "none",
      });
    });
  };

  // rename via keyboard 'E' → correction with a new target_field
  window.__renameElement = (elementId) => {
    const geo = window.__proposalGeo;
    const el = (geo.spatial || []).find((e) => e.id === elementId);
    if (!el) return;
    const name = prompt("rename target field:", el.target_field || el.label);
    if (!name) return;
    const payload = { bbox: el.bbox, kind: "text", label: name, page: el.page,
                      target_field: name };
    window.htmx.ajax("POST", `/proposals/${proposalId}/elements/${elementId}`, {
      values: { action: "correct", payload: toYaml(payload) },
      target: "#triage-root", swap: "none",
    });
  };
}

function localPoint(evt, layer) {
  const box = layer.getBoundingClientRect();
  return { x: evt.clientX - box.left, y: evt.clientY - box.top };
}

function toYaml(obj) {
  // minimal flow-style YAML the server parses with yaml.safe_load
  return JSON.stringify(obj);
}
