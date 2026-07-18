"""Onboarding draft creation — the single write path for both surfaces (D6).

Extracted from the `rmu onboard draft-profile` / `draft-template` Typer bodies
(feature 004, research.md R4). Rejections and kind-misuse warnings raise typed
errors carrying the exact CLI text (FR-037: same messages on both surfaces);
rejection occurrences are logged to store/onboard_rejections.jsonl for either
surface (FR-010 follow-up data).
"""

from __future__ import annotations

import datetime
import json
from dataclasses import dataclass
from pathlib import Path

from sqlalchemy.orm import Session

from rmu.config import store_root


class OnboardRejected(RuntimeError):
    """Unsupported PDF kind — named condition + workaround (FR-023 ladder)."""

    def __init__(self, rejection: str, workaround: str):
        self.rejection = rejection
        self.workaround = workaround
        super().__init__(rejection)


class KindMisuse(RuntimeError):
    """Document-kind warning; proceed only with an explicit force (FR-023)."""

    def __init__(self, warning: str):
        self.warning = warning
        super().__init__(warning)


@dataclass
class DraftOutcome:
    proposal_id: int
    kind: str                # profile | template
    draft_path: Path
    sheet_path: Path
    document: dict
    pdf_kind: str | None = None  # form | overlay (template drafts)


def log_rejection(diag, pdf: Path) -> None:
    """Append the rejection occurrence so unsupported formats become
    follow-up data, not lost terminal output (moved from onboard/cli.py)."""
    entry = {
        "file": str(pdf),
        "condition": diag.rejection,
        "workaround": diag.workaround,
        "at": datetime.datetime.now(datetime.UTC).isoformat(timespec="seconds"),
    }
    with (store_root() / "onboard_rejections.jsonl").open("a") as fh:
        fh.write(json.dumps(entry, sort_keys=True) + "\n")


def _gate(pdf: Path, command: str, force: bool):
    """Shared reject/misuse ladder. Returns the diagnosis on success."""
    from rmu.onboard.pdf_kind import diagnose, misuse_warning

    diag = diagnose(pdf)
    if diag.kind is None:
        log_rejection(diag, pdf)
        raise OnboardRejected(diag.rejection, diag.workaround)
    warning = misuse_warning(pdf, command=command)
    if warning and not force:
        raise KindMisuse(warning)
    return diag


def _local_llm():
    """Best-effort 002-layer local model; None => enrichment silently skipped."""
    try:
        from rmu.ai.config import load_ai_config
        from rmu.ai.llm_local import LocalLLM

        cfg = load_ai_config(store_root())
        return LocalLLM(cfg.ollama_host, cfg.llm_model, cfg.timeout_seconds)
    except Exception:
        return None


def _axis_interpreter(no_ai: bool):
    """Best-effort feature-005 AxisInterpreter for the matrix interpret stage.

    Mirrors `_local_llm`'s degrade-not-raise contract: `--no-ai` -> None
    (interpret silently skipped, deterministic axes stand); otherwise resolve
    the `local` tier via `resolve_axis_interpreter` (loopback Ollama vision
    model, `ai.yaml`'s dedicated `vision_model` slot) — unavailable local
    runtime/model degrades to None, never raises. `external` is not offered
    here (matrix onboarding has no `--client`/`--assist` surface yet; the
    template-only external tier stays a later wiring), so a `ConsentRequired`
    can only arise if that changes — caught defensively and degraded to None
    rather than aborting the whole draft.
    """
    if no_ai:
        return None
    from rmu.ai.config import load_ai_config
    from rmu.onboard.axis_providers import ConsentRequired, resolve_axis_interpreter

    try:
        cfg = load_ai_config(store_root())
        return resolve_axis_interpreter("local", cfg, client=None)
    except ConsentRequired:
        return None


def draft_profile_proposal(
    s: Session,
    paths: list[Path],
    *,
    no_ai: bool = False,
    seed_from: str = "",
    force: bool = False,
) -> DraftOutcome:
    """Analyse unrecognised source PDF(s) into a draft profile proposal."""
    import pdfplumber

    from rmu import store
    from rmu.onboard.analyze_source import analyze
    from rmu.onboard.enrich import enrich_document
    from rmu.onboard.proposal import Proposal
    from rmu.onboard.review_sheet import write_sheet
    from rmu.onboard.skeleton import attach_diagnosis, is_structureless

    for p in paths:
        if not p.exists():
            raise FileNotFoundError(f"error: no such file {p}")
    _gate(paths[0], "draft-profile", force)

    seed_row = None
    seed_profile = None
    if seed_from:
        from rmu.registry import get_profile
        from rmu.seed import profile_config

        seed_row = get_profile(s, seed_from)  # LookupError carries the message
        # FR-021: pass the seeding recipe so the proposal is annotated as
        # a delta (seed_match evidence / seed_divergent flags)
        seed_profile = {"ref": seed_from, "recipe": profile_config(seed_from)}

    for p in paths:
        store.put_file(p)  # exemplars retrievable at verify-on-approve
    document = analyze(paths, seed_profile=seed_profile)

    if not no_ai:
        llm = _local_llm()
        if llm is not None:
            with pdfplumber.open(paths[0]) as pdf:
                page_texts = [pg.extract_text() or "" for pg in pdf.pages]
            document = enrich_document(document, page_texts, llm=llm)

    if is_structureless(document):
        attach_diagnosis(document)  # FR-001b: never a dead end

    proposal = Proposal.create(
        s, document,
        seeded_from_profile_id=seed_row.id if seed_row else None,
    )
    sheet = write_sheet(document, proposal.id)
    return DraftOutcome(
        proposal_id=proposal.id, kind="profile",
        draft_path=proposal.draft_path(), sheet_path=Path(sheet),
        document=document,
    )


def draft_template_proposal(
    s: Session,
    pdf: Path,
    *,
    no_ai: bool = False,
    force: bool = False,
) -> DraftOutcome:
    """Analyse a target-format PDF into a draft template proposal."""
    from rmu import store
    from rmu.onboard.analyze_target import analyze
    from rmu.onboard.proposal import Proposal
    from rmu.onboard.review_sheet import write_sheet

    if not pdf.exists():
        raise FileNotFoundError(f"error: no such file {pdf}")
    diag = _gate(pdf, "draft-template", force)

    store.put_file(pdf)  # the template PDF itself becomes the pdf_object
    document = analyze(pdf, kind=diag.kind)

    matrix_pages = sorted({
        e["evidence"]["pages"][0]
        for e in document["elements"]
        if e["element_kind"] in ("row_axis", "col_axis")
    })
    if matrix_pages:
        interpreter = _axis_interpreter(no_ai)
        if interpreter is not None:
            from rmu.onboard.interpret_matrix import apply_interpretation
            from rmu.onboard.matrix import extract_grids, render_page_images

            grids = extract_grids(pdf)
            # page image (vision tier): pdfplumber's own Pillow-backed
            # renderer works with already-installed deps (design "Model
            # substrate" vision tier), so pass the real render rather than
            # None; any per-page render failure just omits that page's
            # image (see render_page_images), degrading that page to the
            # text-grid-only prompt path.
            images = render_page_images(pdf, set(matrix_pages))
            document, dropped = apply_interpretation(document, grids, interpreter, images)
            document["ai_assist"] = {"mode": "local", "dropped": dropped}

    proposal = Proposal.create(s, document)
    sheet = write_sheet(document, proposal.id)
    return DraftOutcome(
        proposal_id=proposal.id, kind="template",
        draft_path=proposal.draft_path(), sheet_path=Path(sheet),
        document=document, pdf_kind=diag.kind,
    )
