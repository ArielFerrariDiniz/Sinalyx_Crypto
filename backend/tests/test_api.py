import asyncio
import logging
import time
from decimal import Decimal
from urllib.parse import parse_qs

import httpx
import pytest
from app.main import COOKIE_NAME, FRONTEND_ORIGIN, create_app
from app.models import Credentials
from app.services.sessions import SessionLimitReached, SessionNotFound, SessionStore
from conftest import BinanceClient, CREDENTIALS, LocalTestClient, pair


def connect(env):
    response = env.client.post("/api/connect", json=CREDENTIALS)
    assert response.status_code == 200, response.text
    return response


def test_connection_creates_protected_opaque_session(environment):
    env = environment
    response = connect(env)
    cookie = response.headers["set-cookie"]
    assert "HttpOnly" in cookie and "SameSite=strict" in cookie and "Path=/api" in cookie
    assert "Max-Age" not in cookie and "expires=" not in cookie.lower()
    assert "secret" not in response.text.lower() and "api_key" not in response.text
    token = env.client.cookies.get(COOKIE_NAME)
    assert len(token) >= 40 and token not in response.text
    assert env.sessions.require(token).credentials is not None
    # canTrade/canWithdraw da conta não significam permissões da API Key.
    assert response.json()["warnings"] == []


@pytest.mark.parametrize(("code", "status", "expected"), [
    (-2014, 400, "invalid_api_key"),
    (-2015, 400, "key_or_permission"),
    (-1022, 400, "invalid_signature"),
    (-1002, 403, "permission_denied"),
    (-1021, 400, "time_sync"),
    (-1008, 503, "unavailable"),
    (-1007, 504, "timeout"),
])
def test_binance_errors_without_credential_exposure(environment, code, status, expected, caplog):
    env = environment
    env.failures["/api/v3/account"] = (status, {"code": code, "msg": str(CREDENTIALS)}, {})
    response = env.client.post("/api/connect", json=CREDENTIALS)
    assert response.status_code >= 400
    assert response.json()["code"] == expected
    assert COOKIE_NAME not in response.cookies
    assert all(session.credentials is None for session in env.sessions._sessions.values())
    for value in CREDENTIALS.values():
        assert value not in response.text and value not in caplog.text
    if code == -1021:
        assert sum(request.url.path == "/api/v3/account" for request in env.requests) == 2


@pytest.mark.parametrize(("exception", "expected", "status"), [
    (httpx.ConnectError("sensitive connection detail"), "connection_error", 502),
    (httpx.ReadTimeout("sensitive timeout detail"), "timeout", 504),
])
def test_network_failure(environment, exception, expected, status):
    env = environment
    env.failures["/api/v3/time"] = exception
    response = env.client.post("/api/connect", json=CREDENTIALS)
    assert response.status_code == status
    assert response.json()["code"] == expected
    assert "sensitive" not in response.text


@pytest.mark.parametrize("status", [418, 429])
def test_rate_limit_honors_retry_after_and_stops_requests(environment, status):
    env = environment
    env.failures["/api/v3/time"] = (status, {"code": -1003}, {"Retry-After": "120"})
    first = env.client.post("/api/connect", json=CREDENTIALS)
    assert first.status_code == 429 and first.headers["Retry-After"] == "120"
    count = len(env.requests)
    second = env.client.post("/api/connect", json=CREDENTIALS)
    assert second.status_code == 429
    assert len(env.requests) == count


@pytest.mark.parametrize("status", [500, 503, 451])
def test_unavailability(environment, status):
    env = environment
    env.failures["/api/v3/time"] = (status, {}, {})
    response = env.client.post("/api/connect", json=CREDENTIALS)
    assert response.status_code == 503 and response.json()["code"] == "unavailable"


def test_clock_resynchronizes_once(environment):
    env = environment
    env.failures["/api/v3/account"] = [(400, {"code": -1021}, {})]
    connect(env)
    paths = [request.url.path for request in env.requests]
    assert paths[:4] == ["/api/v3/time", "/api/v3/account", "/api/v3/time", "/api/v3/account"]


