"""Asset/runtime health for `rmu ai doctor` (FR-014, quickstart.md).

Probes each tier without downloading anything and reports per-tier verdicts,
including whether the local model runtime is bound to loopback (FR-002). Pure
reporting — never mutates config or state.
"""

from __future__ import annotations

SETUP_STEPS = """Local AI assistance — manual setup (nothing is downloaded automatically):

1. Python deps:            uv sync
2. Warm the embedding cache (~130MB, one-time, needs network):
     uv run python -c "from fastembed import TextEmbedding; \\
       TextEmbedding('BAAI/bge-small-en-v1.5')"
3. (Optional) local LLM for value-map proposals:
     brew install ollama        # or https://ollama.com
     ollama pull qwen3:4b       # A12b; fallback: ollama pull gemma3:4b
4. Verify:                  uv run rmu ai doctor

External mode (only with recorded per-client consent):
     uv run rmu ai consent grant --client <id> --by <owner>
"""


def health(config) -> dict:
    """Per-tier health report. Constructs the backends offline; never downloads."""
    from rmu.ai.embeddings import EmbeddingBackend
    from rmu.ai.llm_local import LocalLLM
    from rmu.onboard.axis_providers import LocalVisionInterpreter

    eb = EmbeddingBackend(config.embedding_model)
    emb_ok = eb.available()

    llm = LocalLLM(config.ollama_host, config.llm_model, config.timeout_seconds)
    llm_ok = llm.available()

    # Matrix interpret (feature 005) reuses the configured local LLM slot as
    # its vision model — probed separately since a text-only model pulled for
    # value-map proposals won't necessarily serve vision (FR-011 per-tier).
    vision = LocalVisionInterpreter(config.ollama_host, config.llm_model, config.timeout_seconds)
    vision_ok = vision.available()

    return {
        "default_mode": config.default_mode,
        "embedding": {
            "model": config.embedding_model,
            "ok": emb_ok,
            "reason": None if emb_ok else eb.reason,
        },
        "llm": {
            "model": config.llm_model,
            "host": config.ollama_host,
            "loopback_bound": llm.loopback,
            "ok": llm_ok,
            "reason": None if llm_ok else llm.reason,
        },
        "vision": {
            "model": config.llm_model,
            "host": config.ollama_host,
            "loopback_bound": vision.loopback,
            "ok": vision_ok,
            "reason": None if vision_ok else vision.reason,
            "label": "vision (matrix interpret)",
        },
        "consent_clients": [e.get("client") for e in config.consent],
    }
