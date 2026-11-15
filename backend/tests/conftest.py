import asyncio
import hashlib
import hmac
import socket
from types import SimpleNamespace
from urllib.parse import parse_qs

import httpx
import pytest
from fastapi.testclient import TestClient

from app.binance_client import BinanceClient
from app.main import FRONTEND_ORIGIN, create_app
from app.services.sessions import SessionStore
from app.services.vault import VaultError

# Dados fictícios. Nenhuma credencial real, conta ou operação financeira.
CREDENTIALS = {"api_key": "FakeApiKeyForTests123", "secret_key": "FakeSecretKeyForTests456"}


class MemoryVault:
    def __init__(self):
        self.record = None
        self.locked = False
        self.unavailable = False

    def check(self):
        if self.unavailable:
            raise VaultError("vault_unavailable", "Cofre indisponível.")
        if self.locked:
            raise VaultError("vault_locked", "Cofre bloqueado.")

    def read(self):
        self.check()
        return self.record

    def write(self, record):
        self.check()
        self.record = record

    def delete(self):
        self.check()
        self.record = None

    def unlock(self):
        self.locked = False
        self.check()


def pair(base, quote, status="TRADING", spot=True):
    return {"symbol": base + quote, "baseAsset": base, "quoteAsset": quote,
            "status": status, "isSpotTradingAllowed": spot}


@pytest.fixture(autouse=True)
def prohibit_network(monkeypatch):
    def denied(*_args, **_kwargs):
        raise AssertionError("Os testes não podem acessar a rede.")
    monkeypatch.setattr(socket.socket, "connect", denied)


@pytest.fixture
def environment():
    state = SimpleNamespace(
        balances=[], requests=[], failures={},
        symbols=[pair("BTC", "USDT"), pair("ETH", "BTC"), pair("NEW", "ETH"), pair("USDT", "BRL")],
        prices=[{"symbol": "BTCUSDT", "price": "60000"}, {"symbol": "ETHBTC", "price": "0.05"},
                {"symbol": "NEWETH", "price": "0.002"}, {"symbol": "USDTBRL", "price": "5"}],
        permissions={"enableReading": True, "enableSpotAndMarginTrading": False, "enableWithdrawals": False},
    )

    def handler(request):
        state.requests.append(request)
        assert request.method == "GET"
        assert request.url.host == "api.binance.com"
        path = request.url.path
        assert path in BinanceClient.PUBLIC_PATHS | BinanceClient.SIGNED_PATHS
        assert all(value not in str(request.url) for value in CREDENTIALS.values())
        if path in BinanceClient.SIGNED_PATHS:
            assert request.headers["X-MBX-APIKEY"] == CREDENTIALS["api_key"]
            payload, signature = request.url.query.decode().rsplit("&signature=", 1)
            expected = hmac.new(CREDENTIALS["secret_key"].encode(), payload.encode(), hashlib.sha256).hexdigest()
            assert hmac.compare_digest(signature, expected)
            params = parse_qs(payload)
            assert params["recvWindow"] == ["5000"]
            assert abs(int(params["timestamp"][0]) - 1_000_000_000_000) < 1000
        else:
            assert "X-MBX-APIKEY" not in request.headers
        failure = state.failures.get(path)
        if isinstance(failure, list):
            failure = failure.pop(0) if failure else None
        if isinstance(failure, Exception):
            raise failure
        if failure is not None:
            status, body, headers = failure
            return httpx.Response(status, json=body, headers=headers)
        if path == "/api/v3/time":
            return httpx.Response(200, json={"serverTime": 1_000_000_000_000})
        if path == "/api/v3/account":
            return httpx.Response(200, json={"balances": state.balances, "canTrade": True, "canWithdraw": True})
        if path == "/sapi/v1/account/apiRestrictions":
            return httpx.Response(200, json=state.permissions)
        if path == "/api/v3/exchangeInfo":
            return httpx.Response(200, json={"symbols": state.symbols})
        return httpx.Response(200, json=state.prices)

    http = httpx.AsyncClient(base_url="https://api.binance.com", transport=httpx.MockTransport(handler))
    state.binance = BinanceClient(http)
    state.sessions = SessionStore()
    state.vault = MemoryVault()
    app = create_app(state.binance, state.sessions, state.vault)
    with TestClient(app, base_url="http://127.0.0.1", headers={"Origin": FRONTEND_ORIGIN}, client=("127.0.0.1", 50000)) as client:
        state.client = client
        response = client.get("/api/session")
        assert response.status_code == 200 and response.json()["connected"] is False, response.text
        yield state
    asyncio.run(http.aclose())
