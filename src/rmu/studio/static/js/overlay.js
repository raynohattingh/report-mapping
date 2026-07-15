/* Element highlight layer: registered visual-space bboxes × zoom scale —
   the ONLY client-side coordinate math (SC-007; the server projects, never
   recomputes). Boxes carry tier classes and numbered tags (FR-018). */

const SVG = "http://www.w3.org/2000/svg";

export function drawBoxes(layer, scale, boxes, { tierOf, tagOf, onSelect, keyAttr }) {
  for (const box of boxes) {
    const [x0, top, x1, bottom] = box.bbox;
    const g = document.createElementNS(SVG, "g");
    const rect = document.createElementNS(SVG, "rect");
    rect.setAttribute("x", x0 * scale);
    rect.setAttribute("y", top * scale);
    rect.setAttribute("width", (x1 - x0) * scale);
    rect.setAttribute("height", (bottom - top) * scale);
    const tier = tierOf ? tierOf(box) : null;
    rect.setAttribute("class", `el-box ${tier ? `tier-${tier}` : "neutral"}`);
    rect.setAttribute("fill-opacity", "0.15");
    rect.dataset[keyAttr] = box.field || box.key;
    g.appendChild(rect);
    const tag = tagOf ? tagOf(box) : null;
    if (tag) {
      const badge = document.createElementNS(SVG, "text");
      badge.setAttribute("x", x1 * scale + 3);
      badge.setAttribute("y", top * scale + 8);
      badge.setAttribute("class", `badge tier-${tier}`);
      badge.setAttribute("font-size", "9");
      badge.textContent = tag;
      g.appendChild(badge);
    }
    if (onSelect) {
      g.style.cursor = "pointer";
      g.addEventListener("click", () => onSelect(box, rect));
    }
    layer.appendChild(g);
  }
}
