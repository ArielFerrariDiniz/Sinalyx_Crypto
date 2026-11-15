"""Coleta e consolidação de saldos Binance sem somar fontes duplicadas."""

import re
from collections import defaultdict, deque
from dataclasses import dataclass, field
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation, localcontext

from ..binance_client import BinanceError, invalid_response
from ..models import AssetSource, AssetView, Credentials, ExchangeInfo, Portfolio, Ticker, WalletSummary

ZERO = Decimal("0")
PAGE_SIZE = 100
MAX_POSITION_PAGES = 100

# A API Wallet identifica algumas modalidades por nome, mas os endpoints
# especializados abaixo são a fonte de saldo canônica para evitar duplicatas.
SPECIALIZED_WALLET_KINDS = {"spot", "margin", "futures", "specialized_earn"}

COVERAGE_NOTES = [
    "Cobertura desta consulta: Spot, Simple Earn Flexible/Locked, On-chain Yields Locked, BFUSD/RWUSD, Funding quando exposto pela API Wallet, Margin Cross/Isolated e saldos/margens Futures USDⓈ-M/COIN-M. On-chain Yields Flexible é informado apenas como subtotal agregado em USDT. Staking legado, ETH/SOL Staking, Options, Portfolio Margin, empréstimos, mineração, Web3, subcontas e outros serviços não estão discriminados; o patrimônio Binance permanece parcial.",
]


@dataclass
class Position:
    wallet_id: str
    wallet: str
    asset: str
    available: Decimal = ZERO
    locked: Decimal = ZERO
    applied: Decimal = ZERO
    liability: Decimal = ZERO
    net_override: Decimal | None = None
    reward_notes: list[str] = field(default_factory=list)
    position_details: list[str] = field(default_factory=list)

    @property
    def total(self) -> Decimal:
        return self.available + self.locked + self.applied

    @property
    def net_total(self) -> Decimal:
        return self.net_override if self.net_override is not None else self.total - self.liability


@dataclass
class WalletState:
    wallet_id: str
    name: str
    status: str = "unavailable"
    warning: str | None = None
    fallback_usdt: Decimal | None = None
    asset_count: int = 0
    total_usdt: Decimal | None = None
    positions: list[Position] = field(default_factory=list)


def _decimal(value, *, default: Decimal | None = None, signed: bool = False) -> Decimal:
    if value is None and default is not None:
        return default
    if isinstance(value, bool) or not isinstance(value, (str, int, Decimal)):
        raise ValueError("valor numérico inválido")
    try:
        number = Decimal(str(value))
    except (InvalidOperation, ValueError):
        raise ValueError("valor numérico inválido") from None
    if not number.is_finite() or (not signed and number < 0):
        raise ValueError("valor numérico fora do intervalo")
    return number


def _record(raw, required: tuple[str, ...] = ()) -> dict:
    if not isinstance(raw, dict) or any(not isinstance(raw.get(key), str) or not raw[key] for key in required):
        raise ValueError("registro inesperado")
    return raw


def _asset(raw: dict) -> str:
    value = raw.get("asset")
    if not isinstance(value, str) or not value or len(value) > 32:
        raise ValueError("ativo inesperado")
    return value.upper()


def _wallet(states: dict[str, WalletState], wallet_id: str, name: str) -> WalletState:
    if wallet_id not in states:
        states[wallet_id] = WalletState(wallet_id, name)
    return states[wallet_id]


def _set_failure(state: WalletState, error: Exception, *, partial: bool = False):
    state.status = "partial" if state.positions else "unavailable"
    if isinstance(error, BinanceError):
        state.warning = error.message
    else:
        state.warning = "A Binance retornou dados inesperados para esta carteira."


def _add(state: WalletState, position: Position):
    state.positions.append(position)


def _parse_page(data) -> tuple[list[dict], int | None]:
    if not isinstance(data, dict) or not isinstance(data.get("rows"), list):
        raise ValueError("resposta paginada inválida")
    total = data.get("total")
    if total is not None and (type(total) is not int or total < 0):
        raise ValueError("total de páginas inválido")
    if not all(isinstance(row, dict) for row in data["rows"]):
        raise ValueError("registro de posição inválido")
    return data["rows"], total