def test_empty_wallet(environment):
    env = environment
    connect(env)
    response = env.client.get("/api/portfolio")
    assert response.status_code == 200
    data = response.json()
    assert data["assets"] == [] and data["asset_count"] == 0
    assert data["total_usdt"] == "0" and data["is_partial"] is True
    assert next(wallet for wallet in data["wallets"] if wallet["wallet_id"] == "spot")["status"] == "ok"
    assert not any(request.url.path == "/api/v3/ticker/price" for request in env.requests)


def test_assets_balances_and_dynamic_intermediate_conversion(environment):
    env = environment
    env.balances = [
        {"asset": "BTC", "free": "0.1", "locked": "0.02"},
        {"asset": "ETH", "free": "1", "locked": "0.5"},
        {"asset": "NEW", "free": "2", "locked": "0"},
        {"asset": "BRL", "free": "50", "locked": "0"},
        {"asset": "USDT", "free": "10", "locked": "2.3"},
        {"asset": "ZERO", "free": "0", "locked": "0"},
    ]
    connect(env)
    response = env.client.get("/api/portfolio")
    assert response.status_code == 200
    data = response.json()
    assets = {asset["asset"]: asset for asset in data["assets"]}
    assert data["asset_count"] == 5 and "ZERO" not in assets
    assert assets["BTC"]["free"] == "0.1" and assets["BTC"]["locked"] == "0.02"
    assert assets["BTC"]["total"] == "0.12"
    assert Decimal(assets["BTC"]["value_usdt"]) == Decimal("7200")
    assert Decimal(assets["ETH"]["price_usdt"]) == Decimal("3000")
    assert assets["ETH"]["conversion_path"] == ["ETH", "BTC", "USDT"]
    assert Decimal(assets["NEW"]["price_usdt"]) == Decimal("6")
    assert Decimal(assets["BRL"]["value_usdt"]) == Decimal("10")
    assert assets["USDT"]["price_usdt"] == "1"
    assert Decimal(data["total_usdt"]) == Decimal("11734.3")
    assert data["updated_at"].endswith("Z") and data["is_partial"] is True
    # Atualização manual consulta os dados novamente, sem manter carteira antiga no servidor.
    env.balances = [{"asset": "USDT", "free": "3", "locked": "0"}]
    assert env.client.get("/api/portfolio").json()["total_usdt"] == "3"


def test_missing_quotes_are_null_and_total_is_partial(environment):
    env = environment
    env.balances = [{"asset": "UNKNOWN", "free": "2", "locked": "1"},
                    {"asset": "USDT", "free": "5", "locked": "0"}]
    connect(env)
    data = env.client.get("/api/portfolio").json()
    unknown = next(asset for asset in data["assets"] if asset["asset"] == "UNKNOWN")
    assert unknown["price_usdt"] is None and unknown["value_usdt"] is None
    assert unknown["total"] == "3" and unknown["conversion_path"] is None
    assert data["is_partial"] is True and data["unpriced_assets"] == ["UNKNOWN"]
    assert data["total_usdt"] == "5"
    spot = next(wallet for wallet in data["wallets"] if wallet["wallet_id"] == "spot")
    assert spot["status"] == "partial" and spot["total_usdt"] == "5"


def test_direct_pair_preferred_and_invalid_markets_excluded(environment):
    env = environment
    env.symbols += [pair("ETH", "USDT"), pair("OLD", "USDT", "BREAK"), pair("OTHER", "USDT", spot=False), pair("BAD", "USDT")]
    env.prices += [{"symbol": "ETHUSDT", "price": "3500"}, {"symbol": "OLDUSDT", "price": "100"},
                   {"symbol": "OTHERUSDT", "price": "100"}, {"symbol": "BADUSDT", "price": "0"}]
    env.balances = [{"asset": asset, "free": "1", "locked": "0"} for asset in ["ETH", "OLD", "OTHER", "BAD"]]
    connect(env)
    data = env.client.get("/api/portfolio").json()
    assert data["assets"][0]["conversion_path"] == ["ETH", "USDT"]
    assert data["total_usdt"] == "3500"
    assert data["unpriced_assets"] == ["BAD", "OLD", "OTHER"]


