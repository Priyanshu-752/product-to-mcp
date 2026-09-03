from __future__ import annotations

import base64
import hashlib
from typing import Protocol


class SecretPersistence(Protocol):
    def put_secret(self, project_id: str, encrypted_value: str | None) -> None: ...
    def get_secret(self, project_id: str) -> str | None: ...


class PrototypeSecretStore:
    """Process-local prototype secret store.

    Values are intentionally not persisted in SQLite or returned in DTOs.
    Production must replace this with KMS/Vault-backed storage.
    """

    def __init__(self) -> None:
        self._values: dict[str, str] = {}

    def put(self, reference: str, value: str | None) -> None:
        if value:
            self._values[reference] = value

    def get(self, reference: str) -> str | None:
        return self._values.get(reference)


class DatabaseSecretStore:
    def __init__(self, persistence: SecretPersistence, encryption_key: str) -> None:
        from cryptography.fernet import Fernet

        key = base64.urlsafe_b64encode(hashlib.sha256(encryption_key.encode()).digest())
        self.persistence = persistence
        self.fernet = Fernet(key)

    def put(self, reference: str, value: str | None) -> None:
        if not value:
            self.persistence.put_secret(reference, None)
            return
        encrypted = self.fernet.encrypt(value.encode()).decode()
        self.persistence.put_secret(reference, encrypted)

    def get(self, reference: str) -> str | None:
        encrypted = self.persistence.get_secret(reference)
        if encrypted is None:
            return None
        return self.fernet.decrypt(encrypted.encode()).decode()
