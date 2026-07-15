/* Studio shell wiring — no business logic (FR-001): auth header for HTMX
   mutations (FR-040a) and the FR-005 conflict-dialog actions. */

const tokenMeta = document.querySelector('meta[name="studio-token"]');
const studioToken = tokenMeta ? tokenMeta.content : "";

let lastRequest = null; // {verb, path, params} of the most recent mutation

document.body.addEventListener("htmx:configRequest", (evt) => {
  evt.detail.headers["X-Studio-Token"] = studioToken;
  if (evt.detail.verb && evt.detail.verb.toUpperCase() !== "GET") {
    lastRequest = {
      verb: evt.detail.verb,
      path: evt.detail.path,
      parameters: { ...evt.detail.parameters },
    };
  }
});

/* 409 conflict fragments are legitimate swap targets (FR-005), as are 422
   refusals and 503 busy fragments — show them instead of dropping them. */
document.body.addEventListener("htmx:beforeSwap", (evt) => {
  if ([409, 422, 503].includes(evt.detail.xhr.status)) {
    evt.detail.shouldSwap = true;
    evt.detail.isError = false;
  }
});

/* Conflict dialog: reload-latest or overwrite-with-mine (never silent). */
document.body.addEventListener("click", (evt) => {
  const button = evt.target.closest("[data-action]");
  if (!button) return;
  if (button.dataset.action === "reload") {
    location.reload();
  } else if (button.dataset.action === "overwrite" && lastRequest) {
    const params = { ...lastRequest.parameters, overwrite: "true" };
    window.htmx.ajax(lastRequest.verb, lastRequest.path, {
      values: params,
      target: "#workspace-flash",
      swap: "innerHTML",
    });
  }
});
