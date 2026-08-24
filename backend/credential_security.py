from __future__ import annotations

from binascii import Error as BinasciiError
import json
from functools import lru_cache
from typing import TypedDict

from cryptography.fernet import Fernet, InvalidToken

from backend.config import get_settings


class CredentialPayload(TypedDict):
    api_key: str
    api_base: str | None


class CredentialDecryptionError(RuntimeError):
    """Raised when stored provider credentials cannot be decrypted."""


class CredentialCipher:
    def __init__(self, encryption_key: str) -> None:
        try:
            self._fernet = Fernet(encryption_key.encode("ascii"))
        except (BinasciiError, TypeError, UnicodeError, ValueError) as exc:
            raise ValueError(
                "CREDENTIAL_ENCRYPTION_KEY must be a valid Fernet key"
            ) from exc

    def encrypt(self, payload: CredentialPayload) -> str:
        serialized = json.dumps(
            payload,
            ensure_ascii=False,
            separators=(",", ":"),
            sort_keys=True,
        ).encode("utf-8")
        return self._fernet.encrypt(serialized).decode("ascii")

    def decrypt(self, encrypted_payload: str) -> CredentialPayload:
        try:
            serialized = self._fernet.decrypt(encrypted_payload.encode("ascii"))
            payload = json.loads(serialized.decode("utf-8"))
            api_key = payload["api_key"]
            api_base = payload.get("api_base")
            if not isinstance(api_key, str) or not api_key:
                raise ValueError("Missing API key")
            if api_base is not None and not isinstance(api_base, str):
                raise ValueError("Invalid API base URL")
            return {"api_key": api_key, "api_base": api_base}
        except (InvalidToken, UnicodeError, json.JSONDecodeError, KeyError, ValueError) as exc:
            raise CredentialDecryptionError(
                "Stored provider credential cannot be decrypted"
            ) from exc


def key_hint(api_key: str) -> str:
    visible = api_key[-4:] if len(api_key) >= 4 else api_key
    return f"••••{visible}"


@lru_cache
def get_credential_cipher() -> CredentialCipher:
    settings = get_settings()
    return CredentialCipher(
        settings.credential_encryption_key.get_secret_value()
    )
