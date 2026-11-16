from decimal import Decimal

import httpx

from conftest import CREDENTIALS, pair


def ticker(symbol, *, price="2", change="0", volume="100", quote_volume="200"):
    return {
        "symbol": symbol,
        "lastPrice": price,
        "openPrice": price,
        "highPrice": price,
        "lowPrice": price,
        "priceChangePercent": change,
        "volume": volume,
        "quoteVolume": quote_volume,
        "openTime": 1000,
        "closeTime": 2000,
    }


def test_market_is_public_aggregated_and_converts_intermediate_pairs(environment):
    response = environment.client.get("/api/market")
    assert response.status_code == 200, response.text
    data = response.json()
    assets = {asset["symbol"]: asset for asset in data["assets"]}
    assert set(assets) == {"BTC", "ETH", "NEW", "USDT"}
    assert assets["BTC"]["pair"] == "BTCUSDT"
    assert Decimal(assets["BTC"]["price_usdt"]) == Decimal("60000")
    assert assets["ETH"]["pair"] == "ETHBTC"
    assert Decimal(assets["ETH"]["price_usdt"]) == Decimal("3000.00")
    assert assets["ETH"]["conversion_path"] == ["BTCUSDT"]
    assert assets["NEW"]["pair"] == "NEWETH"
    assert Decimal(assets["NEW"]["price_usdt"]) == Decimal("6.000000")
    assert Decimal(assets["NEW"]["volume_usdt_24h"]) == Decimal("60000.000000")
    assert Decimal(assets["NEW"]["high_24h_usdt"]) == Decimal("9.000000")
    assert assets["NEW"]["conversion_approximate"] is True
    assert data["updated_at"]
    paths = [request.url.path for request in environment.requests]
    assert paths.count("/api/v3/exchangeInfo") == 1
    assert paths.count("/api/v3/ticker/24hr") == 1
    assert not any(request.headers.get("X-MBX-APIKEY") for request in environment.requests)
    assert all(value not in response.text for value in CREDENTIALS.values())


def test_market_consolidates_multiple_quote_pairs_preferring_usdt(environment):
    environment.symbols.append(pair("BTC", "BRL"))
    environment.market_tickers.append(ticker("BTCBRL", price="300000", change="30", quote_volume="900000"))
    response = environment.client.get("/api/market")
    assert response.status_code == 200
    btc = next(asset for asset in response.json()["assets"] if asset["symbol"] == "BTC")
    assert btc["pair"] == "BTCUSDT"
    assert sum(asset["symbol"] == "BTC" for asset in response.json()["assets"]) == 1


def test_market_excludes_inactive_symbols_and_keeps_unpriced_assets(environment):
    environment.symbols.extend([
        pair("OLD", "USDT", status="BREAK"),
        pair("MYSTERY", "ODD"),
    ])
    environment.market_tickers.append(ticker("MYSTERYODD", price="0.5"))
    response = environment.client.get("/api/market")
    assert response.status_code == 200
    assets = {asset["symbol"]: asset for asset in response.json()["assets"]}
    assert "OLD" not in assets
    assert assets["MYSTERY"]["pair"] == "MYSTERYODD"
    assert assets["MYSTERY"]["price_usdt"] is None
    assert assets["MYSTERY"]["volume_usdt_24h"] is None


def test_market_retains_assets_without_ticker_with_unavailable_metrics(environment):
    environment.symbols.append(pair("NOTICKER", "USDT"))
    response = environment.client.get("/api/market")
    assert response.status_code == 200
    item = next(asset for asset in response.json()["assets"] if asset["symbol"] == "NOTICKER")
    assert item["pair"] == "NOTICKERUSDT"
    assert item["price_usdt"] is None
    assert item["change_percent_24h"] is None


def test_market_cache_limits_repeat_and_manual_refresh_calls(environment):
    first = environment.client.get("/api/market")
    second = environment.client.get("/api/market")
    refresh = environment.client.get("/api/market?refresh=true")
    assert first.status_code == second.status_code == refresh.status_code == 200
    assert first.json() == second.json() == refresh.json()
    paths = [request.url.path for request in environment.requests]
    assert paths.count("/api/v3/exchangeInfo") == 1
    assert paths.count("/api/v3/ticker/24hr") == 1


def test_market_returns_clear_binance_error(environment):
    environment.failures["/api/v3/ticker/24hr"] = (429, {"code": -1003, "msg": "too many requests"}, {"Retry-After": "15"})
    response = environment.client.get("/api/market")
    assert response.status_code == 429
    assert response.json()["code"] == "rate_limit"
    assert response.headers["Retry-After"] == "15"
    assert all(value not in response.text for value in CREDENTIALS.values())


def test_market_network_failure_is_reported_without_secrets(environment):
    environment.failures["/api/v3/ticker/24hr"] = httpx.ConnectError("network detail")
    response = environment.client.get("/api/market")
    assert response.status_code == 502
    assert response.json()["code"] == "connection_error"
    assert "network detail" not in response.text
