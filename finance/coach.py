from __future__ import annotations

import hashlib
import re
from collections import defaultdict
from datetime import date, timedelta
from decimal import Decimal, ROUND_CEILING

from django.db import transaction as db_transaction
from django.utils import timezone

from .formatting import format_idr
from .models import (
    Account,
    Budget,
    Category,
    Debt,
    FinancialGoal,
    MonthlyAudit,
    Recommendation,
    RecurringCandidate,
    RecurringRule,
    Transaction,
)
from .recommendations import generate_recommendations
from .services import (
    ZERO,
    account_balances,
    add_month,
    budget_progress,
    category_spending,
    first_day,
    money,
    monthly_summary,
    monthly_transactions,
)


LOW_BALANCE_THRESHOLD = Decimal("100000.00")


def _month_key(value: date) -> tuple[int, int]:
    return value.year, value.month


def _months_between(start: date, end: date) -> int:
    if end <= start:
        return 0
    months = (Decimal((end - start).days) / Decimal("30")).to_integral_value(rounding=ROUND_CEILING)
    return max(1, int(months))


def _decimal_text(value) -> str:
    return str(money(value))


def normalize_merchant(value: str) -> str:
    text = (value or "").strip().lower()
    text = re.sub(r"[^a-z0-9]+", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def transaction_label(tx: Transaction) -> str:
    if tx.merchant.strip():
        return normalize_merchant(tx.merchant)
    if tx.note.strip():
        return normalize_merchant(tx.note)[:80]
    if tx.category:
        return normalize_merchant(tx.category.name)
    return "uncategorized"


def _candidate_fingerprint(label: str, account_id: int | None, category_id: int | None, amount) -> str:
    raw = f"{label}|{account_id or 0}|{category_id or 0}|{money(amount)}"
    return hashlib.sha1(raw.encode("utf-8")).hexdigest()


def _candidate_cadence(dates: list[date]) -> str:
    if len(dates) < 2:
        return RecurringCandidate.Cadence.UNKNOWN
    gaps = [(dates[idx] - dates[idx - 1]).days for idx in range(1, len(dates))]
    avg_gap = sum(gaps) / len(gaps)
    if 20 <= avg_gap <= 45:
        return RecurringCandidate.Cadence.MONTHLY
    if 5 <= avg_gap <= 10:
        return RecurringCandidate.Cadence.WEEKLY
    return RecurringCandidate.Cadence.UNKNOWN


def detect_recurring_candidates(month: date | None = None, lookback_days: int = 140) -> list[RecurringCandidate]:
    today = timezone.localdate()
    end = first_day(month) + timedelta(days=45) if month else today + timedelta(days=1)
    start = end - timedelta(days=lookback_days)
    groups = defaultdict(list)
    txs = (
        Transaction.objects.filter(
            kind=Transaction.Kind.EXPENSE,
            status=Transaction.Status.CONFIRMED,
            date__gte=start,
            date__lt=end,
        )
        .select_related("account", "category")
        .order_by("date")
    )
    for tx in txs:
        label = transaction_label(tx)
        if not label or label == "uncategorized":
            continue
        key = (label, tx.account_id, tx.category_id, money(tx.amount))
        groups[key].append(tx)

    candidates = []
    for (label, account_id, category_id, amount), rows in groups.items():
        distinct_months = {_month_key(tx.date) for tx in rows}
        if len(rows) < 2 or len(distinct_months) < 2:
            continue
        dates = [tx.date for tx in rows]
        cadence = _candidate_cadence(dates)
        confidence = Decimal("55.00") + Decimal(min(len(rows), 5) * 8)
        if cadence == RecurringCandidate.Cadence.MONTHLY:
            confidence += Decimal("15.00")
        elif cadence == RecurringCandidate.Cadence.WEEKLY:
            confidence += Decimal("10.00")
        confidence = min(confidence, Decimal("95.00"))
        fingerprint = _candidate_fingerprint(label, account_id, category_id, amount)
        existing = RecurringCandidate.objects.filter(fingerprint=fingerprint).first()
        if existing and existing.status in {RecurringCandidate.Status.IGNORED, RecurringCandidate.Status.CONFIRMED}:
            candidates.append(existing)
            continue
        defaults = {
            "merchant": label.title(),
            "note_pattern": label,
            "account_id": account_id,
            "category_id": category_id,
            "amount": amount,
            "cadence": cadence,
            "first_seen": dates[0],
            "last_seen": dates[-1],
            "occurrence_count": len(rows),
            "confidence": confidence,
            "related_transaction_ids": [tx.id for tx in rows],
            "status": RecurringCandidate.Status.SUGGESTED,
        }
        candidate, _ = RecurringCandidate.objects.update_or_create(
            fingerprint=fingerprint,
            defaults=defaults,
        )
        candidates.append(candidate)
    return candidates


@db_transaction.atomic
def confirm_recurring_candidate(candidate: RecurringCandidate) -> RecurringRule:
    if candidate.matched_rule:
        candidate.status = RecurringCandidate.Status.CONFIRMED
        candidate.save(update_fields=["status", "updated_at"])
        return candidate.matched_rule
    account = candidate.account or Account.objects.filter(is_active=True).first()
    if not account:
        account = Account.objects.create(name="CASH", type=Account.Type.CASH)
    category = candidate.category or Category.objects.filter(name="Subscription", type=Category.Type.EXPENSE).first()
    next_due = add_month(candidate.last_seen) if candidate.cadence == RecurringCandidate.Cadence.MONTHLY else candidate.last_seen + timedelta(days=7)
    rule = RecurringRule.objects.create(
        name=candidate.merchant,
        kind=RecurringRule.Kind.EXPENSE,
        account=account,
        category=category,
        amount=candidate.amount,
        interval=RecurringRule.Interval.MONTHLY
        if candidate.cadence != RecurringCandidate.Cadence.WEEKLY
        else RecurringRule.Interval.WEEKLY,
        next_due=next_due,
        prompt_before_post=True,
        is_subscription=True,
        merchant_name=candidate.merchant,
        note=f"Confirmed from recurring candidate #{candidate.id}",
        is_active=True,
    )
    candidate.status = RecurringCandidate.Status.CONFIRMED
    candidate.matched_rule = rule
    candidate.save(update_fields=["status", "matched_rule", "updated_at"])
    return rule


def ignore_recurring_candidate(candidate: RecurringCandidate) -> RecurringCandidate:
    candidate.status = RecurringCandidate.Status.IGNORED
    candidate.save(update_fields=["status", "updated_at"])
    return candidate


def mark_subscription_reviewed(rule: RecurringRule, note: str = "") -> RecurringRule:
    rule.last_reviewed_at = timezone.now()
    if note:
        rule.review_note = note[:255]
    rule.save(update_fields=["last_reviewed_at", "review_note"])
    return rule


def subscription_rows() -> dict:
    candidates = detect_recurring_candidates()
    confirmed = RecurringRule.objects.filter(
        is_active=True,
        kind=RecurringRule.Kind.EXPENSE,
    ).filter(is_subscription=True).select_related("account", "category")
    if not confirmed.exists():
        confirmed = RecurringRule.objects.filter(
            is_active=True,
            kind=RecurringRule.Kind.EXPENSE,
            category__name__iexact="Subscription",
        ).select_related("account", "category")
    return {
        "confirmed": list(confirmed),
        "candidates": [item for item in candidates if item.status == RecurringCandidate.Status.SUGGESTED],
    }


def goal_rows() -> list[dict]:
    rows = []
    today = timezone.localdate()
    for goal in FinancialGoal.objects.all():
        target = money(goal.target_amount)
        current = money(goal.current_amount)
        if goal.linked_savings_goal:
            target = money(goal.linked_savings_goal.target_amount)
            current = money(goal.linked_savings_goal.current_amount)
        if goal.linked_debt:
            target = money(goal.linked_debt.principal_amount)
            current = max(target - money(goal.linked_debt.current_balance), ZERO)
        remaining = max(target - current, ZERO)
        months_left = _months_between(today, goal.target_date) if goal.target_date else 0
        required = money(remaining / Decimal(months_left)) if months_left else money(goal.monthly_target)
        monthly_target = money(goal.monthly_target) if goal.monthly_target > 0 else required
        progress = (current / target * Decimal("100")) if target > 0 else ZERO
        rows.append(
            {
                "goal": goal,
                "target": target,
                "current": current,
                "remaining": remaining,
                "months_left": months_left,
                "monthly_required": required,
                "monthly_target": monthly_target,
                "progress": progress,
                "behind": bool(goal.is_active and required > monthly_target and monthly_target > 0),
            }
        )
    return rows


def top_priority_goal() -> dict | None:
    for row in goal_rows():
        if row["goal"].is_active and row["remaining"] > 0:
            return row
    return None


def _top_leaks(month: date, candidates: list[RecurringCandidate]) -> list[dict]:
    leaks = []
    for item in category_spending(month):
        category = Category.objects.filter(id=item["category_id"]).first()
        amount = money(item["amount"])
        if category and category.is_discretionary and amount > 0:
            leaks.append(
                {
                    "type": "discretionary",
                    "title": f"Kurangi {category.name} 20%",
                    "reason": f"Kategori discretionary {category.name} bulan ini {format_idr(amount)}.",
                    "amount": _decimal_text(amount * Decimal("0.20")),
                    "action": "review_budget",
                    "related_model": "Category",
                    "related_object_id": category.id,
                }
            )
    for rule in RecurringRule.objects.filter(is_active=True, is_subscription=True, kind=RecurringRule.Kind.EXPENSE):
        leaks.append(
            {
                "type": "subscription",
                "title": f"Review subscription {rule.name}",
                "reason": f"Biaya rutin {format_idr(rule.amount)} jatuh tempo {rule.next_due:%d %b %Y}.",
                "amount": _decimal_text(rule.amount),
                "action": "review_subscription",
                "related_model": "RecurringRule",
                "related_object_id": rule.id,
            }
        )
    for candidate in candidates:
        if candidate.status == RecurringCandidate.Status.SUGGESTED:
            leaks.append(
                {
                    "type": "recurring_candidate",
                    "title": f"Kemungkinan subscription: {candidate.merchant}",
                    "reason": f"Muncul {candidate.occurrence_count}x dengan nominal {format_idr(candidate.amount)}.",
                    "amount": _decimal_text(candidate.amount),
                    "action": "confirm_or_ignore_candidate",
                    "related_model": "RecurringCandidate",
                    "related_object_id": candidate.id,
                }
            )
    merchant_totals = defaultdict(lambda: {"amount": ZERO, "count": 0, "ids": []})
    for tx in monthly_transactions(month).filter(kind=Transaction.Kind.EXPENSE):
        label = transaction_label(tx)
        merchant_totals[label]["amount"] += money(tx.amount)
        merchant_totals[label]["count"] += 1
        merchant_totals[label]["ids"].append(tx.id)
    for label, data in merchant_totals.items():
        if data["count"] >= 3 and data["amount"] >= Decimal("100000.00"):
            leaks.append(
                {
                    "type": "frequent_merchant",
                    "title": f"Merchant sering muncul: {label.title()}",
                    "reason": f"{data['count']} transaksi bulan ini, total {format_idr(data['amount'])}.",
                    "amount": _decimal_text(data["amount"] * Decimal("0.10")),
                    "action": "review_transactions",
                    "related_transaction_ids": data["ids"][:20],
                }
            )
    return sorted(leaks, key=lambda item: Decimal(item["amount"]), reverse=True)[:12]


def _action_plan(month: date, leaks: list[dict]) -> list[dict]:
    actions = []
    goal = top_priority_goal()
    for rec in generate_recommendations(month):
        if rec.status != Recommendation.Status.ACTIVE:
            continue
        actions.append(
            {
                "source": "recommendation",
                "title": rec.title,
                "reason": rec.reason,
                "amount": _decimal_text(rec.estimated_saving),
                "severity": rec.severity,
                "action": rec.action_type or "review",
                "recommendation_id": rec.id,
            }
        )
    for leak in leaks:
        action = {
            "source": "leak",
            "title": leak["title"],
            "reason": leak["reason"],
            "amount": leak["amount"],
            "severity": "warning" if Decimal(leak["amount"]) > 0 else "info",
            "action": leak["action"],
            "related_model": leak.get("related_model", ""),
            "related_object_id": leak.get("related_object_id"),
            "related_transaction_ids": leak.get("related_transaction_ids", []),
        }
        if goal and Decimal(leak["amount"]) > 0:
            action["goal_id"] = goal["goal"].id
            action["goal_name"] = goal["goal"].name
            action["reason"] += f" Arahkan potensi saving ke goal prioritas: {goal['goal'].name}."
        actions.append(action)
    seen = set()
    unique = []
    for action in actions:
        key = (action["source"], action["title"], action.get("related_object_id"))
        if key in seen:
            continue
        seen.add(key)
        unique.append(action)
    return unique[:15]


def generate_monthly_audit(month: date | None = None, *, force: bool = False) -> MonthlyAudit:
    month = first_day(month)
    existing = MonthlyAudit.objects.filter(month=month).first()
    if existing and existing.status == MonthlyAudit.Status.CLOSED and not force:
        return existing
    candidates = detect_recurring_candidates(month)
    summary = monthly_summary(month)
    leaks = _top_leaks(month, candidates)
    actions = _action_plan(month, leaks)
    snapshot = {
        "spending": [
            {"name": item["name"], "amount": _decimal_text(item["amount"])}
            for item in category_spending(month)[:10]
        ],
        "budgets": [
            {
                "category": row["budget"].category.name,
                "spent": _decimal_text(row["spent"]),
                "budget": _decimal_text(row["budget"].amount),
                "percent": str(row["percent"]),
            }
            for row in budget_progress(month)
        ],
        "subscription_candidates": len([item for item in candidates if item.status == RecurringCandidate.Status.SUGGESTED]),
        "goals": [
            {
                "id": row["goal"].id,
                "name": row["goal"].name,
                "remaining": _decimal_text(row["remaining"]),
                "monthly_required": _decimal_text(row["monthly_required"]),
                "progress": str(row["progress"]),
            }
            for row in goal_rows()[:8]
        ],
    }
    defaults = {
        "income": summary["income"],
        "expense": summary["expense"],
        "net": summary["net"],
        "saving_rate": summary["saving_rate"],
        "snapshot": snapshot,
        "top_leaks": leaks,
        "action_plan": actions,
    }
    audit, created = MonthlyAudit.objects.update_or_create(month=month, defaults=defaults)
    if created:
        audit.status = MonthlyAudit.Status.DRAFT
        audit.save(update_fields=["status"])
    return audit


def close_monthly_audit(month: date | None = None) -> MonthlyAudit:
    audit = generate_monthly_audit(month, force=True)
    audit.status = MonthlyAudit.Status.CLOSED
    audit.closed_at = timezone.now()
    audit.save(update_fields=["status", "closed_at", "updated_at"])
    return audit


def reopen_monthly_audit(month: date | None = None) -> MonthlyAudit:
    audit = MonthlyAudit.objects.get(month=first_day(month))
    audit.status = MonthlyAudit.Status.DRAFT
    audit.closed_at = None
    audit.save(update_fields=["status", "closed_at", "updated_at"])
    return audit


def recalculate_monthly_audit(month: date | None = None) -> MonthlyAudit:
    return generate_monthly_audit(month, force=True)


def _recurring_events(start: date, end: date) -> list[dict]:
    events = []
    for rule in RecurringRule.objects.filter(is_active=True).select_related("account", "to_account"):
        due = rule.next_due
        guard = 0
        while due <= end and guard < 120:
            if due >= start:
                if rule.kind == RecurringRule.Kind.INCOME:
                    effect = money(rule.amount)
                elif rule.kind == RecurringRule.Kind.EXPENSE:
                    effect = -money(rule.amount)
                else:
                    effect = ZERO
                events.append(
                    {
                        "date": due,
                        "label": rule.name,
                        "type": "subscription" if rule.is_subscription else rule.kind,
                        "amount": effect,
                    }
                )
            if rule.interval == RecurringRule.Interval.DAILY:
                due = due + timedelta(days=1)
            elif rule.interval == RecurringRule.Interval.WEEKLY:
                due = due + timedelta(days=7)
            else:
                due = add_month(due)
            guard += 1
    return events


def forecast_cashflow(days: int = 90) -> dict:
    today = timezone.localdate()
    end = today + timedelta(days=days - 1)
    start_balance = sum((item["balance"] for item in account_balances()), ZERO)
    events = _recurring_events(today, end)
    for debt in Debt.objects.filter(status=Debt.Status.OPEN, current_balance__gt=0, due_date__gte=today, due_date__lte=end):
        amount = money(debt.current_balance)
        events.append(
            {
                "date": debt.due_date,
                "label": debt.counterparty,
                "type": "debt_payment" if debt.direction == Debt.Direction.PAYABLE else "receivable_collection",
                "amount": -amount if debt.direction == Debt.Direction.PAYABLE else amount,
            }
        )
    goal = top_priority_goal()
    if goal:
        contribution = money(goal["monthly_target"] or goal["monthly_required"])
        due = today
        while contribution > 0 and due <= end:
            events.append(
                {
                    "date": due,
                    "label": goal["goal"].name,
                    "type": "goal_contribution",
                    "amount": -contribution,
                }
            )
            due = add_month(due)
    remaining_budget = sum((max(row["remaining"], ZERO) for row in budget_progress(today)), ZERO)
    month_end = add_month(first_day(today)) - timedelta(days=1)
    remaining_days = max(1, (min(month_end, end) - today).days + 1)
    daily_budget_burn = money(remaining_budget / Decimal(remaining_days)) if remaining_budget > 0 else ZERO

    by_day = defaultdict(list)
    for event in events:
        by_day[event["date"]].append(event)
    balance = money(start_balance)
    daily = []
    event_rows = []
    min_balance = balance
    min_day = today
    for index in range(days):
        day = today + timedelta(days=index)
        if daily_budget_burn > 0 and day <= month_end:
            balance -= daily_budget_burn
            event_rows.append(
                {
                    "date": day,
                    "label": "Budget reserve",
                    "type": "budget_reserve",
                    "amount": -daily_budget_burn,
                }
            )
        for event in by_day.get(day, []):
            balance += money(event["amount"])
            event_rows.append(event)
        balance = money(balance)
        if balance < min_balance:
            min_balance = balance
            min_day = day
        daily.append({"label": day.strftime("%d %b"), "date": day.isoformat(), "balance": balance})
    checkpoints = []
    for checkpoint in (30, 60, 90):
        index = min(checkpoint, days) - 1
        checkpoints.append({"days": checkpoint, "balance": daily[index]["balance"] if daily else start_balance})
    return {
        "start_balance": money(start_balance),
        "daily": daily,
        "checkpoints": checkpoints,
        "events": sorted(event_rows, key=lambda item: item["date"])[:80],
        "min_balance": money(min_balance),
        "min_balance_date": min_day,
        "low_balance_warning": min_balance < LOW_BALANCE_THRESHOLD,
        "low_balance_threshold": LOW_BALANCE_THRESHOLD,
    }


def coach_overview() -> dict:
    audit = generate_monthly_audit(first_day())
    return {
        "audit": audit,
        "forecast": forecast_cashflow(90),
        "subscriptions": subscription_rows(),
        "goals": goal_rows(),
    }