async def _position_pages(client, credentials, path: str) -> tuple[list[dict], bool, Exception | None]:
    rows: list[dict] = []
    total: int | None = None
    for page in range(1, MAX_POSITION_PAGES + 1):
        try:
            data = await client.portfolio_endpoint(
                path, credentials, params={"current": page, "size": PAGE_SIZE}
            )
            page_rows, reported_total = _parse_page(data)
        except Exception as error:
            return rows, False, error
        if total is None:
            total = reported_total
        elif reported_total is not None and total != reported_total:
            return rows, False, ValueError("total de posições inconsistente")
        rows.extend(page_rows)
        if total is not None and len(rows) >= total:
            return rows, True, None
        if len(page_rows) < PAGE_SIZE:
            return rows, total is None or len(rows) >= total, None
    return rows, False, ValueError("limite defensivo de paginação atingido")


def _display_reward(asset: object, amount: object, label: str) -> str | None:
    if not isinstance(asset, str) or not asset:
        return None
    try:
        value = _decimal(amount)
    except ValueError:
        return None
    if value == 0:
        return None
    # Informação de rendimento, nunca adicionada à quantidade contabilizada.
    return f"{label}: {value} {asset.upper()} (informativo; não somado)"


def _display_apr(value: object, label: str) -> str | None:
    try:
        percentage = _decimal(value) * Decimal(100)
    except ValueError:
        return None
    return f"{label}: {format(percentage.normalize(), 'f')}% a.a. (informativo)"


def _add_flexible(state: WalletState, row: dict):
    row = _record(row, ("asset",))
    amount = _decimal(row.get("totalAmount"))
    if amount <= 0:
        return
    notes = []
    note = _display_reward(row.get("rewardAsset") or row.get("asset"), row.get("cumulativeTotalRewards"), "Recompensas acumuladas")
    if note:
        notes.append(note)
    for field_name, label in (("yesterdayRealTimeRewards", "Rendimento de ontem"), ("yesterdayAirdropRewards", "Airdrop de ontem")):
        note = _display_reward(row.get("airDropAsset") or row["asset"], row.get(field_name), label)
        if note:
            notes.append(note)
    details = []
    apr = _display_apr(row.get("latestAnnualPercentageRate"), "APR atual")
    if apr:
        details.append(apr)
    _add(state, Position(state.wallet_id, state.name, _asset(row), applied=amount,
                         reward_notes=notes, position_details=details))


