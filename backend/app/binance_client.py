"""Somente GETs explicitamente permitidos; nunca recebe uma URL do usuário."""

import hashlib
import hmac
import logging
import math
import time
from urllib.parse import urlencode

import httpx
from pydantic import TypeAdapter, ValidationError

from .models import Account, Credentials, ExchangeInfo, Ticker

# O httpx pode registrar URLs assinadas em INFO; não registrar tráfego financeiro.
for logger_name in ("httpx", "httpcore", "secretstorage", "jeepney"):
    logger = logging.getLogger(logger_name)
    logger.disabled = True
    logger.setLevel(logging.CRITICAL + 1)
    logger.propagate = False
    logger.addHandler(logging.NullHandler())


class BinanceError(Exception):
    def __init__(self, code: str, message: str, status: int = 502, retry_after: int | None = None):
        super().__init__(message)
        self.code = code
        self.message = message
        self.status = status
        self.retry_after = retry_after


def invalid_response() -> BinanceError:
    return BinanceError("invalid_response", "A Binance retornou dados inesperados. Tente atualizar novamente.")


class BinanceClient:
    PUBLIC_PATHS = frozenset({"/api/v3/time", "/api/v3/ticker/price", "/api/v3/exchangeInfo"})
    SIGNED_PATHS = frozenset({"/api/v3/account", "/sapi/v1/account/apiRestrictions"})

    def __init__(self, http: httpx.AsyncClient):
        self.http = http
        self._cooldown_until = 0.0

    async def _get(self, path: str, params=None, headers=None):
        if path not in self.PUBLIC_PATHS | self.SIGNED_PATHS:
            raise ValueError("Endpoint não permitido.")
        remaining = math.ceil(self._cooldown_until - time.monotonic())
        if remaining > 0:
            raise BinanceError("rate_limit", f"Limite da Binance atingido. Aguarde {remaining} segundos.", 429, remaining)
        try:
            response = await self.http.get(path, params=params, headers=headers)
        except httpx.TimeoutException:
            raise BinanceError("timeout", "A Binance demorou para responder. Tente novamente.", 504) from None
        except httpx.RequestError:
            raise BinanceError("connection_error", "Não foi possível comunicar com a Binance. Verifique sua conexão.", 502) from None
        try:
            data = response.json()
        except ValueError:
            data = None
        code = data.get("code") if isinstance(data, dict) else None
        if response.status_code in (418, 429) or code == -1003:
            try:
                wait = max(1, int(response.headers.get("Retry-After", "60")))
            except ValueError:
                wait = 60
            self._cooldown_until = time.monotonic() + wait
            raise BinanceError("rate_limit", f"Limite da Binance atingido. Aguarde {wait} segundos.", 429, wait)
        if code == -1007:
            raise BinanceError("timeout", "A Binance demorou para responder. Tente novamente.", 504)
        if response.status_code >= 500 or code in (-1000, -1001, -1006, -1008, -1016):
            raise BinanceError("unavailable", "A Binance está temporariamente indisponível. Tente mais tarde.", 503)
        if code == -1021:
            raise BinanceError("time_sync", "Não foi possível sincronizar o horário com a Binance. Verifique a rede e o relógio do sistema.")
        if code == -1022:
            raise BinanceError("invalid_signature", "Falha de assinatura. Confira a Secret Key e se ela pertence à API Key informada.", 400)
        if code == -2014:
            raise BinanceError("invalid_api_key", "API Key inválida. Confira a chave informada.", 400)
        if code == -2015:
            raise BinanceError("key_or_permission", "API Key inválida, IP não autorizado ou permissão de leitura insuficiente. Confira as restrições da chave na Binance.", 400)
        if code == -1002 or response.status_code in (401, 403):
            raise BinanceError("permission_denied", "Acesso recusado pela Binance. Verifique a permissão de leitura, as restrições de IP e os bloqueios de acesso.", 400)
        if response.status_code == 451:
            raise BinanceError("unavailable", "A Binance está indisponível nesta região ou rede.", 503)
        if response.status_code >= 300 or (isinstance(code, int) and code < 0):
            raise BinanceError("binance_error", "A Binance recusou a consulta. Confira as credenciais e tente novamente.")
        if data is None:
            raise invalid_response()
        return data

    async def _signed_get(self, path: str, credentials: Credentials):
        if path not in self.SIGNED_PATHS:
            raise ValueError("Endpoint autenticado não permitido.")
        # Uma única repetição em -1021. Horário do servidor + metade do RTT
        # monotônico, sem depender de ajustes/saltos do relógio local.
        for attempt in range(2):
            started = time.monotonic()
            server = await self._get("/api/v3/time")
            finished = time.monotonic()
            if not isinstance(server, dict) or type(server.get("serverTime")) is not int:
                raise invalid_response()
            timestamp = server["serverTime"] + int((finished - started) * 500)
            payload = urlencode({"timestamp": timestamp, "recvWindow": 5000})
            signature = hmac.new(
                credentials.secret_key.get_secret_value().encode(), payload.encode(), hashlib.sha256
            ).hexdigest()
            try:
                return await self._get(
                    path,
                    params=f"{payload}&signature={signature}",
                    headers={"X-MBX-APIKEY": credentials.api_key.get_secret_value()},
                )
            except BinanceError as error:
                if error.code != "time_sync" or attempt == 1:
                    raise

    async def account(self, credentials: Credentials) -> Account:
        data = await self._signed_get("/api/v3/account", credentials)
        try:
            return Account.model_validate(data)
        except ValidationError:
            raise invalid_response() from None

    async def permission_warnings(self, credentials: Credentials) -> list[str]:
        try:
            data = await self._signed_get("/sapi/v1/account/apiRestrictions", credentials)
        except BinanceError:
            return ["Não foi possível verificar as permissões da API Key. Confirme na Binance que apenas a leitura está habilitada."]
        if not isinstance(data, dict) or type(data.get("enableReading")) is not bool:
            return ["A Binance não informou as permissões da API Key. Confirme que apenas a leitura está habilitada."]
        permissions = {
            "enableSpotAndMarginTrading": "trading Spot/Margin",
            "enableWithdrawals": "saques",
            "enableInternalTransfer": "transferências internas",
            "permitsUniversalTransfer": "transferências universais",
            "enableMargin": "Margin",
            "enableFutures": "Futures",
            "enableVanillaOptions": "opções",
            "enableFixApiTrade": "trading FIX",
            "enablePortfolioMarginTrading": "trading Portfolio Margin",
        }
        extra = [label for flag, label in permissions.items() if data.get(flag) is True]
        if extra:
            return ["Esta API Key possui permissões além da leitura: " + ", ".join(extra) + ". Desabilite essas permissões na Binance."]
        return []

    async def market(self) -> tuple[ExchangeInfo, list[Ticker]]:
        # Sequencial: um rate limit interrompe a coleta sem disparar outro GET.
        info = await self._get("/api/v3/exchangeInfo", params={"permissions": "SPOT"})
        prices = await self._get("/api/v3/ticker/price")
        try:
            return ExchangeInfo.model_validate(info), TypeAdapter(list[Ticker]).validate_python(prices)
        except ValidationError:
            raise invalid_response() from None