def test_decimal_precision(environment):
    env = environment
    env.balances = [{"asset": "USDT", "free": "0.10000000000000000001", "locked": "0.2"}]
    connect(env)
    data = env.client.get("/api/portfolio").json()
    assert data["total_usdt"] == "0.30000000000000000001"
    assert isinstance(data["assets"][0]["free"], str)


def test_spot_and_earn_positions_are_consolidated_without_adding_rewards(environment):
    env = environment
    env.balances = [{"asset": "BTC", "free": "0.1", "locked": "0.02"}]
    env.simple_earn = {"totalFlexibleAmountInUSDT": "12000", "totalLockedInUSDT": "18000"}
    env.flexible_positions = [{
        "asset": "BTC", "totalAmount": "0.2", "cumulativeTotalRewards": "0.03",
        "rewardAsset": "BTC", "latestAnnualPercentageRate": "0.025",
    }]
    env.locked_positions = [{
        "asset": "BTC", "amount": "0.3", "rewardAmt": "0.01", "rewardAsset": "BTC",
        "duration": "60", "APY": "0.12", "nextPay": "0.002", "nextPayDate": 1760000000000,
    }]
    connect(env)

    data = env.client.get("/api/portfolio").json()
    btc = next(asset for asset in data["assets"] if asset["asset"] == "BTC")
    assert btc["total"] == "0.62"  # Recompensas não elevam a quantidade contabilizada.
    assert btc["net_total"] == "0.62" and btc["value_usdt"] == "37200.00"
    assert btc["free"] == "0.1" and btc["locked"] == "0.02" and btc["applied"] == "0.5"
    assert {source["wallet_id"] for source in btc["sources"]} == {"spot", "earn_flexible", "earn_locked"}
    assert any("informativo; não somado" in note for source in btc["sources"] for note in source["reward_notes"])
    detail_text = " ".join(detail for source in btc["sources"] for detail in source["position_details"])
    assert "APR atual: 2.5% a.a." in detail_text and "Prazo: 60 dias" in detail_text
    assert "APY: 12% a.a." in detail_text and "Próximo rendimento estimado" in detail_text
    subtotals = {wallet["wallet_id"]: wallet["total_usdt"] for wallet in data["wallets"]}
    assert Decimal(subtotals["spot"]) == Decimal("7200")
    assert Decimal(subtotals["earn_flexible"]) == Decimal("12000")
    assert Decimal(subtotals["earn_locked"]) == Decimal("18000")
    assert data["total_usdt"] == "37200.00"


def test_simple_earn_summary_is_used_when_positions_confirm_empty_but_summary_has_balance(environment):
    env = environment
    env.simple_earn = {"totalFlexibleAmountInUSDT": "8", "totalLockedInUSDT": "25"}
    connect(env)

    data = env.client.get("/api/portfolio").json()
    wallets = {wallet["wallet_id"]: wallet for wallet in data["wallets"]}
    assert wallets["earn_flexible"]["status"] == "partial" and wallets["earn_flexible"]["total_usdt"] == "8"
    assert wallets["earn_locked"]["status"] == "partial" and wallets["earn_locked"]["total_usdt"] == "25"
    assert data["assets"] == [] and data["total_usdt"] == "33"


def test_simple_earn_pagination_fetches_all_position_pages(environment):
    env = environment
    env.flexible_positions = [{"asset": "USDT", "totalAmount": "0.01"} for _ in range(101)]
    connect(env)

    data = env.client.get("/api/portfolio").json()
    flexible_requests = [
        request for request in env.requests
        if request.url.path == "/sapi/v1/simple-earn/flexible/position"
    ]
    pages = {parse_qs(request.url.query.decode())["current"][0] for request in flexible_requests}
    assert pages == {"1", "2"}
    assert data["total_usdt"] == "1.01"
    assert next(wallet for wallet in data["wallets"] if wallet["wallet_id"] == "earn_flexible")["asset_count"] == 1