def _add_locked(state: WalletState, row: dict):
    row = _record(row, ("asset",))
    amount = _decimal(row.get("amount"))
    if amount <= 0:
        return
    notes = []
    for asset_field, amount_field, label in (
        ("rewardAsset", "rewardAmt", "Recompensa informada"),
        ("extraRewardAsset", "estExtraRewardAmt", "Recompensa extra estimada"),
        ("boostRewardAsset", "totalBoostRewardAmt", "Recompensa boost informada"),
    ):
        note = _display_reward(row.get(asset_field) or row["asset"], row.get(amount_field), label)
        if note:
            notes.append(note)
    details = []
    duration = row.get("duration")
    if duration is not None:
        try:
            details.append(f"Prazo: {format(_decimal(duration), 'f')} dias")
        except ValueError:
            pass
    for field_name, label in (("APY", "APY"), ("extraRewardAPR", "APR extra"), ("boostApr", "APR boost")):
        apr = _display_apr(row.get(field_name), label)
        if apr:
            details.append(apr)
    next_pay = _display_reward(row.get("rewardAsset") or row["asset"], row.get("nextPay"), "Próximo rendimento estimado")
    if next_pay:
        next_date = row.get("nextPayDate")
        if type(next_date) is int and next_date >= 0:
            try:
                date = datetime.fromtimestamp(next_date / 1000, timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
                next_pay += f" em {date}"
            except (OverflowError, OSError, ValueError):
                pass
        details.append(next_pay)
    _add(state, Position(state.wallet_id, state.name, _asset(row), applied=amount,
                         reward_notes=notes, position_details=details))


def _add_onchain_locked(state: WalletState, row: dict):
    row = _record(row, ("asset",))
    amount = _decimal(row.get("amount"))
    if amount <= 0:
        return
    notes = []
    note = _display_reward(row.get("rewardAsset") or row["asset"], row.get("rewardAmt"), "Rendimento reportado")
    if note:
        notes.append(note)
    details = []
    for field_name, label in (("duration", "Prazo"), ("APY", "APY")):
        value = row.get(field_name)
        if value is None:
            continue
        try:
            number = _decimal(value)
        except ValueError:
            continue
        if field_name == "APY":
            number *= Decimal(100)
            details.append(f"{label}: {format(number.normalize(), 'f')}% a.a. (informativo)")
        else:
            details.append(f"{label}: {format(number, 'f')} dias")
    next_pay = _display_reward(row.get("rewardAsset") or row["asset"], row.get("nextPay"), "Próximo rendimento estimado")
    if next_pay:
        details.append(next_pay)
    redeeming = row.get("redeemingAmt")
    if redeeming is not None:
        try:
            redeeming_amount = _decimal(redeeming)
            if redeeming_amount > 0:
                details.append(f"Em resgate informado: {format(redeeming_amount, 'f')} {row['asset'].upper()} (não somado separadamente)")
        except ValueError:
            pass
    _add(state, Position(state.wallet_id, state.name, _asset(row), applied=amount,
                         reward_notes=notes, position_details=details))


def _parse_wallet_detail(state: WalletState, row: dict):
    row = _record(row, ("asset",))
    asset = _asset(row)
    available = _decimal(row.get("free"), default=ZERO)
    locked = _decimal(row.get("locked"), default=ZERO)
    applied = _decimal(row.get("freeze"), default=ZERO) + _decimal(row.get("withdrawing"), default=ZERO)
    if available + locked + applied > 0:
        _add(state, Position(state.wallet_id, state.name, asset, available, locked, applied))


def _wallet_name_kind(name: str) -> str:
    normalized = " ".join(name.strip().lower().replace("ⓢ", "s").split())
    if "fund" in normalized:
        return "funding"
    if "spot" in normalized or normalized == "main":
        return "spot"
    if "margin" in normalized:
        return "margin"
    if "future" in normalized or normalized.startswith(("um ", "cm ")):
        return "futures"
    if ("simple earn" in normalized or "on-chain yields" in normalized or "onchain yields" in normalized
            or normalized in {"bfusd", "rwusd"}):
        return "specialized_earn"
    if "staking" in normalized:
        return "unsupported"
    if "earn" in normalized:
        return "earn"
    if "option" in normalized or "portfolio" in normalized:
        return "unsupported"
    return "other"


def _other_wallet_id(name: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "_", name.lower()).strip("_")[:32] or "wallet"
    return f"other_{slug}"


def _parse_derivative_account(data, *, wallet_id: str, name: str) -> list[Position]:
    if not isinstance(data, dict) or not isinstance(data.get("assets"), list) or not all(
        isinstance(row, dict) for row in data["assets"]
    ):
        raise ValueError("resposta de conta derivativa inválida")
    result = []
    for raw in data["assets"]:
        row = _record(raw, ("asset",))
        wallet_balance = _decimal(row.get("walletBalance"))
        unrealized = _decimal(row.get("unrealizedProfit"), default=ZERO, signed=True)
        margin_balance = _decimal(row.get("marginBalance"), signed=True)
        initial_margin = _decimal(row.get("initialMargin"), default=ZERO)
        position_margin = _decimal(row.get("positionInitialMargin"), default=ZERO)
        order_margin = _decimal(row.get("openOrderInitialMargin"), default=ZERO)
        applied = min(wallet_balance, max(initial_margin, position_margin + order_margin))
        available = wallet_balance - applied
        # O patrimônio usa marginBalance uma única vez; os campos de posição,
        # inclusive notional/notionalValue, não entram no cálculo.
        if wallet_balance == 0 and margin_balance == 0 and applied == 0:
            continue
        details = [f"Saldo de carteira Binance: {wallet_balance}"]
        if applied:
            details.append(f"Margem inicial aplicada: {applied}")
        if unrealized:
            details.append(f"PnL não realizado reportado: {unrealized}")
        result.append(Position(
            wallet_id, name, _asset(row),
            available=available, applied=applied,
            net_override=margin_balance, position_details=details,
        ))
    return result


def _market_quote(info: ExchangeInfo, tickers: list[Ticker]):
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
            for target in sorted(graph[current], key=lambda name: (name != "USDT", name)):
                if target in visited:
                    continue
                converted = rate * graph[current][target]
                if target == "USDT":
                    return converted, path + [target]
                visited.add(target)
                queue.append((target, converted, path + [target]))
        return None, None
    return quote


def _consolidate(positions: list[Position], states: dict[str, WalletState], info: ExchangeInfo,
                 tickers: list[Ticker], warnings: list[str]) -> Portfolio:
    with localcontext() as context:
        context.prec = 60
        quote = _market_quote(info, tickers)
        # Somar posições repetidas pelo ativo e pela carteira, sem repetir os
        # resumos da API nem as fontes gerais que duplicam APIs especializadas.
        combined: dict[tuple[str, str], Position] = {}
        for position in positions:
            key = (position.wallet_id, position.asset)
            current = combined.get(key)
            if current is None:
                combined[key] = position
                continue
            if current.net_override is not None or position.net_override is not None:
                current.net_override = current.net_total + position.net_total
            current.available += position.available
            current.locked += position.locked
            current.applied += position.applied
            current.liability += position.liability
            current.reward_notes.extend(note for note in position.reward_notes if note not in current.reward_notes)
            current.position_details.extend(note for note in position.position_details if note not in current.position_details)
        wallet_rows: dict[str, list[Position]] = defaultdict(list)
        asset_rows: dict[str, list[Position]] = defaultdict(list)
        for position in combined.values():
            if position.total == 0 and position.liability == 0 and position.net_total == 0:
                continue
            wallet_rows[position.wallet_id].append(position)
            asset_rows[position.asset].append(position)

        wallets: list[WalletSummary] = []
        portfolio_total = ZERO
        any_unknown_wallet_value = False
        for state in states.values():
            rows = wallet_rows.get(state.wallet_id, [])
            state.asset_count = len({row.asset for row in rows})
            if state.fallback_usdt is not None:
                state.total_usdt = state.fallback_usdt
                portfolio_total += state.fallback_usdt
            elif state.status in ("unavailable", "unsupported"):
                state.total_usdt = None
                any_unknown_wallet_value = True
            else:
                valued = ZERO
                priced = True
                for row in rows:
                    price, _ = quote(row.asset)
                    if price is None:
                        priced = False
                    else:
                        valued += row.net_total * price
                # Contabiliza os saldos com cotação conhecida e informa o
                # subtotal parcial; não descarta a carteira inteira quando
                # apenas um de seus ativos não tem preço confiável.
                state.total_usdt = valued
                portfolio_total += valued
                if not priced:
                    any_unknown_wallet_value = True
                    state.status = "partial"
                    quote_warning = "Um ou mais ativos desta carteira não têm cotação USDT confiável; o subtotal considera somente os ativos cotados."
                    state.warning = f"{state.warning} {quote_warning}" if state.warning else quote_warning
            wallets.append(WalletSummary(
                wallet_id=state.wallet_id, name=state.name, status=state.status,
                asset_count=state.asset_count, total_usdt=state.total_usdt, warning=state.warning,
            ))

        assets: list[AssetView] = []
        unpriced: list[str] = []
        for asset, rows in asset_rows.items():
            free = sum((row.available for row in rows), ZERO)
            locked = sum((row.locked for row in rows), ZERO)
            applied = sum((row.applied for row in rows), ZERO)
            liability = sum((row.liability for row in rows), ZERO)
            total = sum((row.total for row in rows), ZERO)
            net_total = sum((row.net_total for row in rows), ZERO)
            price, path = quote(asset)
            value = net_total * price if price is not None else None
            if value is None:
                unpriced.append(asset)
            sources = [AssetSource(
                wallet_id=row.wallet_id, wallet=row.wallet,
                available=row.available, locked=row.locked, applied=row.applied,
                liability=row.liability, total=row.total, net_total=row.net_total,
                reward_notes=row.reward_notes,
                position_details=row.position_details,
            ) for row in sorted(rows, key=lambda item: (item.wallet, item.wallet_id))]
            assets.append(AssetView(
                asset=asset, free=free, locked=locked, applied=applied, liability=liability,
                total=total, net_total=net_total, price_usdt=price, value_usdt=value,
                conversion_path=path, sources=sources,
            ))
        assets.sort(key=lambda item: (item.value_usdt is None, -(item.value_usdt or ZERO), item.asset))
        status_incomplete = any(item.status != "ok" for item in wallets)
        return Portfolio(
            assets=assets, wallets=wallets, total_usdt=portfolio_total,
            asset_count=len(assets), unpriced_assets=sorted(unpriced),
            is_partial=bool(unpriced or status_incomplete or any_unknown_wallet_value or COVERAGE_NOTES),
            updated_at=datetime.now(timezone.utc), warnings=list(dict.fromkeys(warnings)),
            coverage_notes=COVERAGE_NOTES.copy(),
        )


async def collect_portfolio(client, credentials: Credentials, session_warnings: list[str]) -> Portfolio:
    states: dict[str, WalletState] = {}
    positions: list[Position] = []
    warnings = list(session_warnings)
    spot = _wallet(states, "spot", "Spot")
    flexible = _wallet(states, "earn_flexible", "Simple Earn Flexible")
    locked = _wallet(states, "earn_locked", "Simple Earn Locked")
    funding = _wallet(states, "funding", "Funding")
    cross = _wallet(states, "margin_cross", "Margin Cross")
    isolated = _wallet(states, "margin_isolated", "Margin Isolated")
    usdm = _wallet(states, "futures_usdm", "Futures USDⓈ-M")
    coinm = _wallet(states, "futures_coinm", "Futures COIN-M")
    bfusd = _wallet(states, "earn_bfusd", "BFUSD")
    rwusd = _wallet(states, "earn_rwusd", "RWUSD")
    onchain_flexible = _wallet(states, "onchain_flexible", "On-chain Yields Flexible (agregado)")
    onchain_locked = _wallet(states, "onchain_locked", "On-chain Yields Locked")
    staking = _wallet(states, "staking_legacy", "Staking legado")
    staking.status = "unsupported"
    staking.warning = "A Binance lista uma rota de posição de Staking legado, mas o esquema atual de resposta não pôde ser validado com detalhe suficiente para contabilização segura."

    try:
        account = await client.account(credentials)
        spot.status = "ok"
        for balance in account.balances:
            if balance.free + balance.locked > 0:
                position = Position("spot", "Spot", balance.asset.upper(), balance.free, balance.locked)
                positions.append(position)
                spot.positions.append(position)
    except Exception as error:
        _set_failure(spot, error)

    # Simple Earn account é apenas um resumo para fallback/verificação; nunca
    # é somado ao mesmo tempo que posições individuais.
    earn_summary = None
    earn_summary_error = None
    try:
        earn_summary = await client.portfolio_endpoint("/sapi/v1/simple-earn/account", credentials)
        if not isinstance(earn_summary, dict):
            raise ValueError("resumo Earn inválido")
        flexible.fallback_usdt = _decimal(earn_summary.get("totalFlexibleAmountInUSDT"))
        locked.fallback_usdt = _decimal(earn_summary.get("totalLockedInUSDT"))
    except Exception as error:
        earn_summary_error = error

    flexible_rows, flexible_complete, flexible_error = await _position_pages(
        client, credentials, "/sapi/v1/simple-earn/flexible/position"
    )
    try:
        for row in flexible_rows:
            _add_flexible(flexible, row)
        if flexible_error:
            _set_failure(flexible, flexible_error)
        else:
            flexible.status = "ok" if flexible_complete else "partial"
            if not flexible_complete:
                flexible.warning = "A consulta paginada de posições Flexible não foi concluída."
    except Exception:
        flexible.status = "partial" if flexible.positions else "unavailable"
        flexible.warning = "Uma ou mais posições Flexible continham dados inválidos."
    positions.extend(flexible.positions)
    if (flexible.status == "ok" and not flexible.positions and flexible.fallback_usdt is not None
            and flexible.fallback_usdt > 0):
        flexible.status = "partial"
        flexible.warning = "O resumo informa saldo Flexible, mas a consulta de posições não retornou ativos; subtotal agregado usado sem inventar moedas."
    elif flexible.status != "ok":
        if flexible.fallback_usdt is not None and not flexible.positions:
            flexible.status = "partial"
            flexible.warning = "As posições individuais Flexible não puderam ser consultadas; subtotal estimado pelo resumo Simple Earn da Binance."
        elif flexible.warning is None:
            flexible.warning = "O resumo de Simple Earn não confirmou o saldo Flexible."
        if flexible.warning:
            warnings.append(f"Simple Earn Flexible: {flexible.warning}")
    else:
        flexible.fallback_usdt = None
    if flexible.status == "ok" and earn_summary_error:
        warnings.append("O resumo Simple Earn não foi consultado, mas as posições Flexible estão disponíveis.")

    locked_rows, locked_complete, locked_error = await _position_pages(
        client, credentials, "/sapi/v1/simple-earn/locked/position"
    )
    try:
        for row in locked_rows:
            _add_locked(locked, row)
        if locked_error:
            _set_failure(locked, locked_error)
        else:
            locked.status = "ok" if locked_complete else "partial"
            if not locked_complete:
                locked.warning = "A consulta paginada de posições Locked não foi concluída."
    except Exception:
        locked.status = "partial" if locked.positions else "unavailable"
        locked.warning = "Uma ou mais posições Locked continham dados inválidos."
    positions.extend(locked.positions)
    if locked.status == "ok" and not locked.positions and locked.fallback_usdt is not None and locked.fallback_usdt > 0:
        locked.status = "partial"
        locked.warning = "O resumo informa saldo Locked, mas a consulta de posições não retornou ativos; subtotal agregado usado sem inventar moedas."
    elif locked.status != "ok":
        if locked.fallback_usdt is not None and not locked.positions:
            locked.status = "partial"
            locked.warning = "As posições individuais Locked não puderam ser consultadas; subtotal estimado pelo resumo Simple Earn da Binance."
        elif locked.warning is None:
            locked.warning = "O resumo de Simple Earn não confirmou o saldo Locked."
        if locked.warning:
            warnings.append(f"Simple Earn Locked: {locked.warning}")
    else:
        locked.fallback_usdt = None
    if locked.status == "ok" and earn_summary_error:
        warnings.append("O resumo Simple Earn não foi consultado, mas as posições Locked estão disponíveis.")

    # On-chain Yields só oferece um resumo agregado para Flexible. Locked tem
    # posições por ativo e usa o resumo apenas como fallback, nunca em paralelo.
    onchain_summary = None
    try:
        onchain_summary = await client.portfolio_endpoint("/sapi/v1/onchain-yields/account", credentials)
        if not isinstance(onchain_summary, dict):
            raise ValueError("resumo On-chain Yields inválido")
        flexible_total = _decimal(onchain_summary.get("totalFlexibleAmountInUSDT"))
        locked_total = _decimal(onchain_summary.get("totalLockedInUSDT"))
        if flexible_total > 0:
            onchain_flexible.fallback_usdt = flexible_total
            onchain_flexible.status = "partial"
            onchain_flexible.warning = "A Binance informa somente o subtotal em USDT, sem detalhar os ativos; incluído no total, mas não na tabela por ativo."
        else:
            onchain_flexible.status = "ok"
            onchain_flexible.fallback_usdt = ZERO
    except Exception as error:
        _set_failure(onchain_flexible, error)
        locked_total = None

    onchain_rows, onchain_complete, onchain_error = await _position_pages(
        client, credentials, "/sapi/v1/onchain-yields/locked/position"
    )
    try:
        for row in onchain_rows:
            _add_onchain_locked(onchain_locked, row)
        if onchain_error:
            _set_failure(onchain_locked, onchain_error)
        else:
            onchain_locked.status = "ok" if onchain_complete else "partial"
            if not onchain_complete:
                onchain_locked.warning = "A consulta paginada de posições On-chain Yields Locked não foi concluída."
    except Exception:
        onchain_locked.status = "partial" if onchain_locked.positions else "unavailable"
        onchain_locked.warning = "Uma ou mais posições On-chain Yields Locked continham dados inválidos."
    positions.extend(onchain_locked.positions)
    if onchain_locked.status == "ok" and not onchain_locked.positions and locked_total is not None and locked_total > 0:
        onchain_locked.fallback_usdt = locked_total
        onchain_locked.status = "partial"
        onchain_locked.warning = "O resumo informa saldo Locked, mas a consulta paginada não retornou posições; subtotal agregado usado sem inventar ativos."
    elif onchain_locked.status != "ok":
        if not onchain_locked.positions and locked_total is not None:
            onchain_locked.fallback_usdt = locked_total
            onchain_locked.status = "partial"
            onchain_locked.warning = "As posições Locked não puderam ser detalhadas; subtotal agregado em USDT informado pela Binance."
        elif onchain_locked.warning is None:
            onchain_locked.warning = "As posições On-chain Yields Locked não foram confirmadas."
    elif locked_total is not None:
        onchain_locked.fallback_usdt = None

    # O balanço detalhado Wallet enumera os tipos de carteira ativos. Para os
    # produtos com consulta especializada, essa resposta serve só para detectar
    # cobertura e NÃO é somada uma segunda vez.
    funding_seen = False
    try:
        wallet_data = await client.portfolio_endpoint(
            "/sapi/v1/asset/wallet/balance", credentials,
            params={"needBalanceDetail": "true", "quoteAsset": "USDT"},
        )
        if not isinstance(wallet_data, list) or not all(isinstance(item, dict) for item in wallet_data):
            raise ValueError("lista de carteiras inválida")
        for item in wallet_data:
            name = item.get("walletName")
            if not isinstance(name, str) or not name:
                raise ValueError("nome da carteira ausente")
            kind = _wallet_name_kind(name)
            if kind == "funding":
                funding_seen = True
                if not funding.positions:
                    detail = item.get("assetBalances")
                    if not isinstance(detail, list):
                        raise ValueError("detalhes Funding ausentes")
                    for row in detail:
                        _parse_wallet_detail(funding, row)
                    positions.extend(funding.positions)
                    funding.status = "ok"
                continue
            if kind in SPECIALIZED_WALLET_KINDS:
                continue
            if kind == "unsupported":
                wallet_id = "staking_legacy" if "staking" in name.lower() else _other_wallet_id(name)
                other = _wallet(states, wallet_id, "Staking legado" if wallet_id == "staking_legacy" else name[:80])
                other.status = "unsupported"
                other.warning = "Esta carteira não é contabilizada nesta versão para evitar declarar uma cobertura que ainda não foi validada."
                continue
            if kind == "earn":
                other = _wallet(states, _other_wallet_id(name), f"{name[:64]} (agregado)")
                other.status = "unsupported"
                other.warning = "A Binance retornou uma carteira Earn agregada que pode incluir produtos já consultados; não somada para evitar dupla contagem."
                continue
            # Carteiras desconhecidas entram com o nome fornecido pela API.
            other = _wallet(states, _other_wallet_id(name), name[:80])
            detail = item.get("assetBalances")
            if not isinstance(detail, list):
                other.status = "partial"
                other.warning = "A Binance não forneceu os saldos detalhados desta carteira."
                continue
            try:
                for row in detail:
                    _parse_wallet_detail(other, row)
                other.status = "ok"
            except Exception:
                other.status = "partial" if other.positions else "unavailable"
                other.warning = "A Binance retornou detalhes inválidos para esta carteira adicional."
            positions.extend(other.positions)
    except Exception as error:
        _set_failure(_wallet(states, "wallet_inventory", "Inventário de carteiras adicionais"), error)

    if not funding_seen:
        try:
            funding_data = await client.portfolio_endpoint(
                "/sapi/v1/asset/get-funding-asset", credentials, method="POST",
                params={"needBtcValuation": "true"},
            )
            if not isinstance(funding_data, list) or not all(isinstance(row, dict) for row in funding_data):
                raise ValueError("resposta Funding inválida")
            for row in funding_data:
                _parse_wallet_detail(funding, row)
            positions.extend(funding.positions)
            funding.status = "partial"
            funding.warning = "A Binance documenta esta consulta para ativos de serviços de negócio (Pay, Card, Gift Card e Stock Token); não confirma todos os ativos da carteira Funding."
        except Exception as error:
            _set_failure(funding, error)
        if funding.warning:
            warnings.append(f"Funding: {funding.warning}")

    # Margin usa netAsset informado pela Binance; empréstimos e juros reduzem
    # o patrimônio. Os saldos isolados são separados por par para não perder origem.
    try:
        data = await client.portfolio_endpoint("/sapi/v1/margin/account", credentials)
        if not isinstance(data, dict) or type(data.get("created")) is not bool:
            raise ValueError("resposta Margin Cross inválida")
        assets = data.get("userAssets", [])
        if not isinstance(assets, list):
            raise ValueError("lista Margin Cross inválida")
        if data["created"]:
            for row in assets:
                row = _record(row, ("asset",))
                free, reserved = _decimal(row.get("free")), _decimal(row.get("locked"))
                borrowed, interest = _decimal(row.get("borrowed")), _decimal(row.get("interest"))
                net = _decimal(row.get("netAsset"), signed=True)
                if free + reserved + borrowed + interest != 0 or net != 0:
                    pos = Position("margin_cross", "Margin Cross", _asset(row), free, reserved,
                                   liability=borrowed + interest, net_override=net)
                    positions.append(pos)
                    cross.positions.append(pos)
        cross.status = "ok"
    except Exception as error:
        _set_failure(cross, error)

    try:
        data = await client.portfolio_endpoint("/sapi/v1/margin/isolated/account", credentials)
        if not isinstance(data, dict) or not isinstance(data.get("assets"), list):
            raise ValueError("resposta Margin Isolated inválida")
        for item in data["assets"]:
            if not isinstance(item, dict) or not isinstance(item.get("symbol"), str):
                raise ValueError("par Margin Isolated inválido")
            label = "Margin Isolated"
            wallet_id = "margin_isolated"
            for key in ("baseAsset", "quoteAsset"):
                row = item.get(key)
                if not isinstance(row, dict):
                    raise ValueError("saldo Margin Isolated inválido")
                free, reserved = _decimal(row.get("free")), _decimal(row.get("locked"))
                borrowed, interest = _decimal(row.get("borrowed")), _decimal(row.get("interest"))
                net = _decimal(row.get("netAsset"), signed=True)
                if free + reserved + borrowed + interest != 0 or net != 0:
                    pos = Position(wallet_id, label, _asset(row), free, reserved,
                                   liability=borrowed + interest, net_override=net)
                    positions.append(pos)
                    isolated.positions.append(pos)
        isolated.status = "ok"
    except Exception as error:
        _set_failure(isolated, error)

    try:
        data = await client.portfolio_endpoint("/fapi/v3/account", credentials, host="usdm")
        rows = _parse_derivative_account(data, wallet_id="futures_usdm", name=usdm.name)
        positions.extend(rows)
        usdm.positions.extend(rows)
        usdm.status = "ok"
    except Exception as error:
        _set_failure(usdm, error)

    try:
        data = await client.portfolio_endpoint("/dapi/v1/account", credentials, host="coinm")
        rows = _parse_derivative_account(data, wallet_id="futures_coinm", name=coinm.name)
        positions.extend(rows)
        coinm.positions.extend(rows)
        coinm.status = "ok"
    except Exception as error:
        _set_failure(coinm, error)

    for state, path, amount_field, reward_field, reward_label in (
        (bfusd, "/sapi/v1/bfusd/account", "bfusdAmount", "bfusdProfit", "Rendimento reportado"),
        (rwusd, "/sapi/v1/rwusd/account", "rwusdAmount", "totalProfit", "Rendimento reportado"),
    ):
        try:
            data = await client.portfolio_endpoint(path, credentials)
            if not isinstance(data, dict):
                raise ValueError("resposta Earn inválida")
            amount = _decimal(data.get(amount_field))
            asset = "BFUSD" if state is bfusd else "RWUSD"
            if amount > 0:
                note = _display_reward(asset, data.get(reward_field), reward_label)
                pos = Position(state.wallet_id, state.name, asset, applied=amount,
                               reward_notes=[note] if note else [])
                positions.append(pos)
                state.positions.append(pos)
            state.status = "ok"
        except Exception as error:
            _set_failure(state, error)

    # Consultar preço somente quando há saldo. A falta de mercado não apaga as
    # posições, apenas deixa a cotação como indisponível.
    all_positions = positions
    if all_positions:
        try:
            info, tickers = await client.market()
        except Exception as error:
            info, tickers = ExchangeInfo(symbols=[]), []
            warnings.append(error.message if isinstance(error, BinanceError) else "Não foi possível consultar os preços Spot; as cotações estão indisponíveis.")
            market_state = _wallet(states, "market_prices", "Cotações Spot")
            _set_failure(market_state, error)
    else:
        info, tickers = ExchangeInfo(symbols=[]), []

    # Resumos Simple Earn são fallback somente se a consulta de posições inteira
    # falhou; se o resumo também falhou, o subtotal fica indisponível, não zero.
    # A atribuição usa status para diferenciar sucesso vazio de erro.
    if earn_summary_error:
        warnings.append("O endpoint de resumo Simple Earn não respondeu; a cobertura Earn depende das consultas de posições.")
    for state in states.values():
        if state.warning:
            warnings.append(f"{state.name}: {state.warning}")
    return _consolidate(all_positions, states, info, tickers, warnings)
