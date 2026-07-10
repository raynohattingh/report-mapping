from rmu import store


def test_put_get_roundtrip(tmp_path, monkeypatch):
    monkeypatch.setenv("RMU_STORE", str(tmp_path))
    sha = store.put_bytes(b"hello findings")
    assert store.get_bytes(sha) == b"hello findings"
    assert store.get_path(sha).exists()
    assert sha == store.sha256_bytes(b"hello findings")


def test_write_once_dedupes(tmp_path, monkeypatch):
    monkeypatch.setenv("RMU_STORE", str(tmp_path))
    a = store.put_bytes(b"same")
    b = store.put_bytes(b"same")
    assert a == b
    objects = list((tmp_path / "objects").rglob("*"))
    files = [p for p in objects if p.is_file()]
    assert len(files) == 1
