"""Document-kind diagnosis ladder (research R7) + cross-misuse signals.

First match wins: unparseable → encrypted → XFA → form → fixed-layout →
scanned. Every rejection names the specific condition and a practical
workaround (FR-010) — never a generic failure, never a best-effort proposal
from a partially readable file. Deterministic and cheap: metadata plus
first-pages text only. Uses pypdf + pdfplumber (D10).
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from pathlib import Path

import pdfplumber
from pypdf import PdfReader

#: pages scanned for text/record signals (matches detect.fingerprint.SCAN_PAGES spirit)
SCAN_PAGES = 4
#: lines sharing one x-signature that make a document "record-like" (FR-023)
RECORD_LINES_THRESHOLD = 5


@dataclass(frozen=True)
class Diagnosis:
    kind: str | None  # 'form' | 'fixed_layout' | None (rejected)
    rejection: str | None = None
    workaround: str | None = None
    detail: str = ""


def diagnose(pdf_path: Path) -> Diagnosis:
    pdf_path = Path(pdf_path)
    try:
        reader = PdfReader(pdf_path)
        if reader.is_encrypted:
            return Diagnosis(
                kind=None,
                rejection="encrypted or password-protected PDF",
                workaround="obtain an unlocked copy from the document owner",
                detail="pypdf reports is_encrypted",
            )
        root = reader.trailer["/Root"]
        acroform = root.get("/AcroForm")
        if acroform is not None and "/XFA" in acroform:
            return Diagnosis(
                kind=None,
                rejection="XFA (LiveCycle) form - not a standard AcroForm",
                workaround=(
                    "flatten it (print-to-PDF) and onboard the result as a "
                    "fixed-layout target, or request an AcroForm version"
                ),
                detail="/AcroForm carries /XFA",
            )
        if reader.get_fields():
            return Diagnosis(kind="form", detail=f"{len(reader.get_fields())} AcroForm fields")
    except Exception as exc:  # unreadable / not a PDF
        return Diagnosis(
            kind=None,
            rejection="not a parseable PDF",
            workaround="check the file is a PDF export, not a rename or a partial download",
            detail=str(exc)[:200],
        )

    has_text = False
    has_images = False
    with pdfplumber.open(pdf_path) as pdf:
        for page in pdf.pages[:SCAN_PAGES]:
            if (page.extract_text() or "").strip():
                has_text = True
                break
            if page.images:
                has_images = True
    if has_text:
        return Diagnosis(kind="fixed_layout", detail="text layer present, no form fields")
    if has_images:
        return Diagnosis(
            kind=None,
            rejection="scanned/image-only PDF - no machine-readable text layer",
            workaround=(
                "OCR is out of scope (A10); obtain the digital export from the "
                "source tool instead of a scan"
            ),
            detail="pages contain images but no extractable text",
        )
    return Diagnosis(
        kind=None,
        rejection="PDF contains no text and no images",
        workaround="check the export produced actual content",
    )


def _looks_record_like(pdf_path: Path) -> bool:
    """Cheap FR-023 signal: many lines sharing one multi-column x-signature."""
    signatures: Counter[tuple[int, ...]] = Counter()
    with pdfplumber.open(pdf_path) as pdf:
        for page in pdf.pages[:SCAN_PAGES]:
            lines: dict[int, list[float]] = {}
            for word in page.extract_words():
                lines.setdefault(round(word["top"]), []).append(word["x0"])
            for xs in lines.values():
                if len(xs) >= 4:  # multi-column line
                    signatures[tuple(round(x / 10) for x in sorted(xs)[:6])] += 1
    return any(count >= RECORD_LINES_THRESHOLD for count in signatures.values())


def misuse_warning(pdf_path: Path, *, command: str) -> str | None:
    """Warn when the document strongly resembles the OTHER command's kind
    (FR-023). Caller proceeds only with an explicit --force."""
    diag = diagnose(pdf_path)
    if command == "draft-profile" and diag.kind == "form":
        return (
            "this PDF is a fillable form - it looks like a TARGET format, not a "
            "source report; did you mean 'rmu onboard draft-template'? "
            "(--force to analyse it as a source anyway)"
        )
    if command == "draft-template" and diag.kind == "fixed_layout" and _looks_record_like(pdf_path):
        return (
            "this PDF carries repeating record rows - it looks like a SOURCE "
            "report, not a target format; did you mean 'rmu onboard draft-profile'? "
            "(--force to analyse it as a target anyway)"
        )
    return None
