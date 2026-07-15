"""Geometry projection (FR-011/FR-012/FR-013a/FR-015) — projection ONLY.

Registered coordinates pass through verbatim: element bboxes were registered
in the VISUAL rotation-aware space pdfplumber reports (feature 003), PDF.js
renders in the same space, so the client multiplies by its zoom scale and
nothing here does rotation math (SC-007). Elements without coordinates fall
to panels — listed, never invented, never invisible.
"""

from __future__ import annotations

from pathlib import Path

import pdfplumber
from sqlalchemy.orm import Session

from rmu import store as blobstore
from rmu.mapping.approve import gate_state
from rmu.mapping.loader import parse_transform
from rmu.mapping.session import source_inventory
from rmu.mapping.start import load_session_state
from rmu.models import SourceProfile
from rmu.registry import get_template_by_id, required_fields, template_meta
from rmu.seed import profile_config

_OBSERVED_CAP = 12


def page_dimensions(pdf_path: Path) -> list[dict]:
    """Visual (post-rotation) page dims — what PDF.js will render."""
    with pdfplumber.open(pdf_path) as pdf:
        return [
            {"page": i, "width": float(p.width), "height": float(p.height)}
            for i, p in enumerate(pdf.pages, start=1)
        ]


def project_box(box: dict) -> dict:
    """Identity by design: the registered bbox IS the visual-space bbox."""
    return box


def observed_values(normalized: dict, key: str) -> list[str]:
    """Distinct observed values for a finding key, in first-seen order."""
    seen: dict[str, None] = {}
    for finding in normalized.get("findings", []):
        value = finding.get(key)
        values = value if isinstance(value, list) else [value]
        for v in values:
            if v is None or v == "":
                continue
            seen.setdefault(str(v), None)
    return list(seen)[:_OBSERVED_CAP]


def _source_panel(normalized: dict) -> list[dict]:
    inventory = source_inventory(normalized)
    panel = [
        {"key": f"header.{k}", "sample": v, "observed": []}
        for k, v in sorted(inventory["header"].items())
    ]
    panel += [
        {"key": f"finding.{k}", "sample": v,
         "observed": observed_values(normalized, k)}
        for k, v in sorted(inventory["finding"].items())
    ]
    return panel


def _source_boxes(profile_ref: str, dims: list[dict]) -> list[dict]:
    """Spatial anchors from the profile recipe, where the recipe has any
    (onboarded recipes carry record-table x-ranges/pages; the seed v2020
    profile is label-anchored — no coordinates, so no boxes)."""
    recipe = profile_config(profile_ref)
    boxes: list[dict] = []
    table = recipe.get("record_table") or {}
    x_ranges = table.get("x_ranges")
    page_no = table.get("page")
    if x_ranges and page_no:
        page = next((d for d in dims if d["page"] == page_no), None)
        height = page["height"] if page else 842.0
        columns = table.get("columns", [])
        for i, (x0, x1) in enumerate(x_ranges):
            name = columns[i] if i < len(columns) else f"col_{i}"
            boxes.append({"key": f"finding.{name.lower()}", "page": page_no,
                          "bbox": [x0, 0.0, x1, height], "label": name})
    for region in recipe.get("image_regions", []):
        if region.get("bbox") and region.get("page"):
            boxes.append({"key": region.get("name", "image"),
                          "page": region["page"],
                          "bbox": region["bbox"], "label": "image region"})
    return [project_box(b) for b in boxes]


def _target_view(template_row, meta: dict) -> dict:
    kind = meta["kind"]
    schema = template_row.required_schema
    if kind in ("pdf_form", "pdf_overlay"):
        pdf_sha = meta["pdf_object"]
        dims = page_dimensions(blobstore.get_path(pdf_sha))
        if kind == "pdf_overlay":
            boxes = [project_box({
                "field": r["target_field"], "page": r["page"],
                "bbox": r["bbox"], "label": r.get("label", r["target_field"]),
                "region_kind": r.get("kind", "text"),
            }) for r in meta["regions"]]
            panel = []
        else:
            # AcroForm fields register no coordinates — honest panel (FR-011)
            boxes = []
            panel = [{"field": f["target_field"],
                      "label": f.get("label", f["target_field"]),
                      "required": True}
                     for f in meta["fields"]]
        return {"kind": kind, "pdf_sha": pdf_sha, "pages": dims,
                "page_count": len(dims), "boxes": boxes, "panel": panel}

    required = list(schema.get("required", []))
    fields = (required + list(schema.get("optional", []))
              + list(schema.get("finding_fields", [])))
    panel = [{"field": f, "label": schema.get("field_labels", {}).get(f, f),
              "required": f in required} for f in fields]
    return {"kind": kind, "pdf_sha": None, "pages": [], "page_count": 0,
            "boxes": [], "panel": panel}


_STATE_BY_TIER = {"T0": "confirmed", "T1": "confirmed", "T2": "pending",
                  "T3": "missing"}


