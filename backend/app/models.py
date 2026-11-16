from datetime import datetime
from decimal import Decimal
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, SecretStr, field_validator


class Credentials(BaseModel):
    model_config = ConfigDict(extra="forbid", hide_input_in_errors=True, frozen=True)

    api_key: SecretStr = Field(min_length=1, max_length=256)
    secret_key: SecretStr = Field(min_length=1, max_length=256)

    @field_validator("api_key", "secret_key")
    @classmethod
    def validate_key(cls, value: SecretStr) -> SecretStr:
        raw = value.get_secret_value()
        if not raw.isascii() or not raw.isalnum():
            raise ValueError("Informe uma chave HMAC válida, sem espaços.")
        return value


NonNegativeDecimal = Annotated[Decimal, Field(ge=0, allow_inf_nan=False)]


class Balance(BaseModel):
    asset: str = Field(min_length=1)
    free: NonNegativeDecimal
    locked: NonNegativeDecimal


class Account(BaseModel):
    balances: list[Balance]


class MarketSymbol(BaseModel):
    symbol: str
    baseAsset: str
    quoteAsset: str
    status: str
    isSpotTradingAllowed: bool


class ExchangeInfo(BaseModel):
    symbols: list[MarketSymbol]


class Ticker(BaseModel):
    symbol: str
    price: NonNegativeDecimal


class Ticker24h(BaseModel):
    symbol: str
    last_price: NonNegativeDecimal = Field(alias="lastPrice")
    open_price: NonNegativeDecimal = Field(alias="openPrice")
    high_price: NonNegativeDecimal = Field(alias="highPrice")
    low_price: NonNegativeDecimal = Field(alias="lowPrice")
    price_change_percent: Decimal = Field(alias="priceChangePercent", allow_inf_nan=False)
    volume: NonNegativeDecimal
    quote_volume: NonNegativeDecimal = Field(alias="quoteVolume")
    open_time: int = Field(alias="openTime", ge=0)
    close_time: int = Field(alias="closeTime", ge=0)


class MarketAsset(BaseModel):
    asset_id: str
    symbol: str
    pair: str
    quote_asset: str
    price_usdt: Decimal | None
    change_percent_24h: Decimal | None
    high_24h_usdt: Decimal | None
    low_24h_usdt: Decimal | None
    volume_usdt_24h: Decimal | None
    conversion_path: list[str] = Field(default_factory=list)
    conversion_approximate: bool = False
    open_time: int | None = None
    close_time: int | None = None


class MarketSnapshot(BaseModel):
    assets: list[MarketAsset]
    updated_at: datetime


class AssetSource(BaseModel):
    wallet_id: str
    wallet: str
    available: Decimal = Decimal(0)
    locked: Decimal = Decimal(0)
    applied: Decimal = Decimal(0)
    liability: Decimal = Decimal(0)
    total: Decimal
    net_total: Decimal
    reward_notes: list[str] = Field(default_factory=list)
    position_details: list[str] = Field(default_factory=list)


class AssetView(BaseModel):
    asset: str
    free: Decimal
    locked: Decimal
    applied: Decimal = Decimal(0)
    liability: Decimal = Decimal(0)
    total: Decimal
    net_total: Decimal = Decimal(0)
    price_usdt: Decimal | None
    value_usdt: Decimal | None
    conversion_path: list[str] | None
    sources: list[AssetSource] = Field(default_factory=list)


class WalletSummary(BaseModel):
    wallet_id: str
    name: str
    status: Literal["ok", "partial", "unavailable", "unsupported"]
    asset_count: int = 0
    total_usdt: Decimal | None = None
    warning: str | None = None


class Portfolio(BaseModel):
    assets: list[AssetView]
    wallets: list[WalletSummary] = Field(default_factory=list)
    total_usdt: Decimal
    asset_count: int
    unpriced_assets: list[str]
    is_partial: bool
    updated_at: datetime
    usdt_brl_rate: Decimal | None = None
    usdt_brl_updated_at: datetime | None = None
    usdt_brl_error: str | None = None
    warnings: list[str] = Field(default_factory=list)
    coverage_notes: list[str] = Field(default_factory=list)
