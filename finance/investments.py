from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal, ROUND_CEILING

from django.db import transaction as db_transaction
from django.utils import timezone

from .exchange_rates import get_exchange_rate
from .formatting import format_idr
from .models import (
    Account,
    AllocationTarget,
    Debt,
    ExchangeRateSnapshot,
    FinancialFreedomProfile,
    Instrument,
    InvestmentAccount,
    InvestmentInsight,
    InvestmentTransaction,
    PriceSnapshot,
    Transaction,
)
from .services import ZERO, account_balances, first_day, money, monthly_transactions, next_month_start, total_balance


QTY = Decimal("0.0001")
PRICE = Decimal("0.0001")


class MarketDataUnavailable(Exception):
    pass


@dataclass(frozen=True)
class PriceResult:
    snapshot: PriceSnapshot
    is_stale: bool = False


def quant_qty(value) -> Decimal:
    return Decimal(value or 0).quantize(QTY)


def quant_price(value) -> Decimal:
    return Decimal(value or 0).quantize(PRICE)


def normalize_symbol(symbol: str) -> str:
    return (symbol or "").strip().upper()


def infer_instrument_defaults(symbol: str) -> dict:
    symbol = normalize_symbol(symbol)
    if symbol.endswith(".JK"):
        base_symbol = symbol[:-3]
        return {
            "symbol": base_symbol,
            "provider_symbol": symbol,
            "market": Instrument.Market.IDX,
            "currency": "IDR",
            "asset_class": Instrument.AssetClass.STOCK_ID,
            "lot_size": Decimal("100"),
        }
    # The app is Indonesia-first; bare symbols from Telegram default to IDX.
    return {
        "symbol": symbol,
        "provider_symbol": f"{symbol}.JK",
        "market": Instrument.Market.IDX,
        "currency": "IDR",
        "asset_class": Instrument.AssetClass.STOCK_ID,
        "lot_size": Decimal("100"),
    }


def get_or_create_instrument(symbol: str) -> Instrument:
    defaults = infer_instrument_defaults(symbol)
    return Instrument.objects.get_or_create(
        symbol=defaults.pop("symbol"),
        market=defaults["market"],
        defaults=defaults,
    )[0]


def get_or_create_investment_account(name: str | None) -> InvestmentAccount:
    normalized = (name or "Manual Portfolio").strip().title()
    return InvestmentAccount.objects.get_or_create(name=normalized, defaults={"platform": normalized})[0]


def quantity_from_unit(instrument: Instrument, quantity, unit: str = "") -> Decimal:
    quantity = quant_qty(quantity)
    if unit.lower() in {"lot", "lots"}:
        return (quantity * quant_qty(instrument.lot_size)).quantize(QTY)
    return quantity


@db_transaction.atomic
def record_investment_transaction(
    *,
    kind: str,
    instrument: Instrument,
    account: InvestmentAccount,
    quantity=0,
    unit: str = "",
    price=0,
    fee_amount=0,
    cash_amount=0,
    tx_date: date | None = None,
    note: str = "",
    source: str = Transaction.Source.WEB,
    source_user_id: str = "",
) -> InvestmentTransaction:
    share_quantity = quantity_from_unit(instrument, quantity, unit)
    tx = InvestmentTransaction.objects.create(
        kind=kind,
        instrument=instrument,
        account=account,
        quantity=share_quantity,
        price=quant_price(price),
        fee_amount=money(fee_amount),
        cash_amount=money(cash_amount),
        currency=instrument.currency,
        date=tx_date or timezone.localdate(),
        note=note,
        source=source,
        source_user_id=source_user_id,
    )
    if kind in {InvestmentTransaction.Kind.BUY, InvestmentTransaction.Kind.SELL} and price:
        PriceSnapshot.objects.create(
            instrument=instrument,
            price=quant_price(price),
            currency=instrument.currency,
            provider="Transaction",
        )
    return tx


def latest_price(instrument: Instrument) -> PriceSnapshot | None:
    return instrument.price_snapshots.order_by("-fetched_at").first()


def latest_fx_rate(currency: str) -> Decimal:
    currency = (currency or "IDR").upper()
    if currency == "IDR":
        return Decimal("1")
    snapshot = (
        ExchangeRateSnapshot.objects.filter(base_currency=currency, target_currency="IDR")
        .order_by("-fetched_at")
        .first()
    )
    return snapshot.rate if snapshot else Decimal("1")