def link_projection(doc: dict) -> list[dict]:
    """Routes/constants/formulas/prompts as display links — derived per render,
    stored nowhere (data-model.md 'Mapping link')."""
    links: list[dict] = []
    for field, route in doc.get("routes", {}).items():
        tier = route.get("tier", "T3")
        links.append({
            "target_field": field, "mechanism": "route",
            "from": route.get("from"), "tier": tier,
            "state": _STATE_BY_TIER.get(tier, "missing"),
            "value_map": route.get("value_map"),
            "rationale": route.get("rationale", ""),
        })
    for field, value in doc.get("constants", {}).items():
        links.append({"target_field": field, "mechanism": "constant",
                      "from": repr(value), "tier": "T0", "state": "confirmed",
                      "value_map": None, "rationale": ""})
    for field, spec in doc.get("formulas", {}).items():
        links.append({"target_field": field, "mechanism": "formula",
                      "from": spec.get("fn"), "tier": "T0", "state": "confirmed",
                      "value_map": None, "rationale": ""})
    for prompt in doc.get("prompts", []):
        links.append({"target_field": prompt.get("target_field") or prompt["key"],
                      "mechanism": "prompt", "from": f"--answer {prompt['key']}=…",
                      "tier": "T0", "state": "confirmed", "value_map": None,
                      "rationale": prompt.get("label", "")})
    links.sort(key=lambda link: link["target_field"])
    for i, link in enumerate(links, start=1):
        link["tag"] = i
    return links


def _active_payload(element: dict) -> dict:
    return element.get("corrected_payload") or element.get("payload") or {}


_SPATIAL_KINDS = {"overlay_region", "image_region"}


def proposal_geometry(s: Session, proposal_id: int) -> dict:
    """Onboarding proposal projection (US4, FR-032/FR-032a).

    Spatially-anchored elements (bbox+page in the registered visual space) are
    drawn as overlays on every exemplar; non-spatial elements are listed with
    evidence, confidence and flags. Cross-exemplar agreement rides on each
    spatial element for the primary+switcher review (FR-032a)."""
    from rmu.onboard.proposal import Proposal

    proposal = Proposal.load(s, proposal_id)  # sync YAML→DB (interchangeable)
    document = proposal.document
    elements = document.get("elements", [])

    spatial: list[dict] = []
    non_spatial: list[dict] = []
    for e in elements:
        payload = _active_payload(e)
        bbox, page = payload.get("bbox"), payload.get("page")
        if e["element_kind"] in _SPATIAL_KINDS and bbox and page:
            spatial.append({
                "id": e["id"], "kind": e["element_kind"], "page": page,
                "bbox": bbox, "label": payload.get("label", e["id"]),
                "target_field": payload.get("target_field"),
                "review_state": e["review_state"],
                "confidence": e.get("confidence"),
                "source": e.get("evidence", {}).get("source", "heuristic"),
                "agreement": e.get("evidence", {}).get("cross_exemplar_agreement"),
                "flags": e.get("flags", []),
            })
        else:
            non_spatial.append({
                "id": e["id"], "element_kind": e["element_kind"],
                "review_state": e["review_state"],
                "confidence": e.get("confidence"),
                "evidence": e.get("evidence", {}),
                "flags": e.get("flags", []),
                "payload": payload,
            })

    exemplars = []
    for idx, sha in enumerate(proposal.row.exemplar_shas):
        try:
            dims = page_dimensions(blobstore.get_path(sha))
        except FileNotFoundError:
            dims = []
        exemplars.append({
            "index": idx, "sha": sha, "pages": dims, "page_count": len(dims),
            "primary": idx == 0, "boxes": [project_box(b) for b in spatial],
        })

    pending = proposal.unresolved()
    return {
        "proposal_id": proposal_id,
        "kind": proposal.kind,
        "status": proposal.status,
        "exemplars": exemplars,
        "spatial": spatial,
        "non_spatial": non_spatial,
        "pending": pending,
        "diagnosis": document.get("diagnosis"),
        "verify_report": proposal.row.verify_report,
    }


def session_geometry(s: Session, session_id: int) -> dict:
    """Everything the canvas needs, computed from the same artifacts the CLI
    reads: session row, draft file, extraction, registries."""
    import json

    ms, draft_path, doc_row = load_session_state(s, session_id)
    doc = parse_transform(draft_path.read_text(encoding="utf-8"))
    normalized = json.loads(blobstore.get_bytes(doc_row.extraction_ref))
    template_row = get_template_by_id(s, ms.target_template_id)
    profile_row = s.get(SourceProfile, ms.source_profile_id)
    profile_ref = f"{profile_row.key}@{profile_row.structural_version}"
    meta = template_meta(template_row)

    try:  # pre-004 sessions may not have the exemplar bytes in the store
        source_dims = page_dimensions(blobstore.get_path(doc_row.sha256))
        source_sha = doc_row.sha256
    except FileNotFoundError:
        source_dims, source_sha = [], None
    return {
        "session_id": session_id,
        "status": ms.status,
        "source": {
            "pdf_sha": source_sha,
            "filename": doc_row.original_filename,
            "profile": profile_ref,
            "pages": source_dims,
            "page_count": len(source_dims),
            "panel": _source_panel(normalized),
            "boxes": _source_boxes(profile_ref, source_dims),
        },
        "target": {**_target_view(template_row, meta),
                   "template": f"{template_row.name}@{template_row.version}"},
        "links": link_projection(doc),
        "gate": gate_state(doc, required_fields(template_row), s),
    }
