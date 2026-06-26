from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal

from django.conf import settings
from django.utils import timezone

from .formatting import format_idr
from .models import Budget, Category, Debt, Recommendation, RecurringRule, Transaction
from .services import (
    ZERO,
    budget_progress,
    category_spending,
    first_day,
    money,
    monthly_summary,
    monthly_transactions,
    next_month_start,
)


def _fingerprint(month: date, rec_type: str, key: str) -> str:
    return f"{month:%Y-%m}:{rec_type}:{key}"[:160]


def _create_or_update(month: date, **fields) -> None:
    fingerprint = _fingerprint(month, fields["type"], fields.pop("key"))
    existing = Recommendation.objects.filter(fingerprint=fingerprint).first()
    if existing and existing.status in {Recommendation.Status.IGNORED, Recommendation.Status.DONE}:
        return
    defaults = {
        "generated_for_month": month,
        "fingerprint": fingerprint,
        "status": Recommendation.Status.ACTIVE,
        **fields,
    }
    if existing:
        for key, value in defaults.items():
            setattr(existing, key, value)
        existing.save()
    else:
        Recommendation.objects.create(**defaults)


def _prior_category_average(category_id: int, month: date) -> Decimal:
    total = ZERO
    months = 0
    cursor = first_day(month)
    for _ in range(3):
        previous_month = cursor.month - 1 or 12
        previous_year = cursor.year - 1 if cursor.month == 1 else cursor.year
        cursor = date(previous_year, previous_month, 1)
        months += 1
        for item in category_spending(cursor):
            if item["category_id"] == category_id:
                total += money(item["amount"])
    return total / Decimal(months) if months else ZERO


