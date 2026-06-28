import csv
import json
import shutil
from datetime import date, timedelta
from decimal import Decimal
from pathlib import Path

from django.conf import settings
from django.contrib import messages
from django.db.models import ProtectedError
from django.http import FileResponse, HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone

from .forms import (
    AccountForm,
    AllocationTargetForm,
    BudgetForm,
    CategoryForm,
    CurrencyConversionForm,
    DebtForm,
    DebtRepaymentForm,
    FinancialFreedomProfileForm,
    InstrumentForm,
    InvestmentAccountForm,
    InvestmentTransactionForm,
    PriceSnapshotForm,
    RecurringRuleForm,
    SavingsGoalForm,
    TransactionForm,
    TransferForm,
)
from .exchange_rates import ExchangeRateUnavailable, convert_to_idr
from .formatting import format_idr
from .models import (
    Account,
    AllocationTarget,
    Budget,
    Category,
    CurrencyConversionCheck,
    Debt,
    FinancialFreedomProfile,
    Instrument,
    InvestmentAccount,
    InvestmentInsight,
    InvestmentTransaction,
    Recommendation,
    PriceSnapshot,
    RecurringRule,
    SavingsGoal,
    Transaction,
    Transfer,
)
from .investments import (
    MarketDataUnavailable,
    financial_freedom_summary,
    generate_investment_insights,
    portfolio_summary,
    refresh_price,
)
from .recommendations import generate_recommendations
from .services import (
    account_balances,
    balance_history,
    budget_progress,
    category_spending,
    create_transaction,
    create_transfer,
    daily_spending,
    first_day,
    income_expense_by_month,
    monthly_summary,
    next_month_start,
    repay_debt,
    search_transactions,
)


def decimal_json(value):
    if isinstance(value, Decimal):
        return float(value)
    if isinstance(value, (date,)):
        return value.isoformat()
    raise TypeError(f"Cannot serialize {type(value)!r}")


def dashboard(request):
    month = first_day()
    recommendations = generate_recommendations(month)
    summary = monthly_summary(month)
    balances = account_balances()
    spending = category_spending(month)
    charts = {
        "incomeExpense": income_expense_by_month(6),
        "categorySpending": spending[:8],
        "dailySpending": daily_spending(month),
        "balanceHistory": balance_history(30),
        "savingRate": income_expense_by_month(6),
    }
    context = {
        "summary": summary,
        "balances": balances,
        "total_balance": sum((item["balance"] for item in balances), Decimal("0.00")),
        "spending": spending[:6],
        "budget_rows": budget_progress(month),
        "recommendations": [rec for rec in recommendations if rec.status == Recommendation.Status.ACTIVE][:8],
        "recent_transactions": Transaction.objects.select_related("account", "category")
        .exclude(status=Transaction.Status.DELETED)
        .order_by("-date", "-created_at")[:10],
        "charts_json": json.dumps(charts, default=decimal_json),
    }
    return render(request, "finance/dashboard.html", context)


def _decimal_text(value, places=4):
    value = Decimal(value or 0)
    text = f"{value:.{places}f}"
    return text.rstrip("0").rstrip(".") or "0"


def _generic_manage(request, *, model, form_class, title, rows_builder, list_url, queryset=None, form_initial=None):
    queryset = queryset if queryset is not None else model.objects.all()
    edit_id = request.GET.get("edit")
    instance = get_object_or_404(model, id=edit_id) if edit_id else None
    if request.method == "POST":
        delete_id = request.POST.get("delete_id")
        if delete_id:
            target = get_object_or_404(model, id=delete_id)
            try:
                target.delete()
                messages.success(request, "Data deleted.")
            except ProtectedError:
                messages.error(request, "Data masih dipakai transaksi lain, tidak bisa dihapus.")
            return redirect(list_url)
        form = form_class(request.POST, instance=instance)
        if form.is_valid():
            form.save()
            messages.success(request, "Data saved.")
            return redirect(list_url)
    else:
        form = form_class(instance=instance, initial=None if instance else form_initial)
    return render(
        request,
        "finance/manage.html",
        {
            "title": title,
            "form": form,
            "rows": rows_builder(queryset),
            "list_url": list_url,
            "editing": instance,
        },
    )


