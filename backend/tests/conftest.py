import asyncio
import hashlib
import hmac
import socket
from types import SimpleNamespace
from urllib.parse import parse_qs

import httpx
import pytest
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


class LocalTestClient:
    """Cliente ASGI síncrono de teste com loop persistente e sem rede externa."""
    def __init__(self, app, *, base_url="http://127.0.0.1", headers=None, client=("127.0.0.1", 50000)):
        self.app = app
        self.base_url = base_url
        self.headers = headers or {}
        self.client_address = client
        self.cookies = httpx.Cookies()
        self.loop = None
        self._http = None
        self._lifespan = None

    def __enter__(self):
        self.loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self.loop)
        self._http = httpx.AsyncClient(
            base_url=self.base_url,
            transport=httpx.ASGITransport(app=self.app, client=self.client_address),
            headers=self.headers, cookies=self.cookies,
        )
        self._lifespan = self.app.router.lifespan_context(self.app)
        self.loop.run_until_complete(self._lifespan.__aenter__())
        self.cookies = self._http.cookies
        return self

    def __exit__(self, *_exc):
        if self.loop is not None:
            if self._lifespan is not None:
                self.loop.run_until_complete(self._lifespan.__aexit__(None, None, None))
            for task in asyncio.all_tasks(self.loop):
                task.cancel()
            self.loop.run_until_complete(asyncio.sleep(0))
            self.loop.close()
            asyncio.set_event_loop(None)
        return False

    def request(self, method, path, **kwargs):
        if self.loop is None or self._http is None:
            raise RuntimeError("LocalTestClient precisa ser usado em um bloco with.")
        return self.loop.run_until_complete(asyncio.wait_for(self._http.request(method, path, **kwargs), timeout=5))

    def get(self, path, **kwargs):
        return self.request("GET", path, **kwargs)

    def post(self, path, **kwargs):
        return self.request("POST", path, **kwargs)

    def delete(self, path, **kwargs):
        return self.request("DELETE", path, **kwargs)

    def options(self, path, **kwargs):
        return self.request("OPTIONS", path, **kwargs)


def pair(base, quote, status="TRADING", spot=True):
    return {"symbol": base + quote, "baseAsset": base, "quoteAsset": quote,
            "status": status, "isSpotTradingAllowed": spot}


@pytest.fixture(autouse=True)
def prohibit_network(monkeypatch):
    def denied(*_args, **_kwargs):
        raise AssertionError("Os testes não podem acessar a rede.")

    async def immediate_test_thread(func, *args, **kwargs):
        # O cofre fake é apenas memória; evitar worker threads mantém o ASGI
        # determinístico em ambientes sem socketpair de loop de eventos.
        return func(*args, **kwargs)

    monkeypatch.setattr(socket.socket, "connect", denied)
    monkeypatch.setattr(asyncio, "to_thread", immediate_test_thread)