def _empty_position(instrument: Instrument) -> dict:
    return {
        "instrument": instrument,
        "quantity": ZERO,
        "cost_basis": ZERO,
        "realized_gain": ZERO,
        "dividend_income": ZERO,
        "fees": ZERO,
    }


def portfolio_positions() -> list[dict]:
    positions: dict[int, dict] = {}
    txs = (
        InvestmentTransaction.objects.filter(status=InvestmentTransaction.Status.CONFIRMED)
        .select_related("instrument", "account")
        .order_by("date", "created_at", "id")
    )
    for tx in txs:
        position = positions.setdefault(tx.instrument_id, _empty_position(tx.instrument))
        quantity = quant_qty(tx.quantity)
        price = quant_price(tx.price)
        fee = money(tx.fee_amount)
        cash_amount = money(tx.cash_amount)
        if tx.kind == InvestmentTransaction.Kind.BUY:
            position["quantity"] += quantity
            position["cost_basis"] += money(quantity * price) + fee
            position["fees"] += fee
        elif tx.kind == InvestmentTransaction.Kind.SELL:
            sell_quantity = min(quantity, position["quantity"])
            average_cost = position["cost_basis"] / position["quantity"] if position["quantity"] > 0 else ZERO
            cost_removed = money(average_cost * sell_quantity)
            proceeds = money(sell_quantity * price) - fee
            position["quantity"] -= sell_quantity
            position["cost_basis"] -= cost_removed
            position["realized_gain"] += proceeds - cost_removed
            position["fees"] += fee
        elif tx.kind == InvestmentTransaction.Kind.DIVIDEND:
            position["dividend_income"] += cash_amount
        elif tx.kind == InvestmentTransaction.Kind.FEE:
            amount = cash_amount or fee
            position["fees"] += amount
            position["realized_gain"] -= amount
        elif tx.kind == InvestmentTransaction.Kind.SPLIT and price > 0:
            position["quantity"] = quant_qty(position["quantity"] * price)

    rows = []
    for position in positions.values():
        instrument = position["instrument"]
        snapshot = latest_price(instrument)
        price = snapshot.price if snapshot else ZERO
        fx_rate = latest_fx_rate(instrument.currency)
        market_value_native = money(position["quantity"] * price)
        market_value_idr = money(market_value_native * fx_rate)
        cost_basis_idr = money(position["cost_basis"] * fx_rate)
        unrealized_gain = market_value_idr - cost_basis_idr
        average_cost = position["cost_basis"] / position["quantity"] if position["quantity"] > 0 else ZERO
        rows.append(
            {
                **position,
                "latest_price": price,
                "price_snapshot": snapshot,
                "price_is_stale": bool(snapshot and snapshot.is_stale),
                "fx_rate": fx_rate,
                "market_value_native": market_value_native,
                "market_value_idr": market_value_idr,
                "cost_basis_idr": cost_basis_idr,
                "unrealized_gain": unrealized_gain,
                "total_return": unrealized_gain + position["realized_gain"] + position["dividend_income"] - position["fees"],
                "average_cost": average_cost,
            }
        )
    return sorted(rows, key=lambda item: item["market_value_idr"], reverse=True)


def portfolio_summary() -> dict:
    positions = portfolio_positions()
    total_market_value = sum((row["market_value_idr"] for row in positions), ZERO)
    total_cost = sum((row["cost_basis_idr"] for row in positions), ZERO)
    realized_gain = sum((row["realized_gain"] for row in positions), ZERO)
    dividend_income = sum((row["dividend_income"] for row in positions), ZERO)
    unrealized_gain = total_market_value - total_cost
    realized_income = realized_gain + dividend_income
    allocation = {}
    for row in positions:
        key = row["instrument"].asset_class
        allocation.setdefault(key, {"asset_class": key, "label": row["instrument"].get_asset_class_display(), "amount": ZERO})
        allocation[key]["amount"] += row["market_value_idr"]
    allocation_rows = []
    for item in allocation.values():
        percent = (item["amount"] / total_market_value * Decimal("100")) if total_market_value > 0 else ZERO
        allocation_rows.append({**item, "percent": percent})
    return {
        "positions": positions,
        "total_market_value": total_market_value,
        "total_cost": total_cost,
        "unrealized_gain": unrealized_gain,
        "realized_gain": realized_gain,
        "dividend_income": dividend_income,
        "realized_income": realized_income,
        "total_return": unrealized_gain + realized_gain + dividend_income,
        "allocation": sorted(allocation_rows, key=lambda item: item["amount"], reverse=True),
    }


