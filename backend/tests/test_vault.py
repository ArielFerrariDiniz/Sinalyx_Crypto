import json

import pytest

from app.models import Credentials
from app.services.vault import CURRENT_SCHEMA, LEGACY_SCHEMA, SecretServiceVault, VaultError
from conftest import CREDENTIALS


class Item:
    def __init__(self, attributes, secret):
        self.attributes = attributes
        self.secret = secret
        self.deleted = False

    def get_secret(self):
        return self.secret

    def delete(self):
        self.deleted = True


class Collection:
    collection_path = "/org/freedesktop/secrets/collection/login"

    def __init__(self):
        self.items = []
        self.locked = False

    def is_locked(self):
        return self.locked

    def search_items(self, attributes):
        return [item for item in self.items if not item.deleted and all(item.attributes.get(key) == value for key, value in attributes.items())]

    def create_item(self, _label, attributes, secret, replace, content_type):
        if replace:
            for item in self.search_items(attributes):
                item.delete()
        assert content_type == "application/json"
        item = Item(attributes.copy(), secret)
        self.items.append(item)
        return item


@pytest.fixture
def collection(monkeypatch):
    current = Collection()

    class Bus:
        def close(self):
            pass

    monkeypatch.setattr("app.services.vault.secretstorage.dbus_init", Bus)
    monkeypatch.setattr("app.services.vault.secretstorage.check_service_availability", lambda _bus: True)
    monkeypatch.setattr("app.services.vault.secretstorage.get_collection_by_alias", lambda _bus, _alias: current)
    return current


def test_credentials_round_trip_only_through_secret_service_and_delete_legacy(collection):
    vault = SecretServiceVault()
    credentials = Credentials(**CREDENTIALS)
    legacy = Item(vault.legacy_attributes, b"old encrypted record")
    collection.items.append(legacy)

    vault.write(credentials)

    saved = collection.search_items(vault.attributes)
    assert len(saved) == 1 and saved[0].attributes["schema"] == CURRENT_SCHEMA
    assert CREDENTIALS == json.loads(saved[0].get_secret())
    assert all(value not in str(saved[0].attributes) for value in CREDENTIALS.values())
    assert legacy.deleted
    assert vault.read() == credentials

    vault.delete()
    assert vault.read() is None


def test_previous_app_envelope_is_not_read_as_credentials(collection):
    vault = SecretServiceVault()
    legacy = Item(vault.legacy_attributes, b"old encrypted record")
    assert legacy.attributes["schema"] == LEGACY_SCHEMA
    collection.items.append(legacy)

    assert vault.read() is None
    vault.delete()
    assert legacy.deleted


def test_secretservice_failure_is_sanitized(monkeypatch):
    def unavailable():
        raise RuntimeError(str(CREDENTIALS))

    monkeypatch.setattr("app.services.vault.secretstorage.dbus_init", unavailable)
    with pytest.raises(VaultError) as caught:
        SecretServiceVault().read()
    assert caught.value.code == "vault_unavailable"
    assert all(secret not in str(caught.value) for secret in CREDENTIALS.values())


@pytest.mark.parametrize("cancelled", [False, True])
def test_vault_unlock_uses_system_prompt_without_app_password(collection, cancelled):
    calls = []

    def unlock(*, timeout):
        calls.append(timeout)
        if cancelled:
            raise TimeoutError()
        collection.locked = False

    collection.locked = True
    collection.unlock = unlock
    if cancelled:
        with pytest.raises(VaultError) as caught:
            SecretServiceVault().unlock()
        assert caught.value.code == "vault_locked"
    else:
        SecretServiceVault().unlock()
        assert collection.locked is False
    assert calls == [45]
