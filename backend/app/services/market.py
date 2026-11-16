"""Consulta, consolidação e cache temporário dos dados públicos Spot."""

import asyncio
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal

from ..models import ExchangeInfo, MarketAsset, MarketSnapshot, Ticker24h


@dataclass(frozen=True)
class Conversion:
    rate_usdt: Decimal
    change_factor_24h: Decimal
    path: tuple[str, ...]


def _positive(value: Decimal | None) -> bool:
    return value is not None and value > 0


def consolidate_market(info: ExchangeInfo, tickers: list[Ticker24h], *, updated_at: datetime | None = None) -> MarketSnapshot:
    """Produz uma linha por ativo base; conversões não USDT são estimativas."""
    ticker_by_symbol = {ticker.symbol: ticker for ticker in tickers}
    markets = [
        symbol for symbol in info.symbols
        if symbol.status == "TRADING" and symbol.isSpotTradingAllowed
    ]
    market_by_base: dict[str, list] = {}
    for market in markets:
        market_by_base.setdefault(market.baseAsset, []).append(market)

    # Ancora a conversão em pares USDT ativos e com volume negociado. Rotas
    # intermediárias são limitadas a três pares para evitar conversões remotas.
    conversions: dict[str, Conversion] = {"USDT": Conversion(Decimal(1), Decimal(1), ())}
    direct_candidates: dict[str, tuple[Decimal, Conversion]] = {}
    for market in markets:
        ticker = ticker_by_symbol.get(market.symbol)
        if market.quoteAsset != "USDT" or market.baseAsset == "USDT" or ticker is None:
            continue
        if not _positive(ticker.last_price) or not _positive(ticker.quote_volume):
            continue
        gross = Decimal(1) + ticker.price_change_percent / Decimal(100)
        if gross <= 0:
            continue
        candidate = Conversion(ticker.last_price, gross, (market.symbol,))
        previous = direct_candidates.get(market.baseAsset)
        if previous is None or ticker.quote_volume > previous[0]:
            direct_candidates[market.baseAsset] = (ticker.quote_volume, candidate)
    conversions.update({asset: value for asset, (_volume, value) in direct_candidates.items()})

    for _depth in range(3):
        candidates: dict[str, tuple[Decimal, Conversion]] = {}
        for market in markets:
            ticker = ticker_by_symbol.get(market.symbol)
            if ticker is None or not _positive(ticker.last_price) or not _positive(ticker.quote_volume):
                continue
            pair_factor = Decimal(1) + ticker.price_change_percent / Decimal(100)
            if pair_factor <= 0:
                continue
            base = conversions.get(market.baseAsset)
            quote = conversions.get(market.quoteAsset)
            if (base is None) == (quote is None):
                continue
            if quote is not None:
                target = market.baseAsset
                rate = ticker.last_price * quote.rate_usdt
                factor = pair_factor * quote.change_factor_24h
                path = (market.symbol, *quote.path)
                liquidity = ticker.quote_volume * quote.rate_usdt
            else:
                target = market.quoteAsset
                assert base is not None
                rate = base.rate_usdt / ticker.last_price
                factor = base.change_factor_24h / pair_factor
                path = (market.symbol, *base.path)
                liquidity = ticker.volume * base.rate_usdt
            if target in conversions or not _positive(rate) or factor <= 0:
                continue
            value = Conversion(rate, factor, path)
            previous = candidates.get(target)
            if previous is None or liquidity > previous[0]:
                candidates[target] = (liquidity, value)
        if not candidates:
            break
        conversions.update({asset: value for asset, (_liquidity, value) in candidates.items()})

    assets: list[MarketAsset] = []
    for asset, choices in market_by_base.items():
        direct = [market for market in choices if market.quoteAsset == "USDT"]
        if direct:
            selected = max(
                direct,
                key=lambda market: (
                    ticker_by_symbol[market.symbol].quote_volume if market.symbol in ticker_by_symbol else Decimal(-1),
                    market.symbol,
                ),
            )
        else:
            convertible = [market for market in choices if market.quoteAsset in conversions]
            if convertible:
                selected = max(
                    convertible,
                    key=lambda market: (
                        (ticker_by_symbol[market.symbol].quote_volume * conversions[market.quoteAsset].rate_usdt)
                        if market.symbol in ticker_by_symbol else Decimal(-1),
                        market.symbol,
                    ),
                )
            else:
                selected = max(
                    choices,
                    key=lambda market: (
                        ticker_by_symbol[market.symbol].quote_volume if market.symbol in ticker_by_symbol else Decimal(-1),
                        market.symbol,
                    ),
                )

        ticker = ticker_by_symbol.get(selected.symbol)
        quote_conversion = conversions.get(selected.quoteAsset)
        price = None
        high = low = volume = change = None
        if asset == "USDT":
            price = Decimal(1)
        if ticker is not None and quote_conversion is not None:
            if _positive(ticker.last_price) and price is None:
                price = ticker.last_price * quote_conversion.rate_usdt
            if _positive(ticker.high_price):
                high = ticker.high_price * quote_conversion.rate_usdt
            if _positive(ticker.low_price):
                low = ticker.low_price * quote_conversion.rate_usdt
            volume = ticker.quote_volume * quote_conversion.rate_usdt
            factor = (Decimal(1) + ticker.price_change_percent / Decimal(100)) * quote_conversion.change_factor_24h
            if factor > 0:
                change = (factor - Decimal(1)) * Decimal(100)

        assets.append(MarketAsset(
            asset_id=asset,
            symbol=asset,
            pair=selected.symbol,
            quote_asset=selected.quoteAsset,
            price_usdt=price,
            change_percent_24h=change,
            high_24h_usdt=high,
            low_24h_usdt=low,
            volume_usdt_24h=volume,
            conversion_path=list(quote_conversion.path) if quote_conversion else [],
            conversion_approximate=selected.quoteAsset != "USDT",
            open_time=ticker.open_time if ticker else None,
            close_time=ticker.close_time if ticker else None,
        ))

    assets.sort(key=lambda item: item.symbol)
    return MarketSnapshot(assets=assets, updated_at=updated_at or datetime.now(timezone.utc))


class MarketDataCache:
    """Cache em memória para limitar chamadas públicas de alto peso."""

    def __init__(self, ttl_seconds: float = 30, minimum_refresh_seconds: float = 10):
        self.ttl_seconds = ttl_seconds
        self.minimum_refresh_seconds = minimum_refresh_seconds
        self._snapshot: MarketSnapshot | None = None
        self._fetched_at = 0.0
        self._lock = asyncio.Lock()

    def peek(self) -> MarketSnapshot | None:
        """Retorna o último catálogo sem disparar uma nova consulta agregada."""
        return self._snapshot

    async def get(self, client, *, refresh: bool = False) -> MarketSnapshot:
        async with self._lock:
            now = time.monotonic()
            if self._snapshot is not None and not refresh and now - self._fetched_at < self.ttl_seconds:
                return self._snapshot
            if self._snapshot is not None and refresh and now - self._fetched_at < self.minimum_refresh_seconds:
                return self._snapshot
            info, tickers = await client.market_data()
            snapshot = consolidate_market(info, tickers)
            self._snapshot = snapshot
            self._fetched_at = time.monotonic()
            return snapshot
