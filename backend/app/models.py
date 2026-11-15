from datetime import datetime
from decimal import Decimal
from typing import Annotated

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


class AssetView(BaseModel):
    asset: str
    free: Decimal
    locked: Decimal
    total: Decimal
    price_usdt: Decimal | None
    value_usdt: Decimal | None
    conversion_path: list[str] | None


class Portfolio(BaseModel):
    assets: list[AssetView]
    total_usdt: Decimal
    asset_count: int
    unpriced_assets: list[str]
    is_partial: bool
    updated_at: datetime
    warnings: list[str] = Field(default_factory=list)
