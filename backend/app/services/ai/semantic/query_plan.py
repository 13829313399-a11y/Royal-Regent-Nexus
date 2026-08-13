from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from zoneinfo import ZoneInfo

SHANGHAI = ZoneInfo("Asia/Shanghai")


class AISemanticNormalizationError(ValueError):
    pass


def normalize_business_id(value: str) -> str:
    normalized = value.strip()
    if not normalized or len(normalized) > 128:
        raise AISemanticNormalizationError("business identifier is invalid")
    return normalized


def normalize_date(value: str) -> str:
    raw = value.strip()
    try:
        if "T" not in raw and " " not in raw:
            return date.fromisoformat(raw).isoformat()
        parsed = datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError as exc:
        raise AISemanticNormalizationError("date is invalid") from exc
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=SHANGHAI)
    return parsed.astimezone(SHANGHAI).date().isoformat()


def normalize_datetime(value: str) -> str:
    raw = value.strip()
    try:
        parsed = datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError as exc:
        raise AISemanticNormalizationError("datetime is invalid") from exc
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=SHANGHAI)
    return parsed.astimezone(SHANGHAI).isoformat(timespec="seconds")


@dataclass(frozen=True, slots=True)
class NormalizedQuantity:
    amount: Decimal
    unit: str


_UNIT_ALIASES = {
    "pcs": "PCS",
    "pc": "PCS",
    "件": "PCS",
    "个": "PCS",
    "kg": "KG",
    "公斤": "KG",
    "千克": "KG",
}


def normalize_quantity(amount: str, unit: str) -> NormalizedQuantity:
    try:
        normalized_amount = Decimal(amount.strip())
    except InvalidOperation as exc:
        raise AISemanticNormalizationError("quantity is invalid") from exc
    if not normalized_amount.is_finite() or normalized_amount < 0:
        raise AISemanticNormalizationError("quantity is invalid")
    normalized_unit = _UNIT_ALIASES.get(unit.strip().casefold())
    if normalized_unit is None:
        raise AISemanticNormalizationError("unit is unsupported")
    return NormalizedQuantity(normalized_amount, normalized_unit)


@dataclass(frozen=True, slots=True)
class NormalizedMoney:
    amount: Decimal
    currency: str


_CURRENCY_ALIASES = {
    "cny": "CNY",
    "rmb": "CNY",
    "人民币": "CNY",
    "¥": "CNY",
    "usd": "USD",
    "$": "USD",
    "美元": "USD",
}


def normalize_money(amount: str, currency: str) -> NormalizedMoney:
    quantity = normalize_quantity(amount, "件")
    normalized_currency = _CURRENCY_ALIASES.get(currency.strip().casefold())
    if normalized_currency is None:
        raise AISemanticNormalizationError("currency is unsupported")
    return NormalizedMoney(quantity.amount, normalized_currency)
