"""Credenciais armazenadas somente no Secret Service do usuário Linux."""

import json
import os
from contextlib import closing, contextmanager

import secretstorage
from secretstorage.exceptions import ItemNotFoundException, PromptDismissedException

from ..models import Credentials

CURRENT_SCHEMA = "binance-credentials-v2"
LEGACY_SCHEMA = "encrypted-v1"


class VaultError(Exception):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code
        self.message = message


class SecretServiceVault:
    def __init__(self):
        identity = {"application": "crypto-trading-bot", "uid": str(os.getuid())}
        self.attributes = {**identity, "schema": CURRENT_SCHEMA}
        self.legacy_attributes = {**identity, "schema": LEGACY_SCHEMA}

    @contextmanager
    def collection(self, prompt=False):
        try:
            with closing(secretstorage.dbus_init()) as bus:
                if not secretstorage.check_service_availability(bus):
                    raise VaultError("vault_unavailable", "Secret Service indisponível. Ative o cofre do Linux na sua sessão gráfica.")
                try:
                    collection = secretstorage.get_collection_by_alias(bus, "default")
                except ItemNotFoundException:
                    raise VaultError("vault_unavailable", "Crie um cofre padrão persistente no gerenciador de senhas do Linux e tente novamente.") from None
                if collection.collection_path.endswith("/session"):
                    raise VaultError("vault_unavailable", "O cofre padrão é temporário. Configure um cofre persistente no gerenciador de senhas do Linux.")
                if collection.is_locked():
                    if not prompt:
                        raise VaultError("vault_locked", "O cofre do Linux está bloqueado. Desbloqueie-o pela janela segura do sistema.")
                    try:
                        collection.unlock(timeout=45)
                    except (TimeoutError, PromptDismissedException):
                        raise VaultError("vault_locked", "O desbloqueio foi cancelado ou não terminou. Tente novamente na janela do sistema.") from None
                if collection.is_locked():
                    raise VaultError("vault_locked", "O cofre continua bloqueado. Conclua o desbloqueio na janela do sistema.")
                yield collection
        except VaultError:
            raise
        except Exception:
            raise VaultError("vault_unavailable", "Não foi possível acessar o cofre Secret Service. Verifique sua sessão gráfica ou tente desbloqueá-lo novamente.") from None

    def unlock(self):
        with self.collection(prompt=True):
            pass

    def read(self) -> Credentials | None:
        with self.collection() as collection:
            items = list(collection.search_items(self.attributes))
            if len(items) > 1:
                raise VaultError("vault_invalid", "Existem registros duplicados no cofre. Verifique o item Crypto Trading Bot no gerenciador de senhas do Linux.")
            if not items:
                return None
            try:
                payload = json.loads(items[0].get_secret())
                return Credentials.model_validate(payload)
            except Exception:
                raise VaultError("vault_invalid", "As credenciais salvas no cofre estão inválidas. Reconecte a conta Binance.") from None

    def write(self, credentials: Credentials):
        payload = json.dumps({
            "api_key": credentials.api_key.get_secret_value(),
            "secret_key": credentials.secret_key.get_secret_value(),
        }, separators=(",", ":")).encode("utf-8")
        with self.collection() as collection:
            collection.create_item(
                "Crypto Trading Bot — conexão Binance somente leitura",
                self.attributes, payload, replace=True, content_type="application/json",
            )
            # Registros da versão anterior eram cifrados por uma senha do app que
            # não era persistida. Após salvar as chaves novas no cofre, remova-os.
            for item in collection.search_items(self.legacy_attributes):
                item.delete()

    def delete(self):
        with self.collection() as collection:
            for attributes in (self.attributes, self.legacy_attributes):
                for item in collection.search_items(attributes):
                    item.delete()
