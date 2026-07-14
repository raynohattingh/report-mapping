"""Shared word/line geometry over pdfplumber pages.

Used by the generic recipe engine (extract) and the onboarding heuristics
(onboard.analyze_source). Pipeline direction stays one-way: onboard imports
extract, never the reverse (Constitution VI).
"""

from __future__ import annotations

import pdfplumber

#: vertical tolerance (pt) for grouping words into one visual line
LINE_TOP_TOLERANCE = 2.5


def page_lines(page: pdfplumber.page.Page) -> list[dict]:
    """Group a page's words into visual lines, top-to-bottom.

    Returns [{top, words: [word,...], text}] with words sorted left-to-right.
    """
    lines: list[dict] = []
    for word in sorted(page.extract_words(), key=lambda w: (w["top"], w["x0"])):
        target = None
        for line in lines:
            if abs(line["top"] - word["top"]) <= LINE_TOP_TOLERANCE:
                target = line
                break
        if target is None:
            target = {"top": word["top"], "words": []}
            lines.append(target)
        target["words"].append(word)
    for line in lines:
        line["words"].sort(key=lambda w: w["x0"])
        line["text"] = " ".join(w["text"] for w in line["words"])
    lines.sort(key=lambda line: line["top"])
    return lines


def assign_columns(words: list[dict], x_ranges: list[list[float]]) -> list[str]:
    """Distribute a line's words into column cells by x-range membership.

    A word belongs to the column whose [x0, x1) range contains its start;
    words outside every range are dropped (page furniture right of the table,
    image thumbnails, etc.). Multi-word cells join with single spaces.
    """
    cells = ["" for _ in x_ranges]
    for word in words:
        for i, (lo, hi) in enumerate(x_ranges):
            if lo <= word["x0"] < hi:
                cells[i] = f"{cells[i]} {word['text']}".strip() if cells[i] else word["text"]
                break
    return cells
