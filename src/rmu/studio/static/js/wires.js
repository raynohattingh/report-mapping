/* Focus wire (FR-018): ONE bold wire for the hovered/selected link only —
   at rest the pairing lives in numbered tier-coloured tags. */

const SVG = "http://www.w3.org/2000/svg";
const TIER_COLOR = { T0: "#4ade80", T1: "#4ade80", T2: "#fbbf24", T3: "#f87171" };

export function clearWire() {
  const layer = document.getElementById("wire-layer");
  if (layer) layer.replaceChildren();
}

export function drawWire(fromEl, toEl, tier) {
  const layer = document.getElementById("wire-layer");
  if (!layer || !fromEl || !toEl) return;
  clearWire();
  const a = fromEl.getBoundingClientRect();
  const b = toEl.getBoundingClientRect();
  const x1 = a.right, y1 = a.top + a.height / 2;
  const x2 = b.left, y2 = b.top + b.height / 2;
  const mid = (x1 + x2) / 2;
  const path = document.createElementNS(SVG, "path");
  path.setAttribute("d", `M ${x1} ${y1} C ${mid} ${y1} ${mid} ${y2} ${x2} ${y2}`);
  path.setAttribute("fill", "none");
  path.setAttribute("stroke", TIER_COLOR[tier] || "#8b8cf8");
  path.setAttribute("stroke-width", "2.5");
  path.setAttribute("stroke-dasharray", tier === "T2" ? "6 4" : "");
  layer.appendChild(path);
}
