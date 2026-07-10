"""Detect stage: fingerprint a document against known SourceProfiles (FR-002).

Unknown shape -> None -> quarantine, never a guess (Constitution V/VI).
Anchors come from profile fingerprints (data), not code.
"""

from rmu.detect.fingerprint import detect_profile

__all__ = ["detect_profile"]
