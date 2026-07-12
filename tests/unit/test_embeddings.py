"""T008: embeddings availability probe + batch embed (cache-only, offline)."""

import pytest

from rmu.ai.embeddings import EmbeddingBackend, EmbeddingUnavailable

MODEL = "BAAI/bge-small-en-v1.5"


def _has_model() -> bool:
    return EmbeddingBackend(MODEL).available()


pytestmark = pytest.mark.skipif(
    not _has_model(), reason="bge-small cache not warmed (run `rmu ai setup`)"
)


def test_available_true_when_cached():
    assert EmbeddingBackend(MODEL).available() is True


def test_embed_returns_fixed_dim_vectors():
    vecs = EmbeddingBackend(MODEL).embed(["severity", "priority"])
    assert len(vecs) == 2
    assert len(vecs[0]) == 384
    assert all(isinstance(x, float) for x in vecs[0])


def test_embed_is_deterministic():
    a = EmbeddingBackend(MODEL).embed(["comments"])[0]
    b = EmbeddingBackend(MODEL).embed(["comments"])[0]
    assert a == b


def test_bogus_model_unavailable_and_never_downloads():
    backend = EmbeddingBackend("BAAI/does-not-exist-xyz")
    assert backend.available() is False
    with pytest.raises(EmbeddingUnavailable):
        backend.embed(["x"])