def accounts(request):
    return _generic_manage(
        request,
        model=Account,
        form_class=AccountForm,
        title="Accounts",
        list_url="finance:accounts",
        rows_builder=lambda qs: [
            {"object": obj, "cells": [obj.name, obj.get_type_display(), obj.opening_balance, "Active" if obj.is_active else "Inactive"]}
            for obj in qs
        ],
    )


def categories(request):
    return _generic_manage(
        request,
        model=Category,
        form_class=CategoryForm,
        title="Categories",
        list_url="finance:categories",
        rows_builder=lambda qs: [
            {"object": obj, "cells": [obj.name, obj.get_type_display(), "Fixed" if obj.is_fixed else "Variable", "Discretionary" if obj.is_discretionary else "Core"]}
            for obj in qs
        ],
    )


def transactions(request):
    edit_id = request.GET.get("edit")
    instance = get_object_or_404(Transaction, id=edit_id) if edit_id else None
    if request.method == "POST":
        delete_id = request.POST.get("delete_id")
        if delete_id:
            tx = get_object_or_404(Transaction, id=delete_id)
            tx.status = Transaction.Status.DELETED
            tx.save(update_fields=["status"])
            messages.success(request, "Transaction deleted from reports.")
            return redirect("finance:transactions")
        form = TransactionForm(request.POST, instance=instance)
        if form.is_valid():
            form.save()
            messages.success(request, "Transaction saved.")
            return redirect("finance:transactions")
    else:
        form = TransactionForm(instance=instance)
    query = request.GET.get("q", "")
    txs = search_transactions(query)[:200]
    rows = [
        {
            "object": tx,
            "cells": [
                tx.date,
                tx.get_kind_display(),
                tx.account.name,
                tx.category.name if tx.category else "Uncategorized",
                tx.amount,
                tx.note,
            ],
        }
        for tx in txs
    ]
    return render(
        request,
        "finance/manage.html",
        {
            "title": "Transactions",
            "form": form,
            "rows": rows,
            "list_url": "finance:transactions",
            "editing": instance,
            "query": query,
            "show_search": True,
        },
    )


def transfers(request):
    queryset = Transfer.objects.exclude(status=Transfer.Status.DELETED)
    return _generic_manage(
        request,
        model=Transfer,
        form_class=TransferForm,
        title="Transfers",
        list_url="finance:transfers",
        queryset=queryset,
        rows_builder=lambda qs: [
            {"object": obj, "cells": [obj.date, obj.from_account.name, obj.to_account.name, obj.amount, obj.fee_amount, obj.note]}
            for obj in qs[:200]
        ],
    )


def investment_dashboard(request):
    portfolio = portfolio_summary()
    fire = financial_freedom_summary()
    insights = generate_investment_insights()
    charts = {
        "allocation": [
            {"label": item["label"], "amount": item["amount"]}
            for item in portfolio["allocation"]
        ],
        "holdings": [
            {"label": row["instrument"].symbol, "amount": row["market_value_idr"]}
            for row in portfolio["positions"][:8]
        ],
    }
    return render(
        request,
        "finance/investments.html",
        {
            "portfolio": portfolio,
            "fire": fire,
            "insights": [insight for insight in insights if insight.status == InvestmentInsight.Status.ACTIVE],
            "charts_json": json.dumps(charts, default=decimal_json),
        },
    )


def investment_instruments(request):
    return _generic_manage(
        request,
        model=Instrument,
        form_class=InstrumentForm,
        title="Investment Instruments",
        list_url="finance:investment_instruments",
        rows_builder=lambda qs: [
            {
                "object": obj,
                "cells": [
                    obj.symbol,
                    obj.provider_symbol or "-",
                    obj.get_market_display(),
                    obj.currency,
                    obj.get_asset_class_display(),
                    _decimal_text(obj.lot_size),
                    "Watchlist" if obj.is_watchlisted else "-",
                ],
                "actions": [
                    {"label": "Price", "href": reverse("finance:investment_price", args=[obj.id])},
                ],
            }
            for obj in qs
        ],
    )


