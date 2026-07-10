# NormalizedRecords Contract (profile `scopito.pdf.powerline.v2020`)

The Extract→Map/Apply boundary and the only contract a future v2 engine must meet
(Constitution VI). Per-profile, thin, no universal ontology (design §5). Stored as
JSON in the content-addressed store; referenced by `SourceDocument.extraction_ref`.

```json
{
  "schema": "rmu.normalized/1",
  "profile": "scopito.pdf.powerline@v2020",
  "source_sha256": "…",
  "header": {
    "inspection_name": "str",
    "report_date": "str (as printed; normalization is the transform's job)",
    "inspection_type": "str",
    "company": "str",
    "declared_counts": {"images": 0, "annotations": 0}
  },
  "findings": [
    {
      "id": "str",
      "severity": "1|2|3|4|5|? (A3; '?' = POI)",
      "user_tags": ["str"],
      "issues": ["str"],
      "comments": "str",
      "page": 0
    }
  ],
  "assets": [{"kind": "image", "page": 0, "ref": "str|null"}],
  "integrity": {
    "anchors_found": ["header_block", "severity_overview", "annotation_table"],
    "anchors_missing": [],
    "declared_vs_extracted": {"declared": 0, "extracted": 0}
  }
}
```

Rules:

- `integrity.anchors_missing` non-empty OR `declared ≠ extracted` ⇒ the document is
  drift-BLOCKED upstream of Apply (FR-016); Apply never sees it.
- Record-level parse failures appear as findings with a `parse_error` marker field and
  become per-record exceptions at apply time — the document still converts.
- All strings are extracted verbatim (trimmed); semantic conversion happens only via
  the transform's value maps/formulas, so Extract stays profile-specific *code* and
  Map/Apply stay data-driven (design §4).
