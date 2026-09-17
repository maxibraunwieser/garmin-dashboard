#!/usr/bin/env python3
"""
crypto_store.py -- encrypt the Garmin data so it can sit on a public web host.

The dashboard page decrypts it in the browser with the passphrase you type; the
server only ever holds ciphertext. Same scheme both ways:

    PBKDF2-HMAC-SHA256, 300000 iterations -> 256-bit key -> AES-256-GCM

Used by make_dashboard.py and by the GitHub Action. Standalone:

    python crypto_store.py encrypt garmin/data.json docs/data.enc
    python crypto_store.py decrypt docs/data.enc garmin/data.json

The passphrase comes from the DASH_PASSPHRASE environment variable and is never
written anywhere.
"""

import base64
import hashlib
import json
import os
import sys

ITERATIONS = 300000
SALT_BYTES = 16
IV_BYTES = 12


def _aesgcm():
    try:
        from cryptography.hazmat.primitives.ciphers.aead import AESGCM
    except ImportError:
        sys.exit("The cryptography library is missing. Run:  pip install -r requirements.txt")
    return AESGCM


def passphrase():
    pw = os.environ.get("DASH_PASSPHRASE")
    if pw:
        pw = pw.strip().lstrip("﻿")   # BOM/Zeilenumbruch aus dem Secret entfernen
    if not pw:
        sys.exit("DASH_PASSPHRASE is not set. Without it nothing can be encrypted or read back.")
    if len(pw) < 8:
        sys.exit("DASH_PASSPHRASE is shorter than 8 characters. Pick something longer.")
    return pw


def derive_key(pw, salt):
    return hashlib.pbkdf2_hmac("sha256", pw.encode("utf-8"), salt, ITERATIONS, dklen=32)


def encrypt_obj(obj, pw):
    """Return a JSON-safe envelope the browser can decrypt with WebCrypto."""
    AESGCM = _aesgcm()
    salt = os.urandom(SALT_BYTES)
    iv = os.urandom(IV_BYTES)
    plaintext = json.dumps(obj, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    ciphertext = AESGCM(derive_key(pw, salt)).encrypt(iv, plaintext, None)
    return {
        "v": 1,
        "kdf": "PBKDF2-SHA256",
        "iterations": ITERATIONS,
        "salt": base64.b64encode(salt).decode(),
        "iv": base64.b64encode(iv).decode(),
        "data": base64.b64encode(ciphertext).decode(),
    }


def decrypt_obj(envelope, pw):
    AESGCM = _aesgcm()
    salt = base64.b64decode(envelope["salt"])
    iv = base64.b64decode(envelope["iv"])
    ciphertext = base64.b64decode(envelope["data"])
    key = derive_key(pw, salt) if envelope.get("iterations", ITERATIONS) == ITERATIONS else \
        hashlib.pbkdf2_hmac("sha256", pw.encode("utf-8"), salt, envelope["iterations"], dklen=32)
    plaintext = AESGCM(key).decrypt(iv, ciphertext, None)
    return json.loads(plaintext.decode("utf-8"))


def main():
    if len(sys.argv) != 4 or sys.argv[1] not in ("encrypt", "decrypt"):
        sys.exit("Usage: python crypto_store.py encrypt|decrypt <in> <out>")
    mode, src, dst = sys.argv[1], sys.argv[2], sys.argv[3]
    pw = passphrase()

    if mode == "encrypt":
        if not os.path.exists(src):
            sys.exit("Nothing to encrypt: {} does not exist.".format(src))
        with open(src, "r", encoding="utf-8") as fh:
            obj = json.load(fh)
        out = encrypt_obj(obj, pw)
    else:
        if not os.path.exists(src):
            print("{} does not exist yet -- nothing to decrypt, starting fresh.".format(src))
            return
        with open(src, "r", encoding="utf-8") as fh:
            out = decrypt_obj(json.load(fh), pw)

    parent = os.path.dirname(os.path.abspath(dst))
    if parent:
        os.makedirs(parent, exist_ok=True)
    with open(dst, "w", encoding="utf-8") as fh:
        json.dump(out, fh, ensure_ascii=False)
    print("{}ed {} -> {}".format(mode, src, dst))


if __name__ == "__main__":
    main()