def investment_accounts(request):
    return _generic_manage(
        request,
        model=InvestmentAccount,
        form_class=InvestmentAccountForm,
        title="Investment Accounts",
        list_url="finance:investment_accounts",
        rows_builder=lambda qs: [
            {
                "object": obj,
                "cells": [
                    obj.name,
                    obj.platform or "-",
                    obj.currency,
                    obj.linked_cash_account.name if obj.linked_cash_account else "-",
                    "Active" if obj.is_active else "Inactive",
                ],
            }
            for obj in qs
        ],
    )


def investment_transactions(request):
    queryset = InvestmentTransaction.objects.exclude(status=InvestmentTransaction.Status.DELETED).select_related(
        "account", "instrument"
    )
    return _generic_manage(
        request,
        model=InvestmentTransaction,
        form_class=InvestmentTransactionForm,
        title="Investment Transactions",
        list_url="finance:investment_transactions",
        queryset=queryset,
        rows_builder=lambda qs: [
            {
                "object": obj,
                "cells": [
                    obj.date,
                    obj.get_kind_display(),
                    obj.instrument.symbol,
                    obj.account.name,
                    _decimal_text(obj.quantity),
                    _decimal_text(obj.price),
                    _decimal_text(obj.cash_amount, 2),
                    obj.currency,
                ],
            }
            for obj in qs[:200]
        ],
    )


def investment_price(request, pk):
    instrument = get_object_or_404(Instrument, pk=pk)
    latest = instrument.price_snapshots.first()
    if request.method == "POST" and request.POST.get("refresh_provider"):
        provider = request.POST.get("refresh_provider") or settings.MARKET_DATA_PROVIDER
        try:
            result = refresh_price(instrument, provider=provider)
            if result.is_stale:
                messages.warning(request, "Provider gagal. Menggunakan cached price terakhir dan menandainya stale.")
            else:
                messages.success(request, "Harga berhasil direfresh.")
        except MarketDataUnavailable as exc:
            messages.error(request, str(exc))
        return redirect("finance:investment_price", pk=instrument.id)
    form = PriceSnapshotForm(request.POST or None, instrument=instrument)
    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, "Manual price saved.")
        return redirect("finance:investment_price", pk=instrument.id)
    history = instrument.price_snapshots.all()[:20]
    return render(
        request,
        "finance/investment_price.html",
        {
            "instrument": instrument,
            "form": form,
            "latest": latest,
            "history": history,
        },
    )


def financial_freedom(request):
    profile = FinancialFreedomProfile.objects.order_by("name").first()
    form = FinancialFreedomProfileForm(request.POST or None, instance=profile)
    if request.method == "POST" and form.is_valid():
        saved = form.save(commit=False)
        saved.name = profile.name if profile else "Default"
        saved.save()
        messages.success(request, "Financial freedom profile saved.")
        return redirect("finance:financial_freedom")
    return render(
        request,
        "finance/financial_freedom.html",
        {
            "form": form,
            "summary": financial_freedom_summary(profile),
            "targets": AllocationTarget.objects.all(),
            "target_form": AllocationTargetForm(),
        },
    )


def allocation_targets(request):
    if request.method != "POST":
        return redirect("finance:financial_freedom")
    form = AllocationTargetForm(request.POST)
    if form.is_valid():
        AllocationTarget.objects.update_or_create(
            asset_class=form.cleaned_data["asset_class"],
            defaults={"target_percent": form.cleaned_data["target_percent"]},
        )
        messages.success(request, "Allocation target saved.")
    else:
        messages.error(request, "Allocation target tidak valid.")
    return redirect("finance:financial_freedom")


