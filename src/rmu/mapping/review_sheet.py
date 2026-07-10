"""Static HTML review sheet (FR-006, D1/Option A): exemplar values, proposal,
rationale, decision state side-by-side. AI-proposed rows are visually distinct
from human-confirmed ones until accepted (Constitution V)."""

from __future__ import annotations

from jinja2 import Template

from rmu.apply.engine import ResolveError, resolve_path, to_text

_TEMPLATE = Template(
    """<!doctype html>
<html><head><meta charset="utf-8"><title>RMU mapping review — session {{ session_id }}</title>
<style>
 body { font-family: -apple-system, system-ui, sans-serif; margin: 2rem; }
 table { border-collapse: collapse; width: 100%; }
 th, td { border: 1px solid #ccc; padding: 6px 10px; text-align: left;
          vertical-align: top; font-size: 14px; }
 th { background: #f0f0f0; }
 .T0, .T1 { background: #e6f4e6; }           /* human-confirmed */
 .T2 { background: #fff3cd; font-style: italic; }  /* AI proposed — pending */
 .T3 { background: #f8d7da; }                 /* unmapped */
 .tier { font-weight: bold; font-family: monospace; }
 .mech { color: #555; font-family: monospace; font-size: 13px; }
 caption { text-align: left; font-size: 16px; font-weight: 600; padding-bottom: 8px; }
 .legend span { padding: 2px 8px; margin-right: 8px; border: 1px solid #ccc; }
</style></head><body>
<h1>Mapping review — session {{ session_id }} ({{ mode }})</h1>
<p>{{ profile }} &rarr; {{ template }} · exemplar: {{ exemplar }}</p>
<p class="legend">
 <span class="T0">human-confirmed (T0/T1)</span>
 <span class="T2">AI proposed — needs your decision (T2)</span>
 <span class="T3">unmapped (T3)</span>
</p>
<table>
<caption>Target fields</caption>
<tr><th>Target field</th><th>Mechanism</th><th>Exemplar value</th>
    <th>Tier</th><th>Rationale / note</th><th>Decision state</th></tr>
{% for row in rows %}
<tr class="{{ row.tier }}">
 <td><b>{{ row.field }}</b>{% if row.required %} *{% endif %}</td>
 <td class="mech">{{ row.mechanism }}</td>
 <td>{{ row.sample }}</td>
 <td class="tier">{{ row.tier }}</td>
 <td>{{ row.rationale }}</td>
 <td>{{ row.state }}</td>
</tr>
{% endfor %}
</table>
<p>* required by the target template. Approval is refused while any T2/T3 rows
remain or any required field is unrouted (FR-007).</p>
</body></html>
"""
)

_STATES = {
    "T0": "human-confirmed (deterministic)",
    "T1": "human-confirmed (validated, value-map backed)",
    "T2": "AI proposed — accept, edit or reject",
    "T3": "unmapped — add a route, constant, formula or prompt",
}


def _sample(mechanism_kind: str, spec, context: dict) -> str:
    if mechanism_kind == "route":
        try:
            return to_text(resolve_path(spec["from"], context))
        except ResolveError as err:
            return f"<<{err.reason}>>"
    if mechanism_kind == "constant":
        return to_text(spec)
    return "(computed)"


def build_review_html(
    session_id: int,
    mode: str,
    profile_ref: str,
    template_ref: str,
    exemplar_name: str,
    doc: dict,
    normalized: dict,
    required: list[str],
) -> str:
    context = {
        "header": normalized["header"],
        "finding": normalized["findings"][0] if normalized["findings"] else {},
    }
    rows = []
    for field, route in sorted(doc.get("routes", {}).items()):
        mech = f"route: {route['from']}"
        if route.get("value_map"):
            vm = route["value_map"]
            mech += f" via {vm['name']}@{vm['version']}"
        rows.append({
            "field": field, "mechanism": mech,
            "sample": _sample("route", route, context),
            "tier": route["tier"], "rationale": route.get("rationale", ""),
            "state": _STATES[route["tier"]], "required": field in required,
        })
    for field, value in sorted(doc.get("constants", {}).items()):
        rows.append({
            "field": field, "mechanism": "constant",
            "sample": _sample("constant", value, context), "tier": "T0",
            "rationale": "fixed value", "state": _STATES["T0"],
            "required": field in required,
        })
    for field, spec in sorted(doc.get("formulas", {}).items()):
        rows.append({
            "field": field, "mechanism": f"formula: {spec['fn']}",
            "sample": _sample("formula", spec, context), "tier": "T0",
            "rationale": "declared formula (closed set)", "state": _STATES["T0"],
            "required": field in required,
        })
    for prompt in doc.get("prompts", []):
        field = prompt.get("target_field") or prompt["key"]
        rows.append({
            "field": field, "mechanism": f"per-batch prompt: {prompt['key']}",
            "sample": "<<answered at batch launch>>", "tier": "T0",
            "rationale": prompt.get("label", ""), "state": _STATES["T0"],
            "required": field in required,
        })
    return _TEMPLATE.render(
        session_id=session_id, mode=mode, profile=profile_ref,
        template=template_ref, exemplar=exemplar_name, rows=rows,
    )
