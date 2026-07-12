"""T008 — pdf_kind diagnosis ladder (research R7, FR-010) and cross-misuse
signals (FR-023). Every rejection names its condition AND a workaround."""

from __future__ import annotations

from pathlib import Path

from rmu.onboard.pdf_kind import diagnose, misuse_warning

FIX = Path("tests/fixtures/onboarding")


def test_form_pdf_diagnosed_as_form():
    d = diagnose(FIX / "target_form.pdf")
    assert d.kind == "form" and d.rejection is None


def test_fixed_layout_pdf_diagnosed():
    d = diagnose(FIX / "target_fixed.pdf")
    assert d.kind == "fixed_layout" and d.rejection is None


def test_structured_source_is_fixed_layout_kind():
    # a source report has a text layer and no form fields -> fixed_layout kind;
    # source-vs-target routing is the caller's business, not the ladder's
    assert diagnose(FIX / "survey_report_a.pdf").kind == "fixed_layout"


def test_encrypted_rejected_with_named_condition_and_workaround():
    d = diagnose(FIX / "target_encrypted.pdf")
    assert d.kind is None
    assert "encrypted" in d.rejection
    assert "unlocked" in d.workaround.lower()


def test_scanned_rejected_ocr_out_of_scope():
    d = diagnose(FIX / "scanned_only.pdf")
    assert d.kind is None
    assert "scanned" in d.rejection or "image-only" in d.rejection
    assert d.workaround  # actionable, not generic


def test_unparseable_rejected(tmp_path):
    junk = tmp_path / "junk.pdf"
    junk.write_bytes(b"this is not a pdf at all")
    d = diagnose(junk)
    assert d.kind is None and "not" in d.rejection.lower()


def test_xfa_rejected_with_flatten_workaround(tmp_path):
    # synthesize an XFA-marked AcroForm: take the real form and tag /XFA
    from pypdf import PdfReader, PdfWriter
    from pypdf.generic import ArrayObject, NameObject

    reader = PdfReader(FIX / "target_form.pdf")
    writer = PdfWriter(clone_from=reader)
    writer._root_object["/AcroForm"][NameObject("/XFA")] = ArrayObject()
    out = tmp_path / "xfa.pdf"
    with out.open("wb") as fh:
        writer.write(fh)

    d = diagnose(out)
    assert d.kind is None
    assert "XFA" in d.rejection
    assert "flatten" in d.workaround.lower() or "print" in d.workaround.lower()


def test_misuse_draft_profile_on_form_warns():
    warning = misuse_warning(FIX / "target_form.pdf", command="draft-profile")
    assert warning is not None and "draft-template" in warning


def test_misuse_draft_template_on_record_report_warns():
    warning = misuse_warning(FIX / "survey_report_a.pdf", command="draft-template")
    assert warning is not None and "draft-profile" in warning


def test_no_misuse_warning_on_matching_kinds():
    assert misuse_warning(FIX / "survey_report_a.pdf", command="draft-profile") is None
    assert misuse_warning(FIX / "target_form.pdf", command="draft-template") is None
    # fixed-layout target with no repeating records: fine for draft-template
    assert misuse_warning(FIX / "target_fixed.pdf", command="draft-template") is None