def test_onchain_yields_locked_positions_and_flexible_summary_are_consolidated_once(environment):
    env = environment
    env.balances = [{"asset": "BTC", "free": "1", "locked": "0"}]
    env.onchain_account = {
        "totalFlexibleAmountInUSDT": "12.34",
        "totalLockedInUSDT": "30000",
        "totalAmountInUSDT": "30012.34",
    }
    env.onchain_locked_positions = [{
        "asset": "BTC", "amount": "0.5", "rewardAsset": "BTC", "rewardAmt": "0.1",
        "duration": "90", "APY": "0.05", "nextPay": "0.01", "redeemingAmt": "0.1",
    }]
    # O inventário geral de carteiras também pode expor o mesmo produto; não
    # deve ser somado novamente às posições especializadas.
    env.wallet_balances = [{"walletName": "On-chain Yields", "assetBalances": [
        {"asset": "BTC", "free": "0.5", "locked": "0", "freeze": "0", "withdrawing": "0"},
    ]}]
    connect(env)

    data = env.client.get("/api/portfolio").json()
    btc = next(asset for asset in data["assets"] if asset["asset"] == "BTC")
    assert btc["total"] == "1.5" and btc["value_usdt"] == "90000.0"
    assert {source["wallet_id"] for source in btc["sources"]} == {"spot", "onchain_locked"}
    onchain_source = next(source for source in btc["sources"] if source["wallet_id"] == "onchain_locked")
    assert onchain_source["applied"] == "0.5"
    assert "informativo; não somado" in onchain_source["reward_notes"][0]
    details = " ".join(onchain_source["position_details"])
    assert "Prazo: 90 dias" in details and "APY: 5% a.a." in details
    assert "Em resgate informado: 0.1 BTC (não somado separadamente)" in details
    wallets = {wallet["wallet_id"]: wallet for wallet in data["wallets"]}
    assert wallets["onchain_locked"]["total_usdt"] == "30000.0"
    assert wallets["onchain_flexible"]["total_usdt"] == "12.34"
    assert wallets["onchain_flexible"]["status"] == "partial"
    assert wallets["onchain_flexible"]["asset_count"] == 0
    assert data["total_usdt"] == "90012.34"


def test_onchain_yields_locked_pagination_reads_every_page(environment):
    env = environment
    env.onchain_account["totalLockedInUSDT"] = "101"
    env.onchain_locked_positions = [{"asset": "USDT", "amount": "1"} for _ in range(101)]
    connect(env)

    data = env.client.get("/api/portfolio").json()
    requests = [request for request in env.requests if request.url.path == "/sapi/v1/onchain-yields/locked/position"]
    assert {parse_qs(request.url.query.decode())["current"][0] for request in requests} == {"1", "2"}
    wallet = next(wallet for wallet in data["wallets"] if wallet["wallet_id"] == "onchain_locked")
    assert wallet["status"] == "ok" and wallet["asset_count"] == 1
    assert data["total_usdt"] == "101"


def test_onchain_summary_is_fallback_only_when_position_query_fails(environment):
    env = environment
    env.onchain_account["totalFlexibleAmountInUSDT"] = "8"
    env.onchain_account["totalLockedInUSDT"] = "25"
    env.failures["/sapi/v1/onchain-yields/locked/position"] = (503, {}, {})
    connect(env)

    data = env.client.get("/api/portfolio").json()
    wallets = {wallet["wallet_id"]: wallet for wallet in data["wallets"]}
    assert wallets["onchain_locked"]["status"] == "partial"
    assert wallets["onchain_locked"]["total_usdt"] == "25"
    assert wallets["onchain_flexible"]["total_usdt"] == "8"
    assert data["assets"] == [] and data["total_usdt"] == "33"


def test_funding_wallet_detail_is_included_once(environment):
    env = environment
    env.balances = [{"asset": "USDT", "free": "3", "locked": "0"}]
    env.wallet_balances = [{"walletName": "Funding", "assetBalances": [
        {"asset": "USDT", "free": "5", "locked": "1", "freeze": "0", "withdrawing": "0"},
    ]}]
    connect(env)

    data = env.client.get("/api/portfolio").json()
    usdt = next(asset for asset in data["assets"] if asset["asset"] == "USDT")
    assert data["total_usdt"] == "9"
    assert usdt["total"] == "9" and usdt["value_usdt"] == "9"
    assert {source["wallet_id"] for source in usdt["sources"]} == {"spot", "funding"}
    assert not any(request.url.path == "/sapi/v1/asset/get-funding-asset" for request in env.requests)


