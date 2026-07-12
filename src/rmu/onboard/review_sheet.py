"""HTML review sheet for onboarding proposals (D1 pattern, FR-003).

Static, self-contained HTML the analyst opens NEXT TO the source PDF: one row
per proposed element with confidence, structural evidence, flags, and review
state. Editing happens in the draft YAML; this sheet is the eyeballing aid
(mirrors mapping/review_sheet.py's role for transforms).
"""

from __future__ import annotations

import html
from pathlib import Path

from rmu.store import drafts_dir

_STYLE = """
body{font-family:-apple-system,Segoe UI,sans-serif;margin:2rem;max-width:70rem}
table{border-collapse:collapse;width:100%}
td,th{border:1px solid #ccc;padding:.4rem .6rem;text-align:left;vertical-align:top}
th{background:#f0f0f0}
.state-proposed{background:#fff3cd}.state-confirmed{background:#d4edda}
.state-corrected{background:#cce5ff}.state-removed{background:#e2e3e5;color:#666}
.low{color:#b00;font-weight:600}.flag{color:#b00;font-size:.85em}
code{background:#f6f6f6;padding:0 .2em}
"""


def build_onboard_review_html(document: dict, *, proposal_id: int, title: str) -> str:
    rows = []
    for e in document.get("elements", []):
        conf = e["confidence"]
        conf_cls = ' class="low"' if conf < 0.5 else ""
        flags = ", ".join(e.get("flags", []))
        evidence = e.get("evidence", {})
        ev_text = ", ".join(
            f"{k}={v}" for k, v in evidence.items() if k != "source"
        )
        payload = html.escape(str(e.get("payload", {})))
        rows.append(
            f'<tr class="state-{e["review_state"]}">'
            f'<td><code>{html.escape(e["id"])}</code></td>'
            f'<td>{html.escape(e["element_kind"])}</td>'
            f"<td{conf_cls}>{conf:.2f}</td>"
            f"<td>{html.escape(ev_text)} ({html.escape(evidence.get('source', '?'))})</td>"
            f'<td class="flag">{html.escape(flags)}</td>'
            f'<td>{html.escape(e["review_state"])}</td>'
            f"<td>{payload}</td></tr>"
        )
    diagnosis = ""
    if document.get("diagnosis"):
        d = document["diagnosis"]
        diagnosis = (
            "<h2>Diagnosis</h2><p>"
            + html.escape(d.get("notes", ""))
            + "</p><p>searched: "
            + html.escape("; ".join(d.get("searched", [])))
            + "<br>found: "
            + html.escape("; ".join(d.get("found", [])))
            + "</p>"
        )
    return (
        "<!doctype html><meta charset='utf-8'>"
        f"<title>{html.escape(title)}</title><style>{_STYLE}</style>"
        f"<h1>{html.escape(title)}</h1>"
        f"<p>proposal #{proposal_id} - kind {html.escape(document['kind'])} - "
        "review each element against the actual PDF, then set its review_state "
        "in the draft YAML to confirmed / corrected (+corrected_payload) / removed. "
        "Approval is blocked while anything stays proposed (FR-003).</p>"
        + diagnosis
        + "<table><tr><th>id</th><th>kind</th><th>conf</th><th>evidence</th>"
        "<th>flags</th><th>state</th><th>payload</th></tr>"
        + "".join(rows)
        + "</table>"
    )


def write_sheet(document: dict, proposal_id: int) -> Path:
    path = drafts_dir() / f"onboard_{proposal_id}.html"
    path.write_text(
        build_onboard_review_html(
            document, proposal_id=proposal_id,
            title=f"Onboarding proposal #{proposal_id}",
        )
    )
    return path
