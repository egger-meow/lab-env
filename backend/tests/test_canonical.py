"""Tests for canonical JSON serialization and hashing."""

import json
import pytest
from preference_lab.domain.canonical import (
    canonical_json_bytes,
    canonical_json_str,
    sha256_canonical_json,
)


def test_canonical_json_key_sorting():
    obj1 = {"b": 2, "a": 1, "c": {"y": 20, "x": 10}}
    obj2 = {"a": 1, "c": {"x": 10, "y": 20}, "b": 2}
    assert canonical_json_str(obj1) == canonical_json_str(obj2)
    assert canonical_json_str(obj1) == '{"a":1,"b":2,"c":{"x":10,"y":20}}'


def test_canonical_json_unicode_preservation():
    obj = {"message": "鑰匙在星星左邊", "symbol": "🌙"}
    s = canonical_json_str(obj)
    assert "鑰匙在星星左邊" in s
    assert "🌙" in s
    assert "\\u" not in s


def test_canonical_json_crlf_vs_lf_string_invariance():
    # If two strings have different newline styles inside a field, json represents them differently,
    # but parsing a json object from CRLF vs LF files produces the identical dict in Python.
    raw_lf = '{\n  "b": 2,\n  "a": 1\n}\n'
    raw_crlf = '{\r\n  "b": 2,\r\n  "a": 1\r\n}\r\n'
    dict_lf = json.loads(raw_lf)
    dict_crlf = json.loads(raw_crlf)
    assert sha256_canonical_json(dict_lf) == sha256_canonical_json(dict_crlf)


def test_canonical_json_rejects_nan_and_inf():
    with pytest.raises(ValueError, match="NaN and Infinity"):
        canonical_json_str({"val": float("nan")})

    with pytest.raises(ValueError, match="NaN and Infinity"):
        canonical_json_str({"val": float("inf")})


def test_sha256_canonical_hash_stability():
    payload = {"k": 20, "r": 1, "N": 100}
    h = sha256_canonical_json(payload)
    assert isinstance(h, str)
    assert len(h) == 64
    # Repeat produces exact same hash
    assert sha256_canonical_json(payload) == h
