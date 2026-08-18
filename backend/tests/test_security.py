import pytest

from app.security import (
    create_access_token,
    decode_token,
    hash_password,
    verify_password,
)


def test_hash_and_verify_password():
    hashed = hash_password("secret123")
    assert hashed != "secret123"
    assert verify_password("secret123", hashed) is True
    assert verify_password("wrong", hashed) is False


def test_token_roundtrip():
    token = create_access_token(1, "sv")
    payload = decode_token(token)
    assert payload["sub"] == "1"
    assert payload["role"] == "sv"


def test_decode_invalid_token():
    with pytest.raises(Exception):
        decode_token("not-a-token")
