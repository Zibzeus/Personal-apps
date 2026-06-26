import json
from datetime import date, timedelta
from decimal import Decimal
from unittest.mock import patch
from urllib.error import URLError

from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from .management.commands.seed_defaults import Command as SeedCommand
from .exchange_rates import ExchangeRateUnavailable, convert_to_idr
from .forms import DebtForm, TransactionForm
from .models import (
    Account,
    Budget,
    Category,
    CurrencyConversionCheck,
    Debt,
    ExchangeRateSnapshot,
    Recommendation,
    Transaction,
)
from .parser import parse_message
from .recommendations import generate_recommendations
from .services import (
    account_balances,
    create_debt,
    create_transaction,
    create_transfer,
    first_day,
    monthly_summary,
    repay_debt,
)


class FakeRateResponse:
    def __init__(self, payload):
        self.payload = payload

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, traceback):
        return False

    def read(self):
        return json.dumps(self.payload).encode("utf-8")


class ParserTests(TestCase):
    def test_parse_expense(self):
        parsed = parse_message("makan 35000 bca")
        self.assertEqual(parsed.action, "expense")
        self.assertEqual(parsed.amount, Decimal("35000.00"))
        self.assertEqual(parsed.account_hint, "bca")
        self.assertEqual(parsed.category_hint, "Makan")

    def test_parse_income(self):
        parsed = parse_message("gaji 15000000 bca")
        self.assertEqual(parsed.action, "income")
        self.assertEqual(parsed.amount, Decimal("15000000.00"))

    def test_parse_transfer(self):
        parsed = parse_message("tf bca ovo 200000")
        self.assertEqual(parsed.action, "transfer")
        self.assertEqual(parsed.account_hint, "bca")
        self.assertEqual(parsed.to_account_hint, "ovo")

    def test_parse_debt(self):
        parsed = parse_message("utang ke budi 100000")
        self.assertEqual(parsed.action, "debt_payable")
        self.assertEqual(parsed.counterparty, "budi")

    def test_parse_rejects_scientific_notation(self):
        parsed = parse_message("makan 1e5 bca")
        self.assertIsNone(parsed.amount)


class FinanceServiceTests(TestCase):
    def setUp(self):
        SeedCommand().handle()
        self.bca = Account.objects.get(name="BCA")
        self.ovo = Account.objects.get(name="OVO")
        self.salary = Category.objects.get(name="Salary")
        self.food = Category.objects.get(name="Makan")

    def test_balances_and_summary(self):
        create_transaction(kind=Transaction.Kind.INCOME, amount=1000000, account=self.bca, category=self.salary)
        create_transaction(kind=Transaction.Kind.EXPENSE, amount=100000, account=self.bca, category=self.food)
        create_transfer(from_account=self.bca, to_account=self.ovo, amount=200000)
        balances = {item["account"].name: item["balance"] for item in account_balances()}
        self.assertEqual(balances["BCA"], Decimal("700000.00"))
        self.assertEqual(balances["OVO"], Decimal("200000.00"))
        summary = monthly_summary()
        self.assertEqual(summary["income"], Decimal("1000000.00"))
        self.assertEqual(summary["expense"], Decimal("100000.00"))

    def test_rupiah_form_accepts_indonesian_separator_and_rejects_e(self):
        empty_form = TransactionForm()
        self.assertEqual(empty_form.fields["amount"].widget.attrs.get("data-rupiah-input"), "true")

        form = TransactionForm(
            data={
                "date": date.today().isoformat(),
                "kind": Transaction.Kind.EXPENSE,
                "account": self.bca.id,
                "category": self.food.id,
                "amount": "Rp100.000",
                "merchant": "",
                "note": "test",
                "debt": "",
                "source": Transaction.Source.WEB,
            }
        )
        self.assertTrue(form.is_valid(), form.errors)
        self.assertEqual(form.cleaned_data["amount"], Decimal("100000"))

        form = TransactionForm(
            data={
                "date": date.today().isoformat(),
                "kind": Transaction.Kind.EXPENSE,
                "account": self.bca.id,
                "category": self.food.id,
                "amount": "1e5",
                "merchant": "",
                "note": "test",
                "debt": "",
                "source": Transaction.Source.WEB,
            }
        )
        self.assertFalse(form.is_valid())
        self.assertIn("amount", form.errors)


