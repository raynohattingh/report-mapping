"""Local AI assistance layer (feature 002, D8).

Everything model-shaped lives here and is used ONLY by the mapping session and
its CLI commands. No pipeline stage (apply/detect/extract/validate/render) may
import this package — enforced by tests/invariants/test_no_ai_in_apply.py.

Tiers (D8): (1) in-process CPU embeddings for field-route ranking and profile
fingerprint similarity, (2) optional loopback-only local LLM for value-map
proposals, (3) external API opt-in, consent-gated. AI never runs at apply time
(Constitution II).
"""