def test_funding_query_fallback_is_marked_limited(environment):
    env = environment
    env.funding_balances = [{"asset": "USDT", "free": "2", "locked": "1"}]
    connect(env)

    data = env.client.get("/api/portfolio").json()
    funding = next(wallet for wallet in data["wallets"] if wallet["wallet_id"] == "funding")
    assert funding["total_usdt"] == "3" and funding["status"] == "partial"
    assert "não confirma todos" in funding["warning"]
    request = next(request for request in env.requests if request.url.path == "/sapi/v1/asset/get-funding-asset")
    assert request.method == "POST"
    assert request.headers["X-MBX-APIKEY"] == CREDENTIALS["api_key"]


def test_additional_wallets_are_discovered_and_unsupported_products_are_flagged(environment):
    env = environment
    env.wallet_balances = [
        {"walletName": "Extra Wallet", "assetBalances": [
            {"asset": "USDT", "free": "2", "locked": "0", "freeze": "0", "withdrawing": "0"},
        ]},
        {"walletName": "Earn", "assetBalances": [
            {"asset": "USDT", "free": "10", "locked": "0", "freeze": "0", "withdrawing": "0"},
        ]},
        {"walletName": "Options", "assetBalances": []},
    ]
    connect(env)

    data = env.client.get("/api/portfolio").json()
    usdt = next(asset for asset in data["assets"] if asset["asset"] == "USDT")
    assert usdt["value_usdt"] == "2"
    assert any(source["wallet"] == "Extra Wallet" for source in usdt["sources"])
    wallet_by_name = {wallet["name"]: wallet for wallet in data["wallets"]}
    assert wallet_by_name["Options"]["status"] == "unsupported"
    assert wallet_by_name["Options"]["total_usdt"] is None
    assert wallet_by_name["Earn (agregado)"]["status"] == "unsupported"
    assert wallet_by_name["Earn (agregado)"]["total_usdt"] is None
    assert data["is_partial"] is True


def test_margin_liabilities_and_futures_wallet_balance_are_net_of_notionals(environment):
    env = environment
    env.margin_cross = {"created": True, "userAssets": [{
        "asset": "USDT", "free": "8", "locked": "1", "borrowed": "3", "interest": "1", "netAsset": "5",
    }]}
    env.margin_isolated = {"assets": [{
        "symbol": "BTCUSDT",
        "baseAsset": {"asset": "BTC", "free": "0", "locked": "0", "borrowed": "0", "interest": "0", "netAsset": "0"},
        "quoteAsset": {"asset": "USDT", "free": "2", "locked": "0", "borrowed": "0", "interest": "0", "netAsset": "2"},
    }]}
    env.futures_usdm = {
        "assets": [{
            "asset": "USDT", "walletBalance": "5", "unrealizedProfit": "1", "marginBalance": "6",
            "initialMargin": "3", "positionInitialMargin": "2", "openOrderInitialMargin": "1",
            "maintMargin": "0.2",
        }],
        "positions": [{"symbol": "BTCUSDT", "notional": "999999999", "unrealizedProfit": "1", "isolated": True}],
    }
    connect(env)

    data = env.client.get("/api/portfolio").json()
    assert data["total_usdt"] == "13"
    usdt = next(asset for asset in data["assets"] if asset["asset"] == "USDT")
    assert usdt["net_total"] == "13" and usdt["value_usdt"] == "13"
    assert usdt["liability"] == "4"
    subtotals = {wallet["wallet_id"]: wallet["total_usdt"] for wallet in data["wallets"]}
    assert subtotals["margin_cross"] == "5"
    assert subtotals["margin_isolated"] == "2"
    assert subtotals["futures_usdm"] == "6"
    futures_source = next(source for source in usdt["sources"] if source["wallet_id"] == "futures_usdm")
    assert futures_source["available"] == "2" and futures_source["applied"] == "3"
    assert all("999999999" not in detail for detail in futures_source["position_details"])