class DebtWorkflowTests(TestCase):
    def setUp(self):
        SeedCommand().handle()
        self.bca = Account.objects.get(name="BCA")

    def test_debt_form_sets_current_balance_from_principal(self):
        form = DebtForm(
            data={
                "direction": Debt.Direction.PAYABLE,
                "counterparty": "Budi",
                "principal_amount": "120.000",
                "due_date": "",
                "note": "",
            }
        )
        self.assertTrue(form.is_valid(), form.errors)
        self.assertNotIn("current_balance", DebtForm().fields)
        debt = form.save()
        self.assertEqual(debt.principal_amount, Decimal("120000"))
        self.assertEqual(debt.current_balance, Decimal("120000"))
        self.assertEqual(debt.status, Debt.Status.OPEN)

    def test_repay_payable_decreases_balance_and_records_expense(self):
        debt = create_debt(direction=Debt.Direction.PAYABLE, counterparty="Budi", amount=100000)
        tx = repay_debt(debt=debt, account=self.bca, amount=20000, note="Bayar Budi")
        debt.refresh_from_db()
        self.assertEqual(tx.kind, Transaction.Kind.REPAYMENT)
        self.assertEqual(tx.amount, Decimal("20000.00"))
        self.assertEqual(tx.note, "Bayar Budi")
        self.assertEqual(debt.current_balance, Decimal("80000.00"))
        self.assertEqual(monthly_summary()["expense"], Decimal("20000.00"))

    def test_repay_receivable_decreases_balance_and_records_income(self):
        debt = create_debt(direction=Debt.Direction.RECEIVABLE, counterparty="Sari", amount=100000)
        tx = repay_debt(debt=debt, account=self.bca, amount=25000)
        debt.refresh_from_db()
        self.assertEqual(tx.amount, Decimal("25000.00"))
        self.assertEqual(debt.current_balance, Decimal("75000.00"))
        self.assertEqual(monthly_summary()["income"], Decimal("25000.00"))

    def test_overpayment_clamps_to_balance_and_closes_debt(self):
        debt = create_debt(direction=Debt.Direction.PAYABLE, counterparty="Budi", amount=100000)
        tx = repay_debt(debt=debt, account=self.bca, amount=150000)
        debt.refresh_from_db()
        self.assertEqual(tx.amount, Decimal("100000.00"))
        self.assertEqual(debt.current_balance, Decimal("0.00"))
        self.assertEqual(debt.status, Debt.Status.CLOSED)


class CurrencyConversionTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="tester", password="secret")

    @patch("finance.exchange_rates.urlopen")
    def test_successful_api_response_stores_snapshot_and_conversion_check(self, mocked_urlopen):
        mocked_urlopen.return_value = FakeRateResponse(
            {
                "result": "success",
                "provider": "https://www.exchangerate-api.com",
                "time_last_update_unix": 1782510000,
                "time_next_update_unix": 1782596400,
                "rates": {"IDR": 16000},
            }
        )
        result = convert_to_idr("USD", Decimal("2"))
        self.assertEqual(ExchangeRateSnapshot.objects.count(), 1)
        self.assertEqual(CurrencyConversionCheck.objects.count(), 1)
        self.assertEqual(result.converted_amount, Decimal("32000.00"))
        self.assertFalse(result.is_stale)

    @patch("finance.exchange_rates.urlopen")
    def test_api_failure_uses_latest_cached_snapshot(self, mocked_urlopen):
        mocked_urlopen.side_effect = URLError("offline")
        snapshot = ExchangeRateSnapshot.objects.create(
            base_currency="USD",
            target_currency="IDR",
            rate=Decimal("15000.00000000"),
            time_next_update=timezone.now() - timedelta(days=1),
            fetched_at=timezone.now() - timedelta(days=2),
        )
        result = convert_to_idr("USD", Decimal("1"))
        self.assertEqual(result.snapshot, snapshot)
        self.assertTrue(result.is_stale)
        self.assertEqual(result.converted_amount, Decimal("15000.00"))

    @patch("finance.exchange_rates.urlopen")
    def test_missing_cached_rate_raises_clear_error(self, mocked_urlopen):
        mocked_urlopen.side_effect = URLError("offline")
        with self.assertRaises(ExchangeRateUnavailable):
            convert_to_idr("EUR", Decimal("1"))

    def test_currency_page_requires_login(self):
        response = self.client.get(reverse("finance:currency"))
        self.assertEqual(response.status_code, 302)
        self.assertIn("/accounts/login/", response["Location"])


class RecommendationTests(TestCase):
    def setUp(self):
        SeedCommand().handle()
        self.bca = Account.objects.get(name="BCA")
        self.food = Category.objects.get(name="Makan")
        self.salary = Category.objects.get(name="Salary")

    def test_low_saving_and_budget_recommendations(self):
        Budget.objects.create(month=first_day(), category=self.food, amount=Decimal("100000.00"))
        create_transaction(kind=Transaction.Kind.INCOME, amount=1000000, account=self.bca, category=self.salary)
        create_transaction(kind=Transaction.Kind.EXPENSE, amount=950000, account=self.bca, category=self.food)
        recs = generate_recommendations()
        types = {rec.type for rec in recs}
        self.assertIn("saving_rate_gap", types)
        self.assertIn("budget_variance", types)

    def test_debt_due_recommendation(self):
        Debt.objects.create(
            direction=Debt.Direction.PAYABLE,
            counterparty="Budi",
            principal_amount=100000,
            current_balance=100000,
            due_date=timezone.localdate() + timedelta(days=2),
        )
        recs = generate_recommendations()
        self.assertTrue(any(rec.type == "debt_due" for rec in recs))


class DashboardTests(TestCase):
    def setUp(self):
        SeedCommand().handle()
        self.user = User.objects.create_user(username="tester", password="secret")

    def test_dashboard_requires_login(self):
        response = self.client.get(reverse("finance:dashboard"))
        self.assertEqual(response.status_code, 302)
        self.assertIn("/accounts/login/", response["Location"])

    def test_dashboard_loads_after_login(self):
        self.client.force_login(self.user)
        response = self.client.get(reverse("finance:dashboard"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Financial Audit")

    def test_export_csv(self):
        self.client.force_login(self.user)
        response = self.client.get(reverse("finance:export_csv"))
        self.assertEqual(response.status_code, 200)
        self.assertIn("text/csv", response["Content-Type"])
