/* PDF.js pane: lazy per-page rendering (FR-010, SC-010). Pages are created as
   placeholder holders at visual-point size and rendered on demand via
   IntersectionObserver; overlays attach per page through onPage(). */

import * as pdfjs from "/static/vendor/pdf.mjs";

pdfjs.GlobalWorkerOptions.workerSrc = "/static/vendor/pdf.worker.mjs";

const RENDER_WIDTH = 760; // CSS px target width per page

export async function mountPdfPane(container, sha, onPage, indicator) {
  const doc = await pdfjs.getDocument({ url: `/documents/${sha}/pdf` }).promise;
  const holders = [];

  for (let n = 1; n <= doc.numPages; n++) {
    const holder = document.createElement("div");
    holder.className = "page-holder";
    holder.dataset.page = n;
    container.appendChild(holder);
    holders.push(holder);
  }

  const rendered = new Set();
  async function renderPage(holder) {
    const n = Number(holder.dataset.page);
    if (rendered.has(n)) return;
    rendered.add(n);
    const page = await doc.getPage(n);
    const base = page.getViewport({ scale: 1 }); // visual points
    const scale = RENDER_WIDTH / base.width;
    const viewport = page.getViewport({ scale });
    const ratio = window.devicePixelRatio || 1;
    const canvas = document.createElement("canvas");
    canvas.width = viewport.width * ratio;
    canvas.height = viewport.height * ratio;
    canvas.style.width = `${viewport.width}px`;
    canvas.style.height = `${viewport.height}px`;
    holder.style.width = `${viewport.width}px`;
    holder.style.height = `${viewport.height}px`;
    holder.appendChild(canvas);
    await page.render({
      canvasContext: canvas.getContext("2d"),
      viewport,
      transform: ratio !== 1 ? [ratio, 0, 0, ratio, 0, 0] : null,
    }).promise;
    const layer = document.createElementNS("http://www.w3.org/2000/svg", "svg");
    layer.classList.add("overlay-layer");
    layer.setAttribute("width", viewport.width);
    layer.setAttribute("height", viewport.height);
    holder.appendChild(layer);
    if (onPage) onPage(n, holder, layer, scale);
  }

  const observer = new IntersectionObserver((entries) => {
    for (const entry of entries) {
      if (entry.isIntersecting) {
        renderPage(entry.target);
        if (indicator) indicator.textContent =
          `p.${entry.target.dataset.page}/${doc.numPages}`;
      }
    }
  }, { root: container.closest(".doc-pane"), rootMargin: "300px" });
  holders.forEach((h) => {
    h.style.minHeight = "300px"; // placeholder before first render
    observer.observe(h);
  });

  return {
    numPages: doc.numPages,
    jumpTo(pageNo) {
      const holder = holders[pageNo - 1];
      if (holder) {
        holder.scrollIntoView({ behavior: "smooth", block: "start" });
        renderPage(holder);
      }
    },
  };
}
