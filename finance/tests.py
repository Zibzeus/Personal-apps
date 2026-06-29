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
    AllocationTarget,
    Budget,
    Category,
    CurrencyConversionCheck,
    Debt,
    ExchangeRateSnapshot,
    FinancialGoal,
    FinancialFreedomProfile,
    Instrument,
    InvestmentAccount,
    InvestmentTransaction,
    MonthlyAudit,
    PriceSnapshot,
    Recommendation,
    RecurringCandidate,
    RecurringRule,
    Transaction,
)
from .parser import parse_message
from .recommendations import generate_recommendations
from .services import (
    account_balances,
    add_month,
    create_debt,
    create_transaction,
    create_transfer,
    first_day,
    monthly_summary,
    repay_debt,
)
from .coach import (
    close_monthly_audit,
    confirm_recurring_candidate,
    detect_recurring_candidates,
    forecast_cashflow,
    generate_monthly_audit,
    goal_rows,
    recalculate_monthly_audit,
    reopen_monthly_audit,
)
from .investments import (
    MarketDataUnavailable,
    financial_freedom_summary,
    generate_investment_insights,
    manual_price,
    portfolio_summary,
    record_investment_transaction,
    refresh_price,
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

    def test_parse_investment_buy_lot(self):
        parsed = parse_message("buy bbca 10 lot 10000 ajaib")
        self.assertEqual(parsed.action, "investment_buy")
        self.assertEqual(parsed.instrument_symbol, "BBCA")
        self.assertEqual(parsed.investment_quantity, Decimal("10.00"))
        self.assertEqual(parsed.investment_unit, "lot")
        self.assertEqual(parsed.investment_price, Decimal("10000.00"))
        self.assertEqual(parsed.investment_account_hint, "ajaib")

    def test_parse_investment_price(self):
        parsed = parse_message("price bbca 10500")
        self.assertEqual(parsed.action, "investment_price")
        self.assertEqual(parsed.instrument_symbol, "BBCA")
        self.assertEqual(parsed.investment_price, Decimal("10500.00"))


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


class InvestmentPortfolioTests(TestCase):
    def setUp(self):
        SeedCommand().handle()
        self.user = User.objects.create_user(username="tester", password="secret")
        self.bca = Account.objects.get(name="BCA")
        self.salary = Category.objects.get(name="Salary")
        self.instrument = Instrument.objects.create(
            symbol="BBCA",
            provider_symbol="BBCA.JK",
            name="Bank Central Asia",
            market=Instrument.Market.IDX,
            currency="IDR",
            asset_class=Instrument.AssetClass.STOCK_ID,
            lot_size=Decimal("100"),
        )
        self.investment_account = InvestmentAccount.objects.create(name="Ajaib", platform="Ajaib")

    def test_buy_lot_and_price_gain(self):
        record_investment_transaction(
            kind=InvestmentTransaction.Kind.BUY,
            instrument=self.instrument,
            account=self.investment_account,
            quantity=10,
            unit="lot",
            price=1000,
        )
        manual_price(self.instrument, 1100)
        summary = portfolio_summary()
        row = summary["positions"][0]
        self.assertEqual(row["quantity"], Decimal("1000.0000"))
        self.assertEqual(row["cost_basis"], Decimal("1000000.00"))
        self.assertEqual(row["market_value_idr"], Decimal("1100000.00"))
        self.assertEqual(row["unrealized_gain"], Decimal("100000.00"))

    def test_partial_sell_realized_gain_and_remaining_average_cost(self):
        record_investment_transaction(
            kind=InvestmentTransaction.Kind.BUY,
            instrument=self.instrument,
            account=self.investment_account,
            quantity=10,
            unit="lot",
            price=1000,
        )
        record_investment_transaction(
            kind=InvestmentTransaction.Kind.SELL,
            instrument=self.instrument,
            account=self.investment_account,
            quantity=2,
            unit="lot",
            price=1200,
        )
        manual_price(self.instrument, 1200)
        row = portfolio_summary()["positions"][0]
        self.assertEqual(row["quantity"], Decimal("800.0000"))
        self.assertEqual(row["cost_basis"], Decimal("800000.00"))
        self.assertEqual(row["realized_gain"], Decimal("40000.00"))
        self.assertEqual(row["average_cost"], Decimal("1000.00"))

    def test_dividend_adds_income_without_quantity_change(self):
        record_investment_transaction(
            kind=InvestmentTransaction.Kind.BUY,
            instrument=self.instrument,
            account=self.investment_account,
            quantity=10,
            unit="lot",
            price=1000,
        )
        record_investment_transaction(
            kind=InvestmentTransaction.Kind.DIVIDEND,
            instrument=self.instrument,
            account=self.investment_account,
            cash_amount=150000,
        )
        row = portfolio_summary()["positions"][0]
        self.assertEqual(row["quantity"], Decimal("1000.0000"))
        self.assertEqual(row["dividend_income"], Decimal("150000.00"))

    @patch("finance.market_data.urlopen")
    def test_alpha_vantage_price_success_stores_snapshot(self, mocked_urlopen):
        mocked_urlopen.return_value = FakeRateResponse(
            {
                "Global Quote": {
                    "01. symbol": "BBCA.JK",
                    "05. price": "1100.00",
                }
            }
        )
        with self.settings(ALPHA_VANTAGE_API_KEY="demo"):
            result = refresh_price(self.instrument, provider="alpha")
        self.assertFalse(result.is_stale)
        self.assertEqual(PriceSnapshot.objects.filter(instrument=self.instrument).count(), 1)
        self.assertEqual(result.snapshot.price, Decimal("1100.0000"))

    @patch("finance.market_data.urlopen")
    def test_price_failure_uses_cached_snapshot_and_marks_stale(self, mocked_urlopen):
        mocked_urlopen.side_effect = URLError("offline")
        snapshot = manual_price(self.instrument, 1000)
        with self.settings(ALPHA_VANTAGE_API_KEY="demo"):
            result = refresh_price(self.instrument, provider="alpha")
        snapshot.refresh_from_db()
        self.assertTrue(result.is_stale)
        self.assertTrue(snapshot.is_stale)
        self.assertEqual(result.snapshot.price, Decimal("1000.0000"))

    @patch("finance.market_data.urlopen")
    def test_price_failure_without_cache_raises(self, mocked_urlopen):
        mocked_urlopen.side_effect = URLError("offline")
        with self.settings(ALPHA_VANTAGE_API_KEY="demo"):
            with self.assertRaises(MarketDataUnavailable):
                refresh_price(self.instrument, provider="alpha")

    def test_fire_summary_and_investment_insights(self):
        create_transaction(kind=Transaction.Kind.INCOME, amount=5000000, account=self.bca, category=self.salary)
        FinancialFreedomProfile.objects.create(
            annual_expense=Decimal("12000000.00"),
            fire_multiplier=Decimal("25"),
            target_monthly_contribution=Decimal("1000000.00"),
            emergency_fund_months=Decimal("6"),
        )
        record_investment_transaction(
            kind=InvestmentTransaction.Kind.BUY,
            instrument=self.instrument,
            account=self.investment_account,
            quantity=10,
            unit="lot",
            price=1000,
        )
        manual_price(self.instrument, 1100)
        summary = financial_freedom_summary()
        self.assertEqual(summary["fire_number"], Decimal("300000000.00"))
        self.assertGreater(summary["progress"], Decimal("0"))
        insights = generate_investment_insights()
        self.assertTrue(any(insight.type == "fire_gap" for insight in insights))

    def test_investment_pages_require_login(self):
        for name in ["finance:investments", "finance:investment_instruments", "finance:investment_transactions", "finance:financial_freedom", "finance:watchlist"]:
            response = self.client.get(reverse(name))
            self.assertEqual(response.status_code, 302)
            self.assertIn("/accounts/login/", response["Location"])

    def test_investment_pages_load_after_login(self):
        self.client.force_login(self.user)
        pages = [
            ("finance:investments", "Investment Portfolio"),
            ("finance:investment_instruments", "Investment Instruments"),
            ("finance:investment_transactions", "Investment Transactions"),
            ("finance:financial_freedom", "Financial Freedom"),
            ("finance:watchlist", "Watchlist"),
        ]
        for name, marker in pages:
            response = self.client.get(reverse(name))
            self.assertEqual(response.status_code, 200)
            self.assertContains(response, marker)


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


class FinancialCoachTests(TestCase):
    def setUp(self):
        SeedCommand().handle()
        self.user = User.objects.create_user(username="tester", password="secret")
        self.bca = Account.objects.get(name="BCA")
        self.salary = Category.objects.get(name="Salary")
        self.shopping = Category.objects.get(name="Shopping")
        self.subscription = Category.objects.get(name="Subscription")

    def test_recurring_candidate_detection_and_confirmation(self):
        current_month = first_day()
        previous_month = first_day(current_month - timedelta(days=20))
        two_months_ago = first_day(previous_month - timedelta(days=20))
        create_transaction(
            kind=Transaction.Kind.EXPENSE,
            amount=59000,
            account=self.bca,
            category=self.subscription,
            merchant="Spotify",
            note="Spotify Premium",
            tx_date=two_months_ago + timedelta(days=5),
        )
        create_transaction(
            kind=Transaction.Kind.EXPENSE,
            amount=59000,
            account=self.bca,
            category=self.subscription,
            merchant="Spotify",
            note="Spotify Premium",
            tx_date=previous_month + timedelta(days=5),
        )

        candidates = detect_recurring_candidates()
        candidate = next(item for item in candidates if item.merchant == "Spotify")
        self.assertEqual(candidate.status, RecurringCandidate.Status.SUGGESTED)
        self.assertEqual(candidate.cadence, RecurringCandidate.Cadence.MONTHLY)

        rule = confirm_recurring_candidate(candidate)
        candidate.refresh_from_db()
        self.assertTrue(rule.is_subscription)
        self.assertEqual(candidate.status, RecurringCandidate.Status.CONFIRMED)
        self.assertEqual(candidate.matched_rule, rule)

    def test_monthly_audit_close_reopen_and_action_goal_routing(self):
        FinancialGoal.objects.create(
            name="Dana Darurat",
            type=FinancialGoal.Type.EMERGENCY_FUND,
            target_amount=Decimal("3000000.00"),
            current_amount=Decimal("500000.00"),
            monthly_target=Decimal("500000.00"),
            priority=1,
        )
        create_transaction(kind=Transaction.Kind.INCOME, amount=5000000, account=self.bca, category=self.salary)
        create_transaction(kind=Transaction.Kind.EXPENSE, amount=1000000, account=self.bca, category=self.shopping, merchant="Tokopedia")

        audit = generate_monthly_audit()
        self.assertEqual(MonthlyAudit.objects.count(), 1)
        self.assertEqual(audit.income, Decimal("5000000.00"))
        self.assertTrue(any(item["type"] == "discretionary" for item in audit.top_leaks))
        self.assertTrue(any(item.get("goal_name") == "Dana Darurat" for item in audit.action_plan))

        closed = close_monthly_audit()
        self.assertEqual(closed.status, MonthlyAudit.Status.CLOSED)
        reopened = reopen_monthly_audit()
        self.assertEqual(reopened.status, MonthlyAudit.Status.DRAFT)
        recalculated = recalculate_monthly_audit()
        self.assertEqual(recalculated.month, first_day())

    def test_goal_rows_calculate_monthly_required(self):
        FinancialGoal.objects.create(
            name="Laptop",
            target_amount=Decimal("600000.00"),
            current_amount=Decimal("0.00"),
            target_date=timezone.localdate() + timedelta(days=90),
            priority=1,
        )
        row = goal_rows()[0]
        self.assertEqual(row["monthly_required"], Decimal("200000.00"))
        self.assertEqual(row["progress"], Decimal("0"))

    def test_forecast_uses_recurring_debt_goal_and_does_not_create_transactions(self):
        self.bca.opening_balance = Decimal("100000.00")
        self.bca.save(update_fields=["opening_balance"])
        RecurringRule.objects.create(
            name="Netflix",
            kind=RecurringRule.Kind.EXPENSE,
            account=self.bca,
            category=self.subscription,
            amount=Decimal("150000.00"),
            interval=RecurringRule.Interval.MONTHLY,
            next_due=timezone.localdate() + timedelta(days=1),
            is_subscription=True,
        )
        Debt.objects.create(
            direction=Debt.Direction.PAYABLE,
            counterparty="Budi",
            principal_amount=Decimal("50000.00"),
            current_balance=Decimal("50000.00"),
            due_date=timezone.localdate() + timedelta(days=2),
        )
        FinancialGoal.objects.create(
            name="Dana Darurat",
            target_amount=Decimal("1000000.00"),
            current_amount=Decimal("0.00"),
            monthly_target=Decimal("100000.00"),
            priority=1,
        )
        before = Transaction.objects.count()
        data = forecast_cashflow(90)
        self.assertEqual(Transaction.objects.count(), before)
        self.assertTrue(data["low_balance_warning"])
        event_types = {item["type"] for item in data["events"]}
        self.assertIn("subscription", event_types)
        self.assertIn("debt_payment", event_types)
        self.assertIn("goal_contribution", event_types)

    def test_coach_pages_require_login_and_load_after_login(self):
        for name in ["finance:coach", "finance:monthly_audit", "finance:subscriptions", "finance:forecast", "finance:financial_goals"]:
            response = self.client.get(reverse(name))
            self.assertEqual(response.status_code, 302)
            self.assertIn("/accounts/login/", response["Location"])

        self.client.force_login(self.user)
        pages = [
            ("finance:coach", "Leak Audit"),
            ("finance:monthly_audit", "Monthly audit"),
            ("finance:subscriptions", "Subscriptions"),
            ("finance:forecast", "90-Day Forecast"),
            ("finance:financial_goals", "Financial Goals"),
        ]
        for name, marker in pages:
            response = self.client.get(reverse(name))
            self.assertEqual(response.status_code, 200)
            self.assertContains(response, marker)


class DashboardTests(TestCase):
    def setUp(self):
        SeedCommand().handle()
        self.user = User.objects.create_user(username="tester", password="secret")

    def test_home_requires_login(self):
        response = self.client.get(reverse("home"))
        self.assertEqual(response.status_code, 302)
        self.assertIn("/accounts/login/", response["Location"])

    def test_home_loads_after_login(self):
        self.client.force_login(self.user)
        response = self.client.get(reverse("home"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Choose Your Workspace")
        self.assertContains(response, "Money Manager")
        self.assertContains(response, "Productivity")

    def test_dashboard_requires_login(self):
        response = self.client.get(reverse("finance:dashboard"))
        self.assertEqual(response.status_code, 302)
        self.assertIn("/accounts/login/", response["Location"])

    def test_dashboard_is_mounted_under_money(self):
        self.assertEqual(reverse("finance:dashboard"), "/money/")

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
