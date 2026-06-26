from __future__ import annotations

from calendar import monthrange
from dataclasses import asdict
from datetime import date, timedelta
from decimal import Decimal

from django.db import transaction as db_transaction
from django.db.models import Q
from django.utils import timezone

from .models import Account, Budget, Category, Debt, RecurringRule, Transaction, Transfer
from .parser import ParsedEntry
from .formatting import format_idr


ZERO = Decimal("0.00")


def money(value) -> Decimal:
    return Decimal(value or 0).quantize(Decimal("0.01"))


def first_day(value: date | None = None) -> date:
    value = value or timezone.localdate()
    return date(value.year, value.month, 1)


def add_month(value: date) -> date:
    year = value.year + (1 if value.month == 12 else 0)
    month = 1 if value.month == 12 else value.month + 1
    day = min(value.day, monthrange(year, month)[1])
    return date(year, month, day)


def next_month_start(value: date | None = None) -> date:
    start = first_day(value)
    return add_month(start)


def get_or_create_account(name: str | None) -> Account:
    normalized = (name or "Cash").strip().upper()
    account_type = Account.Type.CASH
    if normalized.lower() in {"bca", "bni", "bri", "mandiri", "cimb", "jago", "bank"}:
        account_type = Account.Type.BANK
    if normalized.lower() in {"ovo", "gopay", "dana", "linkaja", "shopeepay"}:
        account_type = Account.Type.E_WALLET
    return Account.objects.get_or_create(name=normalized, defaults={"type": account_type})[0]


def get_category(name: str | None, category_type: str) -> Category | None:
    if not name:
        return None
    category = Category.objects.filter(name__iexact=name, type=category_type).first()
    if category:
        return category
    keyword_match = Category.objects.filter(type=category_type, keywords__icontains=name).first()
    return keyword_match


def transaction_effect(tx: Transaction) -> Decimal:
    if tx.status != Transaction.Status.CONFIRMED:
        return ZERO
    if tx.kind == Transaction.Kind.INCOME:
        return money(tx.amount)
    if tx.kind == Transaction.Kind.EXPENSE:
        return -money(tx.amount)
    if tx.kind == Transaction.Kind.ADJUSTMENT:
        return money(tx.amount)
    if tx.kind == Transaction.Kind.REPAYMENT and tx.debt:
        if tx.debt.direction == Debt.Direction.RECEIVABLE:
            return money(tx.amount)
        return -money(tx.amount)
    if tx.kind == Transaction.Kind.REPAYMENT:
        return -money(tx.amount)
    return ZERO


def account_balances() -> list[dict]:
    accounts = list(Account.objects.all())
    balances = {account.id: money(account.opening_balance) for account in accounts}
    for tx in Transaction.objects.filter(status=Transaction.Status.CONFIRMED).select_related("debt"):
        balances[tx.account_id] = balances.get(tx.account_id, ZERO) + transaction_effect(tx)
    for transfer in Transfer.objects.filter(status=Transfer.Status.CONFIRMED):
        balances[transfer.from_account_id] = balances.get(transfer.from_account_id, ZERO) - money(transfer.amount) - money(transfer.fee_amount)
        balances[transfer.to_account_id] = balances.get(transfer.to_account_id, ZERO) + money(transfer.amount)
    return [
        {
            "account": account,
            "balance": balances.get(account.id, ZERO),
        }
        for account in accounts
    ]


def total_balance() -> Decimal:
    return sum((item["balance"] for item in account_balances()), ZERO)


def monthly_transactions(month: date | None = None):
    start = first_day(month)
    end = next_month_start(start)
    return Transaction.objects.filter(
        date__gte=start,
        date__lt=end,
        status=Transaction.Status.CONFIRMED,
    ).select_related("category", "debt", "account")


def monthly_summary(month: date | None = None) -> dict:
    income = ZERO
    expense = ZERO
    for tx in monthly_transactions(month):
        amount = money(tx.amount)
        if tx.kind == Transaction.Kind.INCOME:
            income += amount
        elif tx.kind == Transaction.Kind.EXPENSE:
            expense += amount
        elif tx.kind == Transaction.Kind.REPAYMENT and tx.debt:
            if tx.debt.direction == Debt.Direction.RECEIVABLE:
                income += amount
            else:
                expense += amount
    for transfer in Transfer.objects.filter(
        date__gte=first_day(month),
        date__lt=next_month_start(month),
        status=Transfer.Status.CONFIRMED,
    ):
        expense += money(transfer.fee_amount)
    net = income - expense
    saving_rate = (net / income) if income > 0 else ZERO
    return {"income": income, "expense": expense, "net": net, "saving_rate": saving_rate}


