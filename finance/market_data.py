from __future__ import annotations

import json
from decimal import Decimal, InvalidOperation
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from django.conf import settings

from .investments import MarketDataUnavailable, quant_price
from .models import Instrument


ALPHA_VANTAGE_URL = "https://www.alphavantage.co/query"


def _provider_symbol(instrument: Instrument) -> str:
    if instrument.provider_symbol:
        return instrument.provider_symbol.upper()
    if instrument.market == Instrument.Market.IDX:
        return f"{instrument.symbol.upper()}.JK"
    return instrument.symbol.upper()


def _currency_for_instrument(instrument: Instrument) -> str:
    return (instrument.currency or "IDR").upper()


def fetch_yfinance_price(instrument: Instrument) -> dict:
    try:
        import yfinance as yf
    except ImportError as exc:
        raise MarketDataUnavailable("yfinance belum terinstall. Pakai manual price atau install yfinance.") from exc
    symbol = _provider_symbol(instrument)
    try:
        ticker = yf.Ticker(symbol)
        price = None
        fast_info = getattr(ticker, "fast_info", None)
        if fast_info:
            price = fast_info.get("last_price") or fast_info.get("regular_market_price")
        if not price:
            history = ticker.history(period="5d")
            if not history.empty:
                price = history["Close"].dropna().iloc[-1]
        if not price:
            raise MarketDataUnavailable(f"Harga {symbol} tidak ditemukan di yfinance.")
        return {
            "price": quant_price(Decimal(str(price))),
            "currency": _currency_for_instrument(instrument),
            "provider": "yfinance",
            "raw": {"symbol": symbol},
        }
    except Exception as exc:
        if isinstance(exc, MarketDataUnavailable):
            raise
        raise MarketDataUnavailable(f"Gagal ambil harga yfinance untuk {symbol}.") from exc


def fetch_alpha_vantage_price(instrument: Instrument) -> dict:
    api_key = getattr(settings, "ALPHA_VANTAGE_API_KEY", "")
    if not api_key:
        raise MarketDataUnavailable("ALPHA_VANTAGE_API_KEY belum diisi.")
    symbol = _provider_symbol(instrument)
    params = urlencode({"function": "GLOBAL_QUOTE", "symbol": symbol, "apikey": api_key})
    request = Request(f"{ALPHA_VANTAGE_URL}?{params}", headers={"User-Agent": "MoneyManagerLocal/1.0"})
    try:
        with urlopen(request, timeout=10) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except (HTTPError, URLError, TimeoutError, json.JSONDecodeError) as exc:
        raise MarketDataUnavailable(f"Gagal ambil harga Alpha Vantage untuk {symbol}.") from exc
    quote = payload.get("Global Quote") or {}
    raw_price = quote.get("05. price")
    if not raw_price:
        message = payload.get("Note") or payload.get("Information") or "Harga tidak tersedia."
        raise MarketDataUnavailable(str(message))
    try:
        price = quant_price(Decimal(str(raw_price)))
    except (InvalidOperation, ValueError) as exc:
        raise MarketDataUnavailable(f"Format harga Alpha Vantage tidak valid untuk {symbol}.") from exc
    return {
        "price": price,
        "currency": _currency_for_instrument(instrument),
        "provider": "Alpha Vantage",
        "raw": payload,
    }


def fetch_market_price(instrument: Instrument, provider: str = "auto") -> dict:
    provider = (provider or "auto").lower()
    if provider == "manual":
        raise MarketDataUnavailable("Manual price harus diinput lewat form.")
    if provider == "yfinance":
        return fetch_yfinance_price(instrument)
    if provider in {"alpha", "alpha_vantage", "alphavantage"}:
        return fetch_alpha_vantage_price(instrument)
    errors = []
    for fetcher in (fetch_yfinance_price, fetch_alpha_vantage_price):
        try:
            return fetcher(instrument)
        except MarketDataUnavailable as exc:
            errors.append(str(exc))
    raise MarketDataUnavailable("Semua provider harga gagal: " + " | ".join(errors))
