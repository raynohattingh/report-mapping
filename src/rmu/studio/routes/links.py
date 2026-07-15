"""Link detail & value mapping (US3, FR-020/FR-021/FR-022) — thin delegates.

Detail shows the exemplar's observed values for the route's source element with
unmapped values conspicuous; the value-map editor stages into the draft file
and Register & pin appends a registry version + pins the route; constants,
formulas and per-batch prompts are written as the schema already defines them.
"""

from __future__ import annotations

import json

from fastapi import APIRouter, Form, Request

from rmu import store as blobstore
from rmu.mapping.loader import TransformValidationError, parse_transform
from rmu.mapping.start import load_session_state
from rmu.registry import create_value_map, load_value_maps
from rmu.studio import draftedit, valuemaps
from rmu.studio.app import DomainRefusal
from rmu.studio.concurrency import content_hash
from rmu.studio.geometry import observed_values
from rmu.studio.routes.common import db_session, lease, render

router = APIRouter()


def _parse_yaml(text: str, what: str):
    """Parse analyst-supplied YAML → a clean 422 on a typo, never a 500."""
    import yaml

    try:
        return yaml.safe_load(text)
    except yaml.YAMLError as err:
        raise DomainRefusal(f"invalid {what}",
                            [f"not valid YAML: {err}"]) from err


def _load(s, session_id: int):
    try:
        return load_session_state(s, session_id)
    except LookupError as err:
        raise DomainRefusal("unknown session", [str(err)]) from err


def _require_draft(ms) -> None:
    if ms.status != "draft":
        raise DomainRefusal(
            "session is read-only",
            [f"refused: session {ms.id} is {ms.status} (terminal)"],
        )


def _mutate(request: Request, session_id: int, base_hash: str, overwrite, mutate):
    with db_session() as s:
        ms, draft_path, _ = _load(s, session_id)
        _require_draft(ms)
        try:
            draftedit.apply_doc_edit(lease(request), draft_path, base_hash,
                                     mutate, overwrite=overwrite)
        except draftedit.RouteEditError as err:
            raise DomainRefusal("edit refused", [str(err)]) from err
        except TransformValidationError as err:
            raise DomainRefusal("draft is not schema-valid", err.errors) from err


@router.get("/sessions/{session_id}/links/{field}")
def link_detail(request: Request, session_id: int, field: str):
    with db_session() as s:
        ms, draft_path, doc_row = _load(s, session_id)
        doc = parse_transform(draft_path.read_text(encoding="utf-8"))
        normalized = json.loads(blobstore.get_bytes(doc_row.extraction_ref))
        route = doc.get("routes", {}).get(field, {})
        source_from = route.get("from", "")
        source_key = source_from.split(".")[-1] if source_from else ""
        observed = observed_values(normalized, source_key) if source_key else []

        vm_ref = route.get("value_map")
        name = vm_ref["name"] if vm_ref else valuemaps.suggest_name(source_from, field)
        staged = valuemaps.load_staged(session_id, name)
        if not staged and vm_ref:
            registry = load_value_maps(s, doc).get((vm_ref["name"], vm_ref["version"]))
            staged = list(registry) if registry else []
        _, draft_hash = lease(request).load(draft_path)

    mapped = {str(e["source_value"]) for e in staged}
    unmapped = [v for v in observed if v not in mapped]
    return render(request, "fragments/link_detail.html", session_id=session_id,
                  field=field, source_from=source_from, observed=observed,
                  unmapped=unmapped, entries=staged, vm_name=name,
                  read_only=ms.status != "draft", draft_hash=draft_hash)


@router.post("/sessions/{session_id}/links/{field}/valuemap")
def stage_valuemap(request: Request, session_id: int, field: str,
                   name: str = Form(...),
                   source_value: list[str] = Form(default=[]),
                   target_value: list[str] = Form(default=[]),
                   provenance: list[str] = Form(default=[])):
    """Stage entries in the draft value-map file — NO registry write (FR-021)."""
    with db_session() as s:
        ms, _, _ = _load(s, session_id)
        _require_draft(ms)
    entries = valuemaps.entries_from_parallel(source_value, target_value, provenance)
    valuemaps.stage_entries(session_id, name, entries)
    return render(request, "fragments/valuemap_staged.html", session_id=session_id,
                  field=field, vm_name=name, entries=entries)


@router.post("/sessions/{session_id}/links/{field}/valuemap/register")
def register_valuemap(request: Request, session_id: int, field: str,
                      name: str = Form(...), base_hash: str = Form(...),
                      overwrite: bool = Form(False)):
    """Register & pin: append a new ValueMap version, pin name@version (FR-021).

    The draft-conflict check runs BEFORE the registry write: a stale/changed
    draft aborts with a 409 and NO ValueMap version is created, so the expected
    FR-005 conflict path (and its retry) can never orphan or duplicate registry
    versions — one create per successful register, matching the CLI (FR-003).
    """
    entries = valuemaps.load_staged(session_id, name)
    if not entries:
        raise DomainRefusal("nothing to register",
                            [f"no staged entries for value map {name!r}"])
    with db_session() as s:
        ms, draft_path, _ = _load(s, session_id)
        _require_draft(ms)
        # Pre-check the lease so a conflict aborts before any registry INSERT.
        current_hash = content_hash(draft_path.read_text(encoding="utf-8"))
        if current_hash != base_hash and not overwrite:
            # Reuse the conflict machinery (409 + diff, reload/overwrite).
            lease(request).apply_edit(draft_path, base_hash, lambda t: t)
        try:
            version = create_value_map(s, name, entries)
        except ValueError as err:
            raise DomainRefusal("value map rejected", [str(err)]) from err

    _mutate(request, session_id, base_hash, overwrite,
            lambda doc: draftedit.pin_value_map(doc, field, name, version))
    with db_session() as s:
        from rmu.studio.geometry import session_geometry

        geo = session_geometry(s, session_id)
    return render(request, "fragments/canvas_update.html", session_id=session_id,
                  links=geo["links"], gate=geo["gate"], state="",
                  read_only=False,
                  draft_hash=_draft_hash(request, session_id))


@router.post("/sessions/{session_id}/links/{field}/mechanism")
def set_mechanism(request: Request, session_id: int, field: str,
                  mechanism: str = Form(...), base_hash: str = Form(...),
                  value: str = Form(""), spec: str = Form(""),
                  key: str = Form(""), label: str = Form(""),
                  required: bool = Form(True), overwrite: bool = Form(False)):
    parsed_spec = None
    if mechanism == "formula":
        parsed_spec = _parse_yaml(spec, "formula spec")

    def mutate(doc: dict) -> None:
        if mechanism == "constant":
            draftedit.set_constant(doc, field, value)
        elif mechanism == "formula":
            draftedit.set_formula(doc, field, parsed_spec)
        elif mechanism == "prompt":
            draftedit.set_prompt(doc, field, key or field, label, required)
        else:
            raise draftedit.RouteEditError(f"unknown mechanism '{mechanism}'")

    _mutate(request, session_id, base_hash, overwrite, mutate)
    with db_session() as s:
        from rmu.studio.geometry import session_geometry

        geo = session_geometry(s, session_id)
    return render(request, "fragments/canvas_update.html", session_id=session_id,
                  links=geo["links"], gate=geo["gate"], state="", read_only=False,
                  draft_hash=_draft_hash(request, session_id))


def _draft_hash(request: Request, session_id: int) -> str:
    with db_session() as s:
        _, draft_path, _ = _load(s, session_id)
    _, digest = lease(request).load(draft_path)
    return digest
