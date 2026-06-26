from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone as datetime_timezone
from decimal import Decimal, InvalidOperation
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from django.conf import settings
from django.utils import timezone

from .models import CurrencyConversionCheck, ExchangeRateSnapshot
from .services import money


RATE_QUANT = Decimal("0.00000001")
OPEN_EXCHANGE_RATE_URL = "https://open.er-api.com/v6/latest/{currency}"


class ExchangeRateUnavailable(Exception):
    pass


@dataclass(frozen=True)
class RateResult:
    snapshot: ExchangeRateSnapshot
    is_stale: bool = False


@dataclass(frozen=True)
class ConversionResult:
    check: CurrencyConversionCheck
    snapshot: ExchangeRateSnapshot
    rate: Decimal
    converted_amount: Decimal
    is_stale: bool


def normalize_currency(value: str) -> str:
    currency = (value or "").strip().upper()
    if len(currency) != 3 or not currency.isalpha():
        raise ExchangeRateUnavailable("Currency code harus 3 huruf, contoh USD, SGD, EUR.")
    return currency


def _api_url(base_currency: str) -> str:
    template = getattr(settings, "EXCHANGE_RATE_API_URL", OPEN_EXCHANGE_RATE_URL)
    return template.format(currency=base_currency)


def _datetime_from_unix(value) -> datetime | None:
    if not value:
        return None
    return datetime.fromtimestamp(int(value), tz=datetime_timezone.utc)


def _latest_snapshot(base_currency: str, target_currency: str = "IDR") -> ExchangeRateSnapshot | None:
    return (
        ExchangeRateSnapshot.objects.filter(base_currency=base_currency, target_currency=target_currency)
        .order_by("-fetched_at")
        .first()
    )


def _is_snapshot_fresh(snapshot: ExchangeRateSnapshot) -> bool:
    now = timezone.now()
    if snapshot.time_next_update and snapshot.time_next_update > now:
        return True
    return timezone.localtime(snapshot.fetched_at).date() == timezone.localdate()


def _fetch_snapshot(base_currency: str, target_currency: str = "IDR") -> ExchangeRateSnapshot:
    url = _api_url(base_currency)
    request = Request(url, headers={"User-Agent": "MoneyManagerLocal/1.0"})
    with urlopen(request, timeout=10) as response:
        payload = json.loads(response.read().decode("utf-8"))
    if payload.get("result") != "success":
        error = payload.get("error-type") or payload.get("result") or "unknown_error"
        raise ExchangeRateUnavailable(f"Gagal ambil kurs {base_currency}: {error}.")
    try:
        rate = Decimal(str(payload["rates"][target_currency])).quantize(RATE_QUANT)
    except (KeyError, InvalidOperation) as exc:
        raise ExchangeRateUnavailable(f"Rate {base_currency} ke {target_currency} tidak tersedia.") from exc
    return ExchangeRateSnapshot.objects.create(
        base_currency=base_currency,
        target_currency=target_currency,
        rate=rate,
        provider="ExchangeRate-API Open Access",
        provider_url=payload.get("provider") or "https://www.exchangerate-api.com",
        time_last_update=_datetime_from_unix(payload.get("time_last_update_unix")),
        time_next_update=_datetime_from_unix(payload.get("time_next_update_unix")),
        raw_response=payload,
    )


def get_exchange_rate(base_currency: str, target_currency: str = "IDR", *, force_refresh: bool = False) -> RateResult:
    base_currency = normalize_currency(base_currency)
    target_currency = normalize_currency(target_currency)
    if base_currency == target_currency:
        snapshot = ExchangeRateSnapshot.objects.create(
            base_currency=base_currency,
            target_currency=target_currency,
            rate=Decimal("1.00000000"),
            provider="System",
            provider_url="",
            raw_response={"result": "same_currency"},
        )
        return RateResult(snapshot=snapshot, is_stale=False)

    latest = _latest_snapshot(base_currency, target_currency)
    if latest and not force_refresh and _is_snapshot_fresh(latest):
        return RateResult(snapshot=latest, is_stale=False)

    try:
        return RateResult(snapshot=_fetch_snapshot(base_currency, target_currency), is_stale=False)
    except (ExchangeRateUnavailable, HTTPError, URLError, TimeoutError, json.JSONDecodeError, ValueError):
        if latest:
            return RateResult(snapshot=latest, is_stale=True)
        raise ExchangeRateUnavailable(
            f"Belum ada cache kurs {base_currency} ke {target_currency}, dan API sedang tidak bisa diakses."
        )


def convert_to_idr(source_currency: str, source_amount) -> ConversionResult:
    source_currency = normalize_currency(source_currency)
    amount = Decimal(source_amount).quantize(Decimal("0.0001"))
    result = get_exchange_rate(source_currency, "IDR")
    converted = money(amount * result.snapshot.rate)
    check = CurrencyConversionCheck.objects.create(
        source_currency=source_currency,
        source_amount=amount,
        idr_rate=result.snapshot.rate,
        converted_idr_amount=converted,
        provider=result.snapshot.provider,
        rate_is_stale=result.is_stale,
        snapshot=result.snapshot,
    )
    return ConversionResult(
        check=check,
        snapshot=result.snapshot,
        rate=result.snapshot.rate,
        converted_amount=converted,
        is_stale=result.is_stale,
    )
