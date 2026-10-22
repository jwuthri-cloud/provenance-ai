"""Prompt-at-rest encryption (AEAD via Fernet).

Prompts may carry secrets, so they are encrypted at rest from M1 — a stolen
db.sqlite yields only ciphertext. The key lives at TRACE_HOME/vault.key (0600).
In M2+ the key is wrapped by the OS keychain (KEK/DEK); for M1 it is a local
0600 file. Only `prompt_excerpt` is encrypted; code content is stored plaintext
in the local, git-ignored hot DB.
"""
from __future__ import annotations

from pathlib import Path

from cryptography.fernet import Fernet


def _load_or_create_key(key_path: Path) -> bytes:
    if key_path.exists():
        return key_path.read_bytes()
    key_path.parent.mkdir(parents=True, exist_ok=True)
    key = Fernet.generate_key()
    key_path.write_bytes(key)
    try:
        key_path.chmod(0o600)
    except OSError:
        pass
    return key


class Vault:
    def __init__(self, key_path: Path) -> None:
        self._fernet = Fernet(_load_or_create_key(key_path))

    def encrypt(self, text: str | None) -> bytes | None:
        if text is None:
            return None
        return self._fernet.encrypt(text.encode("utf-8"))

    def decrypt(self, token: bytes | None) -> str | None:
        if not token:
            return None
        try:
            return self._fernet.decrypt(token).decode("utf-8")
        except Exception:
            return None