def test_partial_endpoint_failure_preserves_other_wallets_and_zero_is_confirmed(environment):
    env = environment
    env.balances = [{"asset": "USDT", "free": "10", "locked": "0"}]
    env.failures["/sapi/v1/simple-earn/flexible/position"] = (503, {}, {})
    connect(env)

    data = env.client.get("/api/portfolio").json()
    wallets = {wallet["wallet_id"]: wallet for wallet in data["wallets"]}
    assert wallets["spot"]["status"] == "ok" and wallets["spot"]["total_usdt"] == "10"
    assert wallets["earn_flexible"]["status"] == "partial"
    assert data["total_usdt"] == "10" and data["is_partial"] is True

    env.failures["/api/v3/account"] = (503, {}, {})
    refreshed = env.client.get("/api/portfolio").json()
    assert next(wallet for wallet in refreshed["wallets"] if wallet["wallet_id"] == "spot")["status"] == "unavailable"


def test_unavailable_product_is_not_reported_as_zero_balance(environment):
    env = environment
    env.failures["/sapi/v1/bfusd/account"] = (404, {}, {})
    connect(env)

    data = env.client.get("/api/portfolio").json()
    bfusd = next(wallet for wallet in data["wallets"] if wallet["wallet_id"] == "earn_bfusd")
    assert bfusd["status"] == "unavailable" and bfusd["total_usdt"] is None
    assert data["is_partial"] is True


def test_client_allows_only_reviewed_read_queries(environment):
    allowed_posts = {endpoint for endpoint in BinanceClient.SIGNED_ENDPOINTS if endpoint[0] == "POST"}
    assert allowed_posts == {("POST", "spot", "/sapi/v1/asset/get-funding-asset")}
    for method, path in (("POST", "/sapi/v1/asset/transfer"), ("POST", "/api/v3/order"),
        ("POST", "/sapi/v1/onchain-yields/locked/redeem"), ("GET", "/fapi/v2/positionRisk"),
        ("GET", "/fapi/v3/balance"), ("DELETE", "/api/v3/order")):
        with pytest.raises(ValueError):
            asyncio.run(environment.binance._request(method, path))


def test_disconnect_clears_credentials_and_vault(environment):
    env = environment
    connect(env)
    token = env.client.cookies.get(COOKIE_NAME)
    session = env.sessions.require(token)
    assert env.client.delete("/api/session").status_code == 204
    assert session.credentials is None and not session.warnings
    assert not env.sessions._sessions
    assert env.vault.record is None
    assert env.client.get("/api/portfolio").status_code == 401
    assert env.client.delete("/api/session").status_code == 401


def test_vault_restores_connection_after_backend_restart_without_app_password(environment):
    env = environment
    env.balances = [{"asset": "USDT", "free": "42.5", "locked": "1"}]
    connect(env)
    previous_token = env.client.cookies.get(COOKIE_NAME)
    saved_credentials = env.vault.record
    env.sessions.clear()

    app = create_app(env.binance, vault=env.vault)
    with LocalTestClient(app, base_url="http://127.0.0.1", client=("127.0.0.1", 1234),
                    headers={"Origin": FRONTEND_ORIGIN}) as browser:
        restored = browser.get("/api/session", headers={"Cookie": f"{COOKIE_NAME}={previous_token}"})
        assert restored.status_code == 200 and restored.json()["connected"] is True
        cookie = restored.headers["set-cookie"]
        assert "HttpOnly" in cookie and "SameSite=strict" in cookie and "Max-Age" not in cookie
        assert cookie.split(";", 1)[0].split("=", 1)[1] != previous_token
        assert browser.get("/api/portfolio").json()["total_usdt"] == "43.5"
        for value in CREDENTIALS.values():
            assert value not in restored.text

    assert not app.state.sessions._sessions
    assert env.vault.record == saved_credentials


def test_locked_vault_uses_system_unlock_then_restores_without_app_password(environment):
    env = environment
    connect(env)
    env.client.cookies.clear()
    env.vault.locked = True
    locked = env.client.get("/api/session")
    assert locked.status_code == 503 and locked.json()["code"] == "vault_locked"
    assert env.client.post("/api/vault/unlock").status_code == 200
    restored = env.client.get("/api/session")
    assert restored.status_code == 200 and restored.json()["connected"] is True
    paths = {route.path for route in env.client.app.routes}
    assert not {"/api/auth/setup", "/api/auth/login", "/api/auth/status"} & paths


