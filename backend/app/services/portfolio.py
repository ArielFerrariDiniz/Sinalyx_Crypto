from collections import defaultdict, deque
from datetime import datetime, timezone
from decimal import Decimal, localcontext

from ..models import Account, AssetView, ExchangeInfo, Portfolio, Ticker


def build_portfolio(account: Account, info: ExchangeInfo, tickers: list[Ticker], warnings: list[str]) -> Portfolio:
    # Decimal permanece Decimal até a serialização Pydantic em strings JSON.
    with localcontext() as context:
        context.prec = 60
        prices = {ticker.symbol: ticker.price for ticker in tickers if ticker.price > 0}
        graph: dict[str, dict[str, Decimal]] = defaultdict(dict)
        for pair in info.symbols:
            price = prices.get(pair.symbol)
            if pair.status != "TRADING" or not pair.isSpotTradingAllowed or price is None:
                continue
            graph[pair.baseAsset][pair.quoteAsset] = price
            graph[pair.quoteAsset][pair.baseAsset] = Decimal(1) / price

        def quote(asset: str) -> tuple[Decimal | None, list[str] | None]:
            if asset == "USDT":
                return Decimal(1), ["USDT"]
            queue = deque([(asset, Decimal(1), [asset])])
            visited = {asset}
            while queue:
                current, rate, path = queue.popleft()
                if len(path) > 3:
                    continue
                # Par direto primeiro; depois menor caminho, sem ciclos e estável.
                neighbors = sorted(graph[current], key=lambda name: (name != "USDT", name))
                for target in neighbors:
                    if target in visited:
                        continue
                    converted = rate * graph[current][target]
                    if target == "USDT":
                        return converted, path + [target]
                    visited.add(target)
                    queue.append((target, converted, path + [target]))
            return None, None

        assets = []
        total_usdt = Decimal(0)
        unpriced = []
        for balance in account.balances:
            total = balance.free + balance.locked
            if total <= 0:
                continue
            price, path = quote(balance.asset)
            value = total * price if price is not None else None
            if value is None:
                unpriced.append(balance.asset)
            else:
                total_usdt += value
            assets.append(AssetView(
                asset=balance.asset, free=balance.free, locked=balance.locked,
                total=total, price_usdt=price, value_usdt=value, conversion_path=path,
            ))
        assets.sort(key=lambda asset: (asset.value_usdt is None, -(asset.value_usdt or Decimal(0)), asset.asset))
        return Portfolio(
            assets=assets, total_usdt=total_usdt, asset_count=len(assets),
            unpriced_assets=sorted(unpriced), is_partial=bool(unpriced),
            updated_at=datetime.now(timezone.utc), warnings=warnings,
        )