def category_spending(month: date | None = None) -> list[dict]:
    totals: dict[str, dict] = {}
    for tx in monthly_transactions(month).filter(kind__in=[Transaction.Kind.EXPENSE, Transaction.Kind.REPAYMENT]):
        if tx.kind == Transaction.Kind.REPAYMENT and tx.debt and tx.debt.direction == Debt.Direction.RECEIVABLE:
            continue
        category_name = tx.category.name if tx.category else "Uncategorized"
        category_id = tx.category_id or 0
        if category_name not in totals:
            totals[category_name] = {"category_id": category_id, "name": category_name, "amount": ZERO}
        totals[category_name]["amount"] += money(tx.amount)
    return sorted(totals.values(), key=lambda item: item["amount"], reverse=True)


def daily_spending(month: date | None = None) -> list[dict]:
    start = first_day(month)
    end = next_month_start(start)
    day_count = (end - start).days
    totals = {start + timedelta(days=idx): ZERO for idx in range(day_count)}
    for tx in monthly_transactions(month).filter(kind=Transaction.Kind.EXPENSE):
        totals[tx.date] = totals.get(tx.date, ZERO) + money(tx.amount)
    return [{"label": day.strftime("%d"), "amount": amount} for day, amount in totals.items()]


def income_expense_by_month(months: int = 6) -> list[dict]:
    current = first_day()
    starts = []
    for _ in range(months):
        starts.append(current)
        previous_month = current.month - 1 or 12
        previous_year = current.year - 1 if current.month == 1 else current.year
        current = date(previous_year, previous_month, 1)
    rows = []
    for start in reversed(starts):
        summary = monthly_summary(start)
        rows.append(
            {
                "label": start.strftime("%b %Y"),
                "income": summary["income"],
                "expense": summary["expense"],
                "saving_rate": summary["saving_rate"],
            }
        )
    return rows


def budget_progress(month: date | None = None) -> list[dict]:
    start = first_day(month)
    spending = {item["category_id"]: item["amount"] for item in category_spending(start)}
    rows = []
    for budget in Budget.objects.filter(month=start).select_related("category"):
        spent = spending.get(budget.category_id, ZERO)
        percent = (spent / budget.amount * Decimal("100")) if budget.amount > 0 else ZERO
        rows.append(
            {
                "budget": budget,
                "spent": spent,
                "remaining": money(budget.amount) - spent,
                "percent": percent,
            }
        )
    return sorted(rows, key=lambda item: item["percent"], reverse=True)


def balance_history(days: int = 30) -> list[dict]:
    today = timezone.localdate()
    start = today - timedelta(days=days - 1)
    current_total = sum((money(account.opening_balance) for account in Account.objects.all()), ZERO)
    for tx in Transaction.objects.filter(date__lt=start, status=Transaction.Status.CONFIRMED).select_related("debt"):
        current_total += transaction_effect(tx)
    for transfer in Transfer.objects.filter(date__lt=start, status=Transfer.Status.CONFIRMED):
        current_total -= money(transfer.fee_amount)
    rows = []
    for idx in range(days):
        day = start + timedelta(days=idx)
        for tx in Transaction.objects.filter(date=day, status=Transaction.Status.CONFIRMED).select_related("debt"):
            current_total += transaction_effect(tx)
        for transfer in Transfer.objects.filter(date=day, status=Transfer.Status.CONFIRMED):
            current_total -= money(transfer.fee_amount)
        rows.append({"label": day.strftime("%d %b"), "balance": current_total})
    return rows


@db_transaction.atomic
def create_transaction(
    *,
    kind: str,
    amount,
    account: Account,
    category: Category | None = None,
    note: str = "",
    merchant: str = "",
    tx_date: date | None = None,
    source: str = Transaction.Source.WEB,
    source_user_id: str = "",
    debt: Debt | None = None,
) -> Transaction:
    return Transaction.objects.create(
        kind=kind,
        amount=money(amount),
        account=account,
        category=category,
        note=note,
        merchant=merchant,
        date=tx_date or timezone.localdate(),
        source=source,
        source_user_id=source_user_id,
        debt=debt,
    )


@db_transaction.atomic
def create_transfer(
    *,
    from_account: Account,
    to_account: Account,
    amount,
    fee_amount=0,
    note: str = "",
    tx_date: date | None = None,
    source: str = Transaction.Source.WEB,
    source_user_id: str = "",
) -> Transfer:
    return Transfer.objects.create(
        from_account=from_account,
        to_account=to_account,
        amount=money(amount),
        fee_amount=money(fee_amount),
        note=note,
        date=tx_date or timezone.localdate(),
        source=source,
        source_user_id=source_user_id,
    )