def test_vault_write_failure_never_falls_back_to_plaintext(environment, caplog):
    env = environment
    env.vault.unavailable = True
    response = env.client.post("/api/connect", json=CREDENTIALS)
    assert response.status_code == 503 and response.json()["code"] == "vault_unavailable"
    assert env.vault.record is None
    assert all(session.credentials is None for session in env.sessions._sessions.values())
    for secret in CREDENTIALS.values():
        assert secret not in response.text + caplog.text


@pytest.mark.parametrize("elapsed", [901, 86400, 315360000])
def test_session_never_expires_by_inactivity(monkeypatch, elapsed):
    store = SessionStore()
    credentials = Credentials(**CREDENTIALS)
    token = store.create(credentials, [])
    session = store.require(token)
    future_monotonic = time.monotonic() + elapsed
    future_wall_time = time.time() + elapsed
    with monkeypatch.context() as clock:
        clock.setattr(time, "monotonic", lambda: future_monotonic)
        clock.setattr(time, "time", lambda: future_wall_time)
        assert store.require(token) is session
        assert session.credentials is credentials
    store.delete(token)
    assert session.credentials is None
    with pytest.raises(SessionNotFound):
        store.require(token)


def test_browser_can_resume_session_without_resending_keys(environment):
    env = environment
    connect(env)
    token = env.client.cookies.get(COOKIE_NAME)
    count = len(env.requests)
    resumed = env.client.get("/api/session")
    assert resumed.status_code == 200 and resumed.json() == {"warnings": [], "connected": True}
    assert len(env.requests) == count  # Inspecionar a sessão não conecta à Binance.
    assert env.client.get("/api/portfolio").status_code == 200
    assert env.client.cookies.get(COOKIE_NAME) == token
    for value in CREDENTIALS.values():
        assert value not in resumed.text


def test_other_local_browser_restores_from_vault_without_resending_keys(environment):
    env = environment
    connect(env)
    token = env.client.cookies.get(COOKIE_NAME)
    env.client.cookies.clear()
    count = len(env.requests)
    resumed = env.client.get("/api/session")
    assert resumed.status_code == 200 and resumed.json()["connected"] is True
    assert env.client.cookies.get(COOKIE_NAME) != token
    assert env.client.get("/api/portfolio").status_code == 200
    assert env.sessions.require(token).credentials is not None
    assert len(env.requests) > count


def test_session_rotation_invalidates_previous_token(environment):
    env = environment
    connect(env)
    old = env.client.cookies.get(COOKIE_NAME)
    old_session = env.sessions.require(old)
    connect(env)
    assert env.client.cookies.get(COOKIE_NAME) != old
    assert old_session.credentials is None
    with pytest.raises(SessionNotFound):
        env.sessions.require(old)


def test_session_limit_does_not_evict_existing_connections():
    store = SessionStore()
    credentials = Credentials(**CREDENTIALS)
    tokens = [store.create(credentials, []) for _ in range(16)]
    with pytest.raises(SessionLimitReached):
        store.create(credentials, [])
    assert all(store.require(token).credentials is credentials for token in tokens)
    store.clear()


def test_extra_key_permissions_and_optional_endpoint(environment):
    env = environment
    env.permissions.update(enableWithdrawals=True, enableSpotAndMarginTrading=True, permitsUniversalTransfer=True)
    response = connect(env)
    warning = response.json()["warnings"][0]
    assert "saques" in warning and "trading Spot/Margin" in warning and "transferências" in warning
    assert warning in env.client.get("/api/portfolio").json()["warnings"]
    env.failures["/sapi/v1/account/apiRestrictions"] = (404, {}, {})
    assert "Não foi possível verificar" in connect(env).json()["warnings"][0]


@pytest.mark.parametrize("body", [
    {**CREDENTIALS, "secret_key": "invalid secret with spaces"},
    {**CREDENTIALS, "api_key": ["sensitive-key"]},
    {**CREDENTIALS, "extra": "sensitive-input"},
    {"secret_key": CREDENTIALS["secret_key"]},
])
def test_validation_never_echoes_input(environment, body, caplog):
    response = environment.client.post("/api/connect", json=body)
    assert response.status_code == 422
    for secret in [*CREDENTIALS.values(), "sensitive", "invalid secret"]:
        assert secret not in response.text and secret not in caplog.text
    assert not environment.requests