def average_monthly_expense(months: int = 6) -> Decimal:
    today = timezone.localdate()
    cursor = first_day(today)
    expenses = []
    for _ in range(months):
        start = cursor
        end = next_month_start(start)
        total = ZERO
        for tx in monthly_transactions(start).filter(date__gte=start, date__lt=end):
            if tx.kind == Transaction.Kind.EXPENSE:
                total += money(tx.amount)
            elif tx.kind == Transaction.Kind.REPAYMENT and tx.debt and tx.debt.direction == Debt.Direction.PAYABLE:
                total += money(tx.amount)
        expenses.append(total)
        previous_month = cursor.month - 1 or 12
        previous_year = cursor.year - 1 if cursor.month == 1 else cursor.year
        cursor = date(previous_year, previous_month, 1)
    non_zero = [expense for expense in expenses if expense > 0]
    if not non_zero:
        return ZERO
    return money(sum(non_zero, ZERO) / Decimal(len(non_zero)))


def financial_freedom_profile() -> FinancialFreedomProfile | None:
    return FinancialFreedomProfile.objects.order_by("name").first()


def financial_freedom_summary(profile: FinancialFreedomProfile | None = None) -> dict:
    profile = profile or financial_freedom_profile()
    monthly_expense = average_monthly_expense()
    annual_expense = money(profile.annual_expense) if profile and profile.annual_expense > 0 else money(monthly_expense * Decimal("12"))
    multiplier = profile.fire_multiplier if profile else Decimal("25")
    monthly_contribution = money(profile.target_monthly_contribution) if profile else ZERO
    fire_number = money(annual_expense * multiplier)
    portfolio = portfolio_summary()
    payable_debt = sum(
        (
            money(debt.current_balance)
            for debt in Debt.objects.filter(status=Debt.Status.OPEN, direction=Debt.Direction.PAYABLE)
        ),
        ZERO,
    )
    cash_balance = total_balance()
    net_worth = money(cash_balance + portfolio["total_market_value"] - payable_debt)
    gap = max(fire_number - net_worth, ZERO)
    progress = (net_worth / fire_number * Decimal("100")) if fire_number > 0 else ZERO
    runway_months = (cash_balance / monthly_expense) if monthly_expense > 0 else ZERO
    months_to_fire = None
    if monthly_contribution > 0 and gap > 0:
        months_to_fire = int((gap / monthly_contribution).to_integral_value(rounding=ROUND_CEILING))
    elif gap == 0 and fire_number > 0:
        months_to_fire = 0
    return {
        "profile": profile,
        "monthly_expense": monthly_expense,
        "annual_expense": annual_expense,
        "fire_multiplier": multiplier,
        "fire_number": fire_number,
        "cash_balance": cash_balance,
        "portfolio_value": portfolio["total_market_value"],
        "payable_debt": payable_debt,
        "net_worth": net_worth,
        "gap": gap,
        "progress": progress,
        "runway_months": runway_months,
        "monthly_contribution": monthly_contribution,
        "months_to_fire": months_to_fire,
    }


def _insight(fingerprint: str, **fields):
    existing = InvestmentInsight.objects.filter(fingerprint=fingerprint).first()
    if existing and existing.status in {InvestmentInsight.Status.IGNORED, InvestmentInsight.Status.DONE}:
        return
    defaults = {"fingerprint": fingerprint, "status": InvestmentInsight.Status.ACTIVE, **fields}
    if existing:
        for key, value in defaults.items():
            setattr(existing, key, value)
        existing.save()
    else:
        InvestmentInsight.objects.create(**defaults)