@db_transaction.atomic
def create_debt(*, direction: str, counterparty: str, amount, note: str = "", due_date: date | None = None) -> Debt:
    amount = money(amount)
    return Debt.objects.create(
        direction=direction,
        counterparty=counterparty.strip().title() or "Unknown",
        principal_amount=amount,
        current_balance=amount,
        due_date=due_date,
        note=note,
    )


@db_transaction.atomic
def repay_debt(
    *,
    debt: Debt,
    account: Account,
    amount,
    tx_date: date | None = None,
    note: str = "",
    source=Transaction.Source.WEB,
    source_user_id="",
) -> Transaction:
    amount = min(money(amount), money(debt.current_balance))
    tx = create_transaction(
        kind=Transaction.Kind.REPAYMENT,
        amount=amount,
        account=account,
        note=note or f"Repayment {debt.counterparty}",
        tx_date=tx_date,
        source=source,
        source_user_id=source_user_id,
        debt=debt,
    )
    debt.current_balance = money(debt.current_balance) - amount
    if debt.current_balance <= 0:
        debt.current_balance = ZERO
        debt.status = Debt.Status.CLOSED
    debt.save(update_fields=["current_balance", "status", "updated_at"])
    return tx


def record_parsed_entry(parsed: ParsedEntry, *, source_user_id: str = ""):
    if not parsed.amount:
        raise ValueError("Amount is required.")
    if parsed.action == "transfer":
        if not parsed.account_hint or not parsed.to_account_hint:
            raise ValueError("Transfer needs source and destination accounts.")
        return create_transfer(
            from_account=get_or_create_account(parsed.account_hint),
            to_account=get_or_create_account(parsed.to_account_hint),
            amount=parsed.amount,
            note=parsed.note,
            source=Transaction.Source.TELEGRAM,
            source_user_id=source_user_id,
        )
    if parsed.action == "debt_payable":
        return create_debt(
            direction=Debt.Direction.PAYABLE,
            counterparty=parsed.counterparty,
            amount=parsed.amount,
            note=parsed.note,
        )
    if parsed.action == "debt_receivable":
        return create_debt(
            direction=Debt.Direction.RECEIVABLE,
            counterparty=parsed.counterparty,
            amount=parsed.amount,
            note=parsed.note,
        )
    kind = Transaction.Kind.INCOME if parsed.action == "income" else Transaction.Kind.EXPENSE
    category_type = Category.Type.INCOME if kind == Transaction.Kind.INCOME else Category.Type.EXPENSE
    return create_transaction(
        kind=kind,
        amount=parsed.amount,
        account=get_or_create_account(parsed.account_hint),
        category=get_category(parsed.category_hint, category_type),
        note=parsed.note,
        source=Transaction.Source.TELEGRAM,
        source_user_id=source_user_id,
    )


def parsed_entry_summary(parsed: ParsedEntry) -> str:
    data = asdict(parsed)
    amount = data.pop("amount")
    amount_label = format_idr(amount) if amount else "Missing"
    lines = [f"Action: {parsed.action}", f"Amount: {amount_label}"]
    if parsed.account_hint:
        lines.append(f"Account: {parsed.account_hint.upper()}")
    if parsed.to_account_hint:
        lines.append(f"To: {parsed.to_account_hint.upper()}")
    if parsed.category_hint:
        lines.append(f"Category: {parsed.category_hint}")
    if parsed.counterparty:
        lines.append(f"Counterparty: {parsed.counterparty.title()}")
    lines.append(f"Note: {parsed.note}")
    return "\n".join(lines)


def latest_telegram_item(user_id: str):
    tx = Transaction.objects.filter(
        source=Transaction.Source.TELEGRAM,
        source_user_id=user_id,
        status=Transaction.Status.CONFIRMED,
    ).order_by("-created_at").first()
    transfer = Transfer.objects.filter(
        source=Transaction.Source.TELEGRAM,
        source_user_id=user_id,
        status=Transfer.Status.CONFIRMED,
    ).order_by("-created_at").first()
    if transfer and (not tx or transfer.created_at > tx.created_at):
        return transfer
    return tx


def soft_delete_item(item) -> None:
    if not item:
        return
    item.status = item.Status.DELETED
    item.save(update_fields=["status"])


def search_transactions(query: str):
    qs = Transaction.objects.select_related("account", "category").exclude(status=Transaction.Status.DELETED)
    if query:
        qs = qs.filter(Q(note__icontains=query) | Q(merchant__icontains=query) | Q(account__name__icontains=query) | Q(category__name__icontains=query))
    return qs