def test_origin_host_and_cors_restrictions(environment):
    client = environment.client
    assert client.post("/api/connect", json=CREDENTIALS, headers={"Origin": "https://attacker.test"}).status_code == 403
    assert client.post("/api/connect", json=CREDENTIALS, headers={"Origin": ""}).status_code == 403
    assert client.get("/api/portfolio", headers={"Host": "attacker.test"}).status_code == 400
    preflight = client.options("/api/connect", headers={"Origin": FRONTEND_ORIGIN,
        "Access-Control-Request-Method": "POST", "Access-Control-Request-Headers": "content-type"})
    assert preflight.headers["access-control-allow-origin"] == FRONTEND_ORIGIN
    rejected = client.options("/api/connect", headers={"Origin": "http://localhost:5173", "Access-Control-Request-Method": "POST"})
    assert "access-control-allow-origin" not in rejected.headers
    response = client.get("/api/portfolio")
    assert response.headers["cache-control"] == "no-store"


def test_malformed_data_safe_internal_error_and_no_secret_repr(environment, caplog):
    env = environment
    env.balances = [{"asset": "BTC", "free": "NaN", "locked": "0"}]
    response = env.client.post("/api/connect", json=CREDENTIALS)
    assert response.status_code == 502 and response.json()["code"] == "invalid_response"
    env.failures["/api/v3/time"] = RuntimeError(str(CREDENTIALS))
    response = env.client.post("/api/connect", json=CREDENTIALS)
    assert response.status_code == 500
    representation = repr(Credentials(**CREDENTIALS))
    for secret in CREDENTIALS.values():
        assert secret not in representation + response.text + caplog.text


def test_client_refuses_any_non_read_endpoint(environment):
    with pytest.raises(ValueError):
        asyncio.run(environment.binance._get("/api/v3/order"))


def test_revoked_session_during_fetch_cannot_return_balances(environment, monkeypatch):
    env = environment
    connect(env)
    token = env.client.cookies.get(COOKIE_NAME)
    account_method = env.binance.account

    async def revoked_account(credentials):
        account = await account_method(credentials)
        env.sessions.delete(token)
        return account

    monkeypatch.setattr(env.binance, "account", revoked_account)
    response = env.client.get("/api/portfolio")
    assert response.status_code == 401
    assert "assets" not in response.json()


def test_forged_token_cannot_query_wallet_and_is_replaced_by_vault_session(environment):
    env = environment
    env.client.cookies.clear()
    assert env.client.get("/api/portfolio", headers={"Cookie": f"{COOKIE_NAME}=forged-token"}).status_code == 401
    env.client.cookies.clear()
    session = env.client.get("/api/session")
    assert session.status_code == 200 and session.json()["connected"] is False
    assert not env.requests


def test_non_local_client_is_rejected_even_with_correct_origin(environment):
    app = create_app(environment.binance)
    with LocalTestClient(app, base_url="http://127.0.0.1", client=("192.0.2.1", 1234)) as client:
        response = client.post("/api/connect", json=CREDENTIALS, headers={"Origin": FRONTEND_ORIGIN})
        assert response.status_code == 403 and response.json()["code"] == "local_only"
    assert not environment.requests


def test_shutdown_clears_sessions(environment):
    store = environment.sessions

    async def lifecycle():
        app = create_app(environment.binance, store)
        async with app.router.lifespan_context(app):
            token = store.create(Credentials(**CREDENTIALS), [])
            session = store.require(token)
        assert session.credentials is None
        assert not store._sessions
        # Uma nova execução não restaura credenciais nem aceita tokens anteriores.
        async with app.router.lifespan_context(app):
            with pytest.raises(SessionNotFound):
                store.require(token)

    asyncio.run(lifecycle())


def test_transport_child_loggers_cannot_propagate_secrets(caplog):
    with caplog.at_level(logging.DEBUG):
        logging.getLogger("httpcore.connection").debug(CREDENTIALS["secret_key"])
    assert CREDENTIALS["secret_key"] not in caplog.text
