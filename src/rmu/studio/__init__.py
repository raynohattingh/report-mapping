"""Mapping Studio (feature 004, D6/D9/D11): strictly-local web front-end.

The studio owns ZERO business logic — every route delegates to the exact code
paths the CLI uses and produces identical stored artifacts (FR-001). It is a
deletable subpackage: no pipeline/mapping/onboard/apply/render module may
import it (tests/invariants/test_no_studio_in_core.py), its Python deps live
in the optional `studio` dependency group, and removing the package leaves the
full suite green (FR-042).

This __init__ intentionally imports nothing heavyweight: `rmu.cli` probes it
lazily, and fastapi may be absent (core install).
"""
