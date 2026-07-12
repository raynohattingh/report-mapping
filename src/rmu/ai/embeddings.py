"""Tier-1 embeddings: in-process CPU vectors via fastembed (A12a, research R1).

Runs entirely in-process (ONNX) — no sockets at all, which is stronger than the
loopback allowance and keeps ranking working even when no model runtime is
installed. Forced into Hugging Face **offline** mode so a missing model is
reported as unavailable rather than silently downloaded at session time
(FR-014): the availability probe constructs the model under `local_files_only`,
succeeding only if the cache is already warmed by the documented setup step.
"""

from __future__ import annotations

import os

# FR-002/FR-014: this module must never reach the network. Force offline BEFORE
# fastembed/huggingface_hub are imported (they read these at construction time).
os.environ.setdefault("HF_HUB_OFFLINE", "1")
os.environ.setdefault("TRANSFORMERS_OFFLINE", "1")


class EmbeddingUnavailable(RuntimeError):
    """Raised if embed() is called when the model/cache is not available."""


class EmbeddingBackend:
    """Lazy fastembed wrapper. `available()` is cache-only (never downloads)."""

    def __init__(self, model_name: str, cache_dir: str | None = None):
        self.model_name = model_name
        self._cache_dir = cache_dir
        self._model = None
        self._probe_error: str | None = None

    def _construct(self):
        # Belt-and-braces: enforce offline even if something reset the env.
        os.environ["HF_HUB_OFFLINE"] = "1"
        os.environ["TRANSFORMERS_OFFLINE"] = "1"
        from fastembed import TextEmbedding

        return TextEmbedding(self.model_name, cache_dir=self._cache_dir)

    def available(self) -> bool:
        """True iff fastembed is importable AND the model is cached locally."""
        if self._model is not None:
            return True
        try:
            self._model = self._construct()
            return True
        except Exception as err:  # ImportError, missing cache, corrupt files
            self._probe_error = f"{type(err).__name__}: {err}"
            return False

    def embed(self, texts: list[str]) -> list[list[float]]:
        """Embed a batch of short strings. Deterministic on fixed model files."""
        if self._model is None and not self.available():
            raise EmbeddingUnavailable(
                f"embedding model {self.model_name!r} unavailable "
                f"({self._probe_error}); run `rmu ai setup`"
            )
        return [[float(x) for x in vec] for vec in self._model.embed(list(texts))]

    @property
    def reason(self) -> str | None:
        return self._probe_error