def watchlist(request):
    initial = {"is_watchlisted": True}
    queryset = Instrument.objects.filter(is_watchlisted=True)
    return _generic_manage(
        request,
        model=Instrument,
        form_class=InstrumentForm,
        title="Watchlist",
        list_url="finance:watchlist",
        queryset=queryset,
        form_initial=initial,
        rows_builder=lambda qs: [
            {
                "object": obj,
                "cells": [
                    obj.symbol,
                    obj.provider_symbol or "-",
                    obj.get_market_display(),
                    obj.currency,
                    obj.get_asset_class_display(),
                    obj.watch_note or "-",
                ],
                "actions": [
                    {"label": "Price", "href": reverse("finance:investment_price", args=[obj.id])},
                ],
            }
            for obj in qs
        ],
    )


def budgets(request):
    initial = {}
    category_id = request.GET.get("category")
    amount = request.GET.get("amount")
    if category_id and amount:
        initial = {"month": first_day(), "category": category_id, "amount": amount}
    return _generic_manage(
        request,
        model=Budget,
        form_class=BudgetForm,
        title="Budgets",
        list_url="finance:budgets",
        form_initial=initial or None,
        rows_builder=lambda qs: [
            {"object": obj, "cells": [obj.month.strftime("%Y-%m"), obj.category.name, obj.amount]}
            for obj in qs
        ],
    )


def debts(request):
    return _generic_manage(
        request,
        model=Debt,
        form_class=DebtForm,
        title="Debts",
        list_url="finance:debts",
        rows_builder=lambda qs: [
            {
                "object": obj,
                "cells": [
                    obj.get_direction_display(),
                    obj.counterparty,
                    obj.principal_amount,
                    obj.current_balance,
                    obj.due_date or "-",
                    obj.get_status_display(),
                ],
                "actions": [
                    {
                        "label": "Record Payment",
                        "href": reverse("finance:debt_repay", args=[obj.id]),
                    }
                ]
                if obj.status == Debt.Status.OPEN and obj.current_balance > 0
                else [],
            }
            for obj in qs
        ],
    )


def debt_repay(request, pk):
    debt = get_object_or_404(Debt, pk=pk)
    if debt.status == Debt.Status.CLOSED or debt.current_balance <= 0:
        messages.info(request, "Debt ini sudah closed atau balance-nya sudah Rp0.")
        return redirect("finance:debts")
    if request.method == "POST":
        form = DebtRepaymentForm(request.POST, debt=debt)
        if form.is_valid():
            repay_debt(
                debt=debt,
                account=form.cleaned_data["account"],
                amount=form.cleaned_data["amount"],
                tx_date=form.cleaned_data["date"],
                note=form.cleaned_data["note"],
            )
            debt.refresh_from_db()
            messages.success(request, f"Repayment recorded. Remaining balance {format_idr(debt.current_balance)}.")
            return redirect("finance:debts")
    else:
        form = DebtRepaymentForm(debt=debt, initial={"date": timezone.localdate(), "amount": debt.current_balance})
    return render(request, "finance/debt_repay.html", {"debt": debt, "form": form})


def currency(request):
    result = None
    form = CurrencyConversionForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        try:
            result = convert_to_idr(form.cleaned_data["currency"], form.cleaned_data["amount"])
            if result.is_stale:
                messages.warning(request, "API kurs sedang tidak bisa diakses. Hasil memakai cache terakhir.")
            else:
                messages.success(request, "Kurs check tersimpan untuk audit history.")
        except ExchangeRateUnavailable as exc:
            messages.error(request, str(exc))
    history = CurrencyConversionCheck.objects.select_related("snapshot")[:30]
    return render(
        request,
        "finance/currency.html",
        {
            "form": form,
            "result": result,
            "history": history,
        },
    )


def recurring(request):
    return _generic_manage(
        request,
        model=RecurringRule,
        form_class=RecurringRuleForm,
        title="Recurring",
        list_url="finance:recurring",
        rows_builder=lambda qs: [
            {"object": obj, "cells": [obj.name, obj.get_kind_display(), obj.account.name, obj.amount, obj.next_due, "Active" if obj.is_active else "Inactive"]}
            for obj in qs
        ],
    )


