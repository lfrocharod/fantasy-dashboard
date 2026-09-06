"""AES-256-GCM, wire-compatible with the web app's lib/crypto.ts.

Encoded form: "v1:" + base64(iv[12] || tag[16] || ciphertext).
Key: 32 raw bytes, base64-encoded, in env var WEB_CRYPTO_KEY.
"""

from __future__ import annotations

import base64
import os

from cryptography.hazmat.primitives.ciphers.aead import AESGCM

_PREFIX = "v1:"


def _key() -> bytes:
    raw = os.environ.get("WEB_CRYPTO_KEY", "")
    if not raw:
        raise RuntimeError("WEB_CRYPTO_KEY not set")
    key = base64.b64decode(raw)
    if len(key) != 32:
        raise RuntimeError("WEB_CRYPTO_KEY must decode to 32 bytes")
    return key


def decrypt(payload: str) -> str:
    if not payload.startswith(_PREFIX):
        raise ValueError("unrecognised secret payload")
    blob = base64.b64decode(payload[len(_PREFIX) :])
    iv, tag, ct = blob[:12], blob[12:28], blob[28:]
    pt = AESGCM(_key()).decrypt(iv, ct + tag, None)
    return pt.decode("utf-8")


def encrypt(plaintext: str) -> str:
    iv = os.urandom(12)
    ct_with_tag = AESGCM(_key()).encrypt(iv, plaintext.encode("utf-8"), None)
    ct, tag = ct_with_tag[:-16], ct_with_tag[-16:]
    return _PREFIX + base64.b64encode(iv + tag + ct).decode("ascii")