@pytest.fixture
def environment():
    state = SimpleNamespace(
        balances=[], requests=[], failures={},
        wallet_balances=[], funding_balances=[], flexible_positions=[], locked_positions=[],
        onchain_locked_positions=[],
        simple_earn={"totalFlexibleAmountInUSDT": "0", "totalLockedInUSDT": "0"},
        onchain_account={"totalFlexibleAmountInUSDT": "0", "totalLockedInUSDT": "0", "totalAmountInUSDT": "0"},
        margin_cross={"created": False, "userAssets": []}, margin_isolated={"assets": []},
        futures_usdm={"assets": [], "positions": []}, futures_coinm={"assets": [], "positions": []},
        bfusd={"bfusdAmount": "0", "bfusdProfit": "0"},
        rwusd={"rwusdAmount": "0", "totalProfit": "0"},
        symbols=[pair("BTC", "USDT"), pair("ETH", "BTC"), pair("NEW", "ETH"), pair("USDT", "BRL")],
        prices=[{"symbol": "BTCUSDT", "price": "60000"}, {"symbol": "ETHBTC", "price": "0.05"},
                {"symbol": "NEWETH", "price": "0.002"}, {"symbol": "USDTBRL", "price": "5"}],
        market_tickers=[
            {"symbol": "BTCUSDT", "lastPrice": "60000", "openPrice": "58823.5294", "highPrice": "61000", "lowPrice": "58000", "priceChangePercent": "2", "volume": "2", "quoteVolume": "120000", "openTime": 1000, "closeTime": 2000},
            {"symbol": "ETHBTC", "lastPrice": "0.05", "openPrice": "0.04950495", "highPrice": "0.052", "lowPrice": "0.048", "priceChangePercent": "1", "volume": "100", "quoteVolume": "5", "openTime": 1000, "closeTime": 2000},
            {"symbol": "NEWETH", "lastPrice": "0.002", "openPrice": "0.00190476", "highPrice": "0.003", "lowPrice": "0.001", "priceChangePercent": "5", "volume": "10000", "quoteVolume": "20", "openTime": 1000, "closeTime": 2000},
            {"symbol": "USDTBRL", "lastPrice": "5", "openPrice": "4.950495", "highPrice": "5.1", "lowPrice": "4.9", "priceChangePercent": "1", "volume": "1000", "quoteVolume": "5000", "openTime": 1000, "closeTime": 2000},
        ],
        permissions={"enableReading": True, "enableSpotAndMarginTrading": False, "enableWithdrawals": False},
    )

    def handler(request):
        state.requests.append(request)
        path = request.url.path
        host = request.url.host
        endpoint = (request.method, {"api.binance.com": "spot", "fapi.binance.com": "usdm", "dapi.binance.com": "coinm"}.get(host), path)
        assert endpoint in BinanceClient.PUBLIC_ENDPOINTS | BinanceClient.SIGNED_ENDPOINTS
        request_text = str(request.url) + request.content.decode("utf-8", "ignore")
        assert all(value not in request_text for value in CREDENTIALS.values())
        if endpoint in BinanceClient.SIGNED_ENDPOINTS:
            assert request.headers["X-MBX-APIKEY"] == CREDENTIALS["api_key"]
            raw_payload = request.content.decode() if request.method == "POST" else request.url.query.decode()
            payload, signature = raw_payload.rsplit("&signature=", 1)
            expected = hmac.new(CREDENTIALS["secret_key"].encode(), payload.encode(), hashlib.sha256).hexdigest()
            assert hmac.compare_digest(signature, expected)
            params = parse_qs(payload)
            assert params["recvWindow"] == ["5000"]
            assert abs(int(params["timestamp"][0]) - 1_000_000_000_000) < 1000
        else:
            assert "X-MBX-APIKEY" not in request.headers
        query = parse_qs(request.url.query.decode())
        current = query.get("current", ["1"])[0]
        failure = state.failures.get(f"{path}:{current}", state.failures.get(path))
        if isinstance(failure, list):
            failure = failure.pop(0) if failure else None
        if isinstance(failure, Exception):
            raise failure
        if failure is not None:
            status, body, headers = failure
            return httpx.Response(status, json=body, headers=headers)
        if path in {"/api/v3/time", "/fapi/v1/time", "/dapi/v1/time"}:
            return httpx.Response(200, json={"serverTime": 1_000_000_000_000})
        if path == "/api/v3/account":
            return httpx.Response(200, json={"balances": state.balances, "canTrade": True, "canWithdraw": True})
        if path == "/sapi/v1/account/apiRestrictions":
            return httpx.Response(200, json=state.permissions)
        if path == "/sapi/v1/asset/wallet/balance":
            return httpx.Response(200, json=state.wallet_balances)
        if path == "/sapi/v1/asset/get-funding-asset":
            return httpx.Response(200, json=state.funding_balances)
        if path == "/sapi/v1/simple-earn/account":
            return httpx.Response(200, json=state.simple_earn)
        if path in {"/sapi/v1/simple-earn/flexible/position", "/sapi/v1/simple-earn/locked/position"}:
            rows = state.flexible_positions if "flexible" in path else state.locked_positions
            page, size = int(current), int(query.get("size", ["100"])[0])
            start = (page - 1) * size
            return httpx.Response(200, json={"rows": rows[start:start + size], "total": len(rows)})
        if path == "/sapi/v1/onchain-yields/account":
            return httpx.Response(200, json=state.onchain_account)
        if path == "/sapi/v1/onchain-yields/locked/position":
            rows = state.onchain_locked_positions
            page, size = int(current), int(query.get("size", ["100"])[0])
            start = (page - 1) * size
            return httpx.Response(200, json={"rows": rows[start:start + size], "total": len(rows)})
        if path == "/sapi/v1/margin/account":
            return httpx.Response(200, json=state.margin_cross)
        if path == "/sapi/v1/margin/isolated/account":
            return httpx.Response(200, json=state.margin_isolated)
        if path == "/fapi/v3/account":
            return httpx.Response(200, json=state.futures_usdm)
        if path == "/dapi/v1/account":
            return httpx.Response(200, json=state.futures_coinm)
        if path == "/sapi/v1/bfusd/account":
            return httpx.Response(200, json=state.bfusd)
        if path == "/sapi/v1/rwusd/account":
            return httpx.Response(200, json=state.rwusd)
        if path == "/api/v3/exchangeInfo":
            return httpx.Response(200, json={"symbols": state.symbols})
        if path == "/api/v3/ticker/24hr":
            return httpx.Response(200, json=state.market_tickers)
        if path == "/api/v3/ticker/price" and query.get("symbol"):
            symbol = query["symbol"][0]
            price = next((item["price"] for item in state.prices if item["symbol"] == symbol), None)
            if price is None:
                return httpx.Response(400, json={"code": -1121, "msg": "Invalid symbol."})
            return httpx.Response(200, json={"symbol": symbol, "price": price})
        return httpx.Response(200, json=state.prices)

    http = httpx.AsyncClient(base_url="https://api.binance.com", transport=httpx.MockTransport(handler))
    state.binance = BinanceClient(http)
    state.sessions = SessionStore()
    state.vault = MemoryVault()
    app = create_app(state.binance, state.sessions, state.vault)
    with LocalTestClient(app, base_url="http://127.0.0.1", headers={"Origin": FRONTEND_ORIGIN}, client=("127.0.0.1", 50000)) as client:
        state.client = client
        response = client.get("/api/session")
        assert response.status_code == 200 and response.json()["connected"] is False, response.text
        yield state
    asyncio.run(http.aclose())