def savings_goals(request):
    return _generic_manage(
        request,
        model=SavingsGoal,
        form_class=SavingsGoalForm,
        title="Savings Goals",
        list_url="finance:savings",
        rows_builder=lambda qs: [
            {"object": obj, "cells": [obj.name, obj.current_amount, obj.target_amount, obj.target_date or "-", "Active" if obj.is_active else "Inactive"]}
            for obj in qs
        ],
    )


def recommendation_action(request, pk):
    if request.method != "POST":
        return redirect("finance:dashboard")
    rec = get_object_or_404(Recommendation, pk=pk)
    action = request.POST.get("action")
    if action in {Recommendation.Status.IGNORED, Recommendation.Status.DONE, Recommendation.Status.ACTIVE}:
        rec.status = action
        rec.save(update_fields=["status", "updated_at"])
        messages.success(request, "Recommendation updated.")
    elif action == "budget" and rec.related_model == "Category" and rec.estimated_saving > 0:
        current_month = first_day()
        category = get_object_or_404(Category, pk=rec.related_object_id)
        current_spend = Decimal(str(rec.metadata.get("current_spend", "0")))
        target = current_spend - rec.estimated_saving
        Budget.objects.update_or_create(month=current_month, category=category, defaults={"amount": target})
        rec.status = Recommendation.Status.DONE
        rec.save(update_fields=["status", "updated_at"])
        messages.success(request, "Budget target created from recommendation.")
    elif action == "mark_recurring_paid" and rec.related_model == "RecurringRule":
        rule = get_object_or_404(RecurringRule, pk=rec.related_object_id)
        if rule.kind == RecurringRule.Kind.TRANSFER and rule.to_account:
            create_transfer(from_account=rule.account, to_account=rule.to_account, amount=rule.amount, note=rule.note or rule.name, source=Transaction.Source.SYSTEM)
        else:
            create_transaction(
                kind=Transaction.Kind.INCOME if rule.kind == RecurringRule.Kind.INCOME else Transaction.Kind.EXPENSE,
                amount=rule.amount,
                account=rule.account,
                category=rule.category,
                note=rule.note or rule.name,
                source=Transaction.Source.SYSTEM,
            )
        if rule.interval == RecurringRule.Interval.DAILY:
            rule.next_due = rule.next_due + timedelta(days=1)
        elif rule.interval == RecurringRule.Interval.WEEKLY:
            rule.next_due = rule.next_due + timedelta(days=7)
        else:
            from .services import add_month

            rule.next_due = add_month(rule.next_due)
        rule.save(update_fields=["next_due"])
        rec.status = Recommendation.Status.DONE
        rec.save(update_fields=["status", "updated_at"])
        messages.success(request, "Recurring item recorded.")
    return redirect("finance:dashboard")


def export_csv(request):
    response = HttpResponse(content_type="text/csv")
    response["Content-Disposition"] = 'attachment; filename="money-manager-transactions.csv"'
    writer = csv.writer(response)
    writer.writerow(["date", "kind", "account", "category", "amount", "merchant", "note", "source"])
    for tx in Transaction.objects.select_related("account", "category").exclude(status=Transaction.Status.DELETED):
        writer.writerow([tx.date, tx.kind, tx.account.name, tx.category.name if tx.category else "", tx.amount, tx.merchant, tx.note, tx.source])
    return response


def backup_database(request):
    db_path = Path(settings.DATABASES["default"]["NAME"])
    backup_dir = settings.BASE_DIR / "runtime" / "backups"
    backup_dir.mkdir(parents=True, exist_ok=True)
    target = backup_dir / f"money-manager-{timezone.now():%Y%m%d-%H%M%S}.sqlite3"
    shutil.copy2(db_path, target)
    return FileResponse(open(target, "rb"), as_attachment=True, filename=target.name)
