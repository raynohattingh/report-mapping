# QUARANTINED — SC-001 acceptance fixtures only

Files in this directory are held-out acceptance fixtures for feature 003
(spec SC-001). They are NEVER read, opened, parsed, or referenced by any
development code, test, fixture builder, or tuning activity. The only
legitimate consumer is the human-run acceptance protocol
(scripts/acceptance_003.md, task T034).

Do not add globs that sweep this directory. tests/invariants/test_quarantine.py
enforces that no repo code references these files.