def generate_investment_insights() -> list[InvestmentInsight]:
    InvestmentInsight.objects.filter(status=InvestmentInsight.Status.ACTIVE).delete()
    portfolio = portfolio_summary()
    fire = financial_freedom_summary()
    total_value = portfolio["total_market_value"]
    if fire["fire_number"] > 0 and fire["gap"] > 0:
        _insight(
            "fire-gap",
            type="fire_gap",
            severity=InvestmentInsight.Severity.INFO,
            title="FIRE gap masih perlu dikejar",
            reason=(
                f"Net worth {format_idr(fire['net_worth'])}, target FIRE {format_idr(fire['fire_number'])}. "
                f"Gap saat ini {format_idr(fire['gap'])}."
            ),
            estimated_amount=fire["gap"],
            action_type="increase_contribution",
            metadata={"progress": str(fire["progress"])},
        )
    if fire["monthly_expense"] > 0:
        profile = fire["profile"]
        emergency_months = profile.emergency_fund_months if profile else Decimal("6")
        emergency_target = money(fire["monthly_expense"] * emergency_months)
        if fire["cash_balance"] < emergency_target:
            _insight(
                "emergency-fund-gap",
                type="emergency_fund_gap",
                severity=InvestmentInsight.Severity.WARNING,
                title="Dana darurat belum cukup",
                reason=(
                    f"Cash balance {format_idr(fire['cash_balance'])}, target dana darurat "
                    f"{emergency_months:g} bulan sekitar {format_idr(emergency_target)}."
                ),
                estimated_amount=emergency_target - fire["cash_balance"],
                action_type="build_emergency_fund",
            )
    for row in portfolio["positions"]:
        if total_value > 0 and row["market_value_idr"] / total_value >= Decimal("0.40"):
            _insight(
                f"concentration-{row['instrument'].id}",
                type="concentration_risk",
                severity=InvestmentInsight.Severity.WARNING,
                title=f"Konsentrasi tinggi di {row['instrument'].symbol}",
                reason=f"Holding ini sekitar {row['market_value_idr'] / total_value * 100:.1f}% dari portfolio.",
                estimated_amount=row["market_value_idr"],
                action_type="review_allocation",
                related_model="Instrument",
                related_object_id=row["instrument"].id,
            )
        if not row["price_snapshot"]:
            _insight(
                f"missing-price-{row['instrument'].id}",
                type="missing_price",
                severity=InvestmentInsight.Severity.INFO,
                title=f"Tambahkan harga untuk {row['instrument'].symbol}",
                reason="Market value dan gain/loss lebih akurat setelah ada price snapshot manual/API.",
                estimated_amount=ZERO,
                action_type="add_price",
                related_model="Instrument",
                related_object_id=row["instrument"].id,
            )
        elif row["price_is_stale"]:
            _insight(
                f"stale-price-{row['instrument'].id}",
                type="stale_price",
                severity=InvestmentInsight.Severity.INFO,
                title=f"Harga {row['instrument'].symbol} memakai cache lama",
                reason="Refresh harga atau input manual price terbaru untuk audit portfolio.",
                estimated_amount=ZERO,
                action_type="refresh_price",
                related_model="Instrument",
                related_object_id=row["instrument"].id,
            )
    targets = {target.asset_class: target.target_percent for target in AllocationTarget.objects.all()}
    for allocation in portfolio["allocation"]:
        target = targets.get(allocation["asset_class"])
        if target is not None and abs(allocation["percent"] - target) >= Decimal("10"):
            _insight(
                f"allocation-drift-{allocation['asset_class']}",
                type="allocation_drift",
                severity=InvestmentInsight.Severity.INFO,
                title=f"Allocation drift: {allocation['label']}",
                reason=f"Actual {allocation['percent']:.1f}%, target {target:.1f}%. Review sebelum tambah posisi baru.",
                estimated_amount=allocation["amount"],
                action_type="rebalance_review",
            )
    return list(InvestmentInsight.objects.all())


def manual_price(instrument: Instrument, price, provider: str = "Manual") -> PriceSnapshot:
    return PriceSnapshot.objects.create(
        instrument=instrument,
        price=quant_price(price),
        currency=instrument.currency,
        provider=provider or "Manual",
    )


def refresh_price(instrument: Instrument, provider: str = "auto") -> PriceResult:
    from .market_data import fetch_market_price

    try:
        payload = fetch_market_price(instrument, provider=provider)
        snapshot = PriceSnapshot.objects.create(
            instrument=instrument,
            price=payload["price"],
            currency=payload["currency"],
            provider=payload["provider"],
            is_stale=False,
            raw_response=payload.get("raw", {}),
        )
        return PriceResult(snapshot=snapshot, is_stale=False)
    except MarketDataUnavailable:
        snapshot = latest_price(instrument)
        if snapshot:
            snapshot.is_stale = True
            snapshot.save(update_fields=["is_stale"])
            return PriceResult(snapshot=snapshot, is_stale=True)
        raise


def refresh_fx_for_currency(currency: str) -> None:
    currency = (currency or "IDR").upper()
    if currency != "IDR":
        get_exchange_rate(currency, "IDR")
