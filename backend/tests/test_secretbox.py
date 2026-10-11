import base64

import pytest
from cryptography.exceptions import InvalidTag

from fantasy.core import secretbox


@pytest.fixture(autouse=True)
def _key(monkeypatch):
    monkeypatch.setenv("WEB_CRYPTO_KEY", base64.b64encode(b"\x01" * 32).decode())


def test_round_trip():
    token = "Bearer eyJhbGciOi.test.value-123"
    enc = secretbox.encrypt(token)
    assert enc.startswith("v1:")
    assert secretbox.decrypt(enc) == token


def test_rejects_tampered_payload():
    enc = secretbox.encrypt("secret")
    tampered = "v1:" + base64.b64encode(base64.b64decode(enc[3:])[:-1] + b"\x00").decode()
    with pytest.raises((InvalidTag, ValueError)):
        secretbox.decrypt(tampered)


def test_bad_prefix():
    with pytest.raises(ValueError):
        secretbox.decrypt("nope")