def generate_recommendations(month: date | None = None) -> list[Recommendation]:
    month = first_day(month)
    Recommendation.objects.filter(generated_for_month=month, status=Recommendation.Status.ACTIVE).delete()

    summary = monthly_summary(month)
    target_rate = Decimal(str(settings.SAVING_RATE_TARGET))
    if summary["income"] > 0 and summary["saving_rate"] < target_rate:
        required = (summary["income"] * target_rate) - summary["net"]
        if required > 0:
            _create_or_update(
                month,
                key="saving-rate",
                type="saving_rate_gap",
                severity=Recommendation.Severity.CRITICAL,
                title="Saving rate di bawah target",
                reason=(
                    f"Saving rate bulan ini {summary['saving_rate'] * 100:.1f}%, "
                    f"target {target_rate * 100:.1f}%. Butuh kurangi expense atau tambah income sekitar {format_idr(required)}."
                ),
                estimated_saving=money(required),
                action_type="review_spending",
                metadata={"target_rate": str(target_rate)},
            )

    for row in budget_progress(month):
        percent = row["percent"]
        if percent >= 90:
            severity = Recommendation.Severity.CRITICAL if percent >= 100 else Recommendation.Severity.WARNING
            _create_or_update(
                month,
                key=f"budget-{row['budget'].id}",
                type="budget_variance",
                severity=severity,
                title=f"Budget {row['budget'].category.name} hampir/melewati batas",
                reason=(
                    f"Terpakai {format_idr(row['spent'])} dari budget {format_idr(row['budget'].amount)} "
                    f"({percent:.1f}%)."
                ),
                estimated_saving=max(row["spent"] - row["budget"].amount, ZERO),
                action_type="adjust_budget",
                related_model="Budget",
                related_object_id=row["budget"].id,
            )

    for item in category_spending(month):
        category = Category.objects.filter(id=item["category_id"]).first()
        if not category:
            continue
        current = money(item["amount"])
        prior_avg = _prior_category_average(category.id, month)
        if prior_avg > 0 and current > prior_avg * Decimal("1.30") and current - prior_avg > Decimal("50000"):
            _create_or_update(
                month,
                key=f"spike-{category.id}",
                type="spending_spike",
                severity=Recommendation.Severity.WARNING,
                title=f"Kategori {category.name} naik tajam",
                reason=f"Bulan ini {format_idr(current)}, rata-rata 3 bulan sebelumnya {format_idr(prior_avg)}.",
                estimated_saving=money(current - prior_avg),
                action_type="view_category_transactions",
                related_model="Category",
                related_object_id=category.id,
            )
        if category.is_discretionary and current > 0:
            cut_20 = current * Decimal("0.20")
            _create_or_update(
                month,
                key=f"discretionary-{category.id}",
                type="saving_opportunity",
                severity=Recommendation.Severity.INFO,
                title=f"Kurangi {category.name} 20%",
                reason=f"Kalau {category.name} dikurangi 20% bulan depan, potensi saving sekitar {format_idr(cut_20)}.",
                estimated_saving=money(cut_20),
                action_type="create_or_reduce_budget",
                related_model="Category",
                related_object_id=category.id,
                metadata={"current_spend": str(current), "cut_percent": "20"},
            )

    uncategorized = [tx.id for tx in monthly_transactions(month).filter(category__isnull=True)]
    if len(uncategorized) >= 3:
        _create_or_update(
            month,
            key="uncategorized",
            type="uncategorized",
            severity=Recommendation.Severity.WARNING,
            title="Banyak transaksi belum dikategorikan",
            reason=f"Ada {len(uncategorized)} transaksi tanpa kategori. Audit kategori akan lebih akurat kalau dirapikan.",
            estimated_saving=ZERO,
            action_type="categorize_transactions",
            related_transaction_ids=uncategorized[:20],
        )

    duplicate_groups = {}
    for tx in monthly_transactions(month):
        key = (tx.date, tx.account_id, tx.amount, tx.note.strip().lower(), tx.merchant.strip().lower())
        duplicate_groups.setdefault(key, []).append(tx.id)
    for key, ids in duplicate_groups.items():
        if len(ids) > 1:
            _create_or_update(
                month,
                key=f"duplicate-{ids[0]}",
                type="duplicate_transaction",
                severity=Recommendation.Severity.WARNING,
                title="Kemungkinan transaksi duplikat",
                reason=f"Ada {len(ids)} transaksi dengan tanggal, akun, nominal, dan catatan yang sama.",
                estimated_saving=ZERO,
                action_type="review_duplicates",
                related_transaction_ids=ids,
            )

    subscription_rules = RecurringRule.objects.filter(is_active=True, kind=RecurringRule.Kind.EXPENSE)
    for rule in subscription_rules:
        if rule.next_due <= timezone.localdate() + timedelta(days=7):
            _create_or_update(
                month,
                key=f"recurring-{rule.id}",
                type="subscription_review",
                severity=Recommendation.Severity.INFO,
                title=f"Review recurring: {rule.name}",
                reason=f"Jatuh tempo {rule.next_due:%d %b %Y}, nominal {format_idr(rule.amount)}. Cancel kalau sudah tidak dipakai.",
                estimated_saving=money(rule.amount),
                action_type="mark_recurring_paid",
                related_model="RecurringRule",
                related_object_id=rule.id,
            )

    due_debts = Debt.objects.filter(status=Debt.Status.OPEN, current_balance__gt=0, due_date__lte=timezone.localdate() + timedelta(days=7))
    for debt in due_debts:
        title = "Utang perlu dibayar" if debt.direction == Debt.Direction.PAYABLE else "Piutang perlu ditagih"
        _create_or_update(
            month,
            key=f"debt-{debt.id}",
            type="debt_due",
            severity=Recommendation.Severity.CRITICAL if debt.due_date and debt.due_date < timezone.localdate() else Recommendation.Severity.WARNING,
            title=f"{title}: {debt.counterparty}",
            reason=f"Saldo {format_idr(debt.current_balance)}, jatuh tempo {debt.due_date:%d %b %Y}.",
            estimated_saving=ZERO,
            action_type="record_repayment",
            related_model="Debt",
            related_object_id=debt.id,
        )

    return list(Recommendation.objects.filter(generated_for_month=month).order_by("status", "-estimated_saving"))
