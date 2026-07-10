from rmu.render.csv import render_csv


def test_deterministic_bytes_lf_utf8_no_bom():
    rows = [
        {"a": "x", "b": "coté", "c": "has,comma"},
        {"a": "y", "b": "", "c": 'quote"inside'},
    ]
    out = render_csv(rows, ["a", "b", "c"])
    assert out == render_csv(rows, ["a", "b", "c"])  # byte-stable
    assert not out.startswith(b"\xef\xbb\xbf")  # no BOM
    assert b"\r\n" not in out  # LF only
    text = out.decode("utf-8")
    assert text.splitlines()[0] == "a,b,c"
    assert '"has,comma"' in text


def test_extra_and_missing_keys_are_stable():
    rows = [{"a": "1", "zz": "ignored"}, {"b": "2"}]
    text = render_csv(rows, ["a", "b"]).decode()
    assert text == "a,b\n1,\n,2\n"
