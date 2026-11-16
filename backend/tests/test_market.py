import asyncio
from decimal import Decimal

import httpx
import pytest

from conftest import CREDENTIALS, pair, raw_kline


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


def test_market_klines_returns_real_ohlcv_and_available_history(environment):
    response = environment.client.get("/api/market/klines?pair=BTCUSDT&interval=1h")
    assert response.status_code == 200, response.text
    data = response.json()
    assert data["pair"] == "BTCUSDT" and data["interval"] == "1h"
    assert [candle["open_time"] for candle in data["candles"]] == [1_700_000_000_000, 1_700_003_600_000]
    assert Decimal(data["candles"][0]["open"]) == Decimal("60000")
    assert Decimal(data["candles"][0]["volume"]) == Decimal("0.5")
    assert data["earliest_open_time"] == 1_700_000_000_000
    assert data["oldest_open_time"] == data["earliest_open_time"]
    assert data["has_older"] is False
    requests = [request for request in environment.requests if request.url.path == "/api/v3/klines"]
    assert len(requests) == 2
    assert all(request.url.params.get("symbol") == "BTCUSDT" for request in requests)
    assert any(request.url.params.get("startTime") == "0" for request in requests)
    assert all("X-MBX-APIKEY" not in request.headers for request in requests)
    assert all(value not in response.text for value in CREDENTIALS.values())


def test_market_history_loads_older_pages_without_duplicate_candles(environment):
    environment.klines[("BTCUSDT", "1m")] = [
        raw_kline(index * 60_000, str(100 + index), "1") for index in range(1001)
    ]
    first = environment.client.get("/api/market/klines?pair=BTCUSDT&interval=1m")
    assert first.status_code == 200
    first_data = first.json()
    assert len(first_data["candles"]) == 500 and first_data["has_older"] is True
    older = environment.client.get(
        f"/api/market/klines?pair=BTCUSDT&interval=1m&end_time={first_data['oldest_open_time'] - 1}"
    )
    assert older.status_code == 200
    older_data = older.json()
    first_times = {candle["open_time"] for candle in first_data["candles"]}
    older_times = {candle["open_time"] for candle in older_data["candles"]}
    assert len(older_times) == 500 and first_times.isdisjoint(older_times)
    assert older_data["has_older"] is True
    oldest_page = environment.client.get(
        f"/api/market/klines?pair=BTCUSDT&interval=1m&end_time={older_data['oldest_open_time'] - 1}"
    )
    assert oldest_page.status_code == 200
    final_data = oldest_page.json()
    assert [candle["open_time"] for candle in final_data["candles"]] == [0]
    assert final_data["has_older"] is False
    all_times = first_times | older_times | {candle["open_time"] for candle in final_data["candles"]}
    assert len(all_times) == 1001


def test_market_history_is_cached_and_unknown_pairs_are_not_forwarded(environment):
    async def simultaneous():
        return await asyncio.gather(
            environment.client._http.get("/api/market/klines?pair=BTCUSDT&interval=1h"),
            environment.client._http.get("/api/market/klines?pair=BTCUSDT&interval=1h"),
        )

    first, second = environment.client.loop.run_until_complete(simultaneous())
    assert first.status_code == second.status_code == 200
    assert len([request for request in environment.requests if request.url.path == "/api/v3/klines"]) == 2
    unknown = environment.client.get("/api/market/klines?pair=NOTACOIN&interval=1h")
    assert unknown.status_code == 404 and unknown.json()["code"] == "market_pair_unknown"
    assert len([request for request in environment.requests if request.url.path == "/api/v3/klines"]) == 2


def test_market_history_distinguishes_no_available_candles(environment):
    environment.symbols.append(pair("EMPTY", "USDT"))
    response = environment.client.get("/api/market/klines?pair=EMPTYUSDT&interval=1d")
    assert response.status_code == 200
    data = response.json()
    assert data["candles"] == []
    assert data["earliest_open_time"] is None
    assert data["has_older"] is False


@pytest.mark.parametrize("interval", ["1m", "5m", "15m", "1h", "4h", "1d"])
def test_market_history_accepts_each_requested_interval(environment, interval):
    response = environment.client.get(f"/api/market/klines?pair=BTCUSDT&interval={interval}")
    assert response.status_code == 200, response.text
    assert response.json()["interval"] == interval


def test_market_history_validates_interval_and_maps_binance_errors(environment):
    invalid = environment.client.get("/api/market/klines?pair=BTCUSDT&interval=3m")
    assert invalid.status_code == 422
    assert not [request for request in environment.requests if request.url.path == "/api/v3/klines"]
    environment.failures["/api/v3/klines"] = (429, {"code": -1003}, {"Retry-After": "20"})
    limited = environment.client.get("/api/market/klines?pair=BTCUSDT&interval=1h")
    assert limited.status_code == 429 and limited.json()["code"] == "rate_limit"
    assert limited.headers["Retry-After"] == "20"


def test_market_history_rejects_malformed_candles_without_raw_details(environment):
    environment.klines[("BTCUSDT", "1h")] = [[1, "not-a-price"]]
    response = environment.client.get("/api/market/klines?pair=BTCUSDT&interval=1h")
    assert response.status_code == 502
    assert response.json()["code"] == "invalid_response"
    assert "not-a-price" not in response.text
