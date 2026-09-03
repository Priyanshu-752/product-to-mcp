from __future__ import annotations


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

