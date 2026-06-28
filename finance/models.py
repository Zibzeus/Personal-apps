from django.db import models
from django.utils import timezone


class Account(models.Model):
    class Type(models.TextChoices):
        CASH = "cash", "Cash"
        BANK = "bank", "Bank"
        E_WALLET = "e_wallet", "E-wallet"
        CREDIT = "credit", "Credit"
        SAVINGS = "savings", "Savings"

    name = models.CharField(max_length=80, unique=True)
    type = models.CharField(max_length=20, choices=Type.choices, default=Type.CASH)
    opening_balance = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["name"]

    def __str__(self):
        return self.name


class Instrument(models.Model):
    class Market(models.TextChoices):
        IDX = "IDX", "Indonesia"
        US = "US", "United States"
        GLOBAL = "GLOBAL", "Global"
        CRYPTO = "CRYPTO", "Crypto"
        OTHER = "OTHER", "Other"

    class AssetClass(models.TextChoices):
        STOCK_ID = "stock_id", "Indonesia Stock"
        STOCK_US = "stock_us", "US Stock"
        ETF = "etf", "ETF"
        MUTUAL_FUND = "mutual_fund", "Mutual Fund"
        CRYPTO = "crypto", "Crypto"
        BOND = "bond", "Bond"
        CASH_EQUIVALENT = "cash_equivalent", "Cash Equivalent"
        OTHER = "other", "Other"

    symbol = models.CharField(max_length=24)
    provider_symbol = models.CharField(max_length=40, blank=True)
    name = models.CharField(max_length=120, blank=True)
    market = models.CharField(max_length=20, choices=Market.choices, default=Market.IDX)
    currency = models.CharField(max_length=3, default="IDR")
    asset_class = models.CharField(max_length=30, choices=AssetClass.choices, default=AssetClass.STOCK_ID)
    lot_size = models.DecimalField(max_digits=12, decimal_places=4, default=100)
    is_active = models.BooleanField(default=True)
    is_watchlisted = models.BooleanField(default=False)
    watch_note = models.CharField(max_length=255, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["market", "symbol"]
        constraints = [
            models.UniqueConstraint(fields=["market", "symbol"], name="unique_instrument_market_symbol")
        ]

    def __str__(self):
        return f"{self.symbol} ({self.market})"


class InvestmentAccount(models.Model):
    name = models.CharField(max_length=80, unique=True)
    platform = models.CharField(max_length=80, blank=True)
    currency = models.CharField(max_length=3, default="IDR")
    linked_cash_account = models.ForeignKey(Account, on_delete=models.SET_NULL, null=True, blank=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["name"]

    def __str__(self):
        return self.name


class Category(models.Model):
    class Type(models.TextChoices):
        INCOME = "income", "Income"
        EXPENSE = "expense", "Expense"

    name = models.CharField(max_length=80)
    type = models.CharField(max_length=20, choices=Type.choices)
    is_fixed = models.BooleanField(default=False)
    is_discretionary = models.BooleanField(default=False)
    keywords = models.CharField(max_length=255, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["type", "name"]
        constraints = [
            models.UniqueConstraint(fields=["name", "type"], name="unique_category_name_type")
        ]

    def __str__(self):
        return f"{self.name} ({self.type})"


class Debt(models.Model):
    class Direction(models.TextChoices):
        PAYABLE = "payable", "Payable"
        RECEIVABLE = "receivable", "Receivable"

    class Status(models.TextChoices):
        OPEN = "open", "Open"
        CLOSED = "closed", "Closed"

    direction = models.CharField(max_length=20, choices=Direction.choices)
    counterparty = models.CharField(max_length=120)
    principal_amount = models.DecimalField(max_digits=14, decimal_places=2)
    current_balance = models.DecimalField(max_digits=14, decimal_places=2)
    due_date = models.DateField(null=True, blank=True)
    note = models.CharField(max_length=255, blank=True)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.OPEN)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["status", "due_date", "counterparty"]

    def __str__(self):
        label = "Utang" if self.direction == self.Direction.PAYABLE else "Piutang"
        return f"{label} - {self.counterparty}"


class Transaction(models.Model):
    class Kind(models.TextChoices):
        EXPENSE = "expense", "Expense"
        INCOME = "income", "Income"
        ADJUSTMENT = "adjustment", "Adjustment"
        REPAYMENT = "repayment", "Repayment"

    class Source(models.TextChoices):
        WEB = "web", "Web"
        TELEGRAM = "telegram", "Telegram"
        SYSTEM = "system", "System"

    class Status(models.TextChoices):
        CONFIRMED = "confirmed", "Confirmed"
        DELETED = "deleted", "Deleted"

    date = models.DateField(default=timezone.localdate)
    kind = models.CharField(max_length=20, choices=Kind.choices)
    account = models.ForeignKey(Account, on_delete=models.PROTECT, related_name="transactions")
    category = models.ForeignKey(
        Category, on_delete=models.SET_NULL, null=True, blank=True, related_name="transactions"
    )
    amount = models.DecimalField(max_digits=14, decimal_places=2)
    merchant = models.CharField(max_length=120, blank=True)
    note = models.CharField(max_length=255, blank=True)
    debt = models.ForeignKey(Debt, on_delete=models.SET_NULL, null=True, blank=True)
    source = models.CharField(max_length=20, choices=Source.choices, default=Source.WEB)
    source_user_id = models.CharField(max_length=80, blank=True)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.CONFIRMED)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-date", "-created_at"]
        indexes = [
            models.Index(fields=["date", "kind", "status"]),
            models.Index(fields=["source", "source_user_id"]),
        ]

    def __str__(self):
        return f"{self.date} {self.kind} {self.amount}"


class Transfer(models.Model):
    class Status(models.TextChoices):
        CONFIRMED = "confirmed", "Confirmed"
        DELETED = "deleted", "Deleted"

    date = models.DateField(default=timezone.localdate)
    from_account = models.ForeignKey(Account, on_delete=models.PROTECT, related_name="outgoing_transfers")
    to_account = models.ForeignKey(Account, on_delete=models.PROTECT, related_name="incoming_transfers")
    amount = models.DecimalField(max_digits=14, decimal_places=2)
    fee_amount = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    note = models.CharField(max_length=255, blank=True)
    source = models.CharField(max_length=20, choices=Transaction.Source.choices, default=Transaction.Source.WEB)
    source_user_id = models.CharField(max_length=80, blank=True)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.CONFIRMED)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-date", "-created_at"]

    def __str__(self):
        return f"{self.from_account} -> {self.to_account} {self.amount}"


class Budget(models.Model):
    month = models.DateField()
    category = models.ForeignKey(Category, on_delete=models.CASCADE, related_name="budgets")
    amount = models.DecimalField(max_digits=14, decimal_places=2)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-month", "category__name"]
        constraints = [
            models.UniqueConstraint(fields=["month", "category"], name="unique_budget_month_category")
        ]

    def __str__(self):
        return f"{self.month:%Y-%m} {self.category.name}"


class RecurringRule(models.Model):
    class Kind(models.TextChoices):
        EXPENSE = "expense", "Expense"
        INCOME = "income", "Income"
        TRANSFER = "transfer", "Transfer"

    class Interval(models.TextChoices):
        DAILY = "daily", "Daily"
        WEEKLY = "weekly", "Weekly"
        MONTHLY = "monthly", "Monthly"

    name = models.CharField(max_length=120)
    kind = models.CharField(max_length=20, choices=Kind.choices)
    account = models.ForeignKey(Account, on_delete=models.PROTECT, related_name="recurring_rules")
    to_account = models.ForeignKey(
        Account, on_delete=models.PROTECT, null=True, blank=True, related_name="incoming_recurring_rules"
    )
    category = models.ForeignKey(Category, on_delete=models.SET_NULL, null=True, blank=True)
    amount = models.DecimalField(max_digits=14, decimal_places=2)
    interval = models.CharField(max_length=20, choices=Interval.choices, default=Interval.MONTHLY)
    next_due = models.DateField()
    prompt_before_post = models.BooleanField(default=True)
    note = models.CharField(max_length=255, blank=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["next_due", "name"]

    def __str__(self):
        return self.name


class SavingsGoal(models.Model):
    name = models.CharField(max_length=120)
    target_amount = models.DecimalField(max_digits=14, decimal_places=2)
    current_amount = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    target_date = models.DateField(null=True, blank=True)
    linked_account = models.ForeignKey(Account, on_delete=models.SET_NULL, null=True, blank=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-is_active", "target_date", "name"]

    def __str__(self):
        return self.name


class Recommendation(models.Model):
    class Severity(models.TextChoices):
        INFO = "info", "Info"
        WARNING = "warning", "Warning"
        CRITICAL = "critical", "Critical"

    class Status(models.TextChoices):
        ACTIVE = "active", "Active"
        IGNORED = "ignored", "Ignored"
        DONE = "done", "Done"

    fingerprint = models.CharField(max_length=160, unique=True)
    generated_for_month = models.DateField()
    type = models.CharField(max_length=60)
    severity = models.CharField(max_length=20, choices=Severity.choices, default=Severity.INFO)
    title = models.CharField(max_length=160)
    reason = models.TextField()
    estimated_saving = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    action_type = models.CharField(max_length=80, blank=True)
    related_model = models.CharField(max_length=80, blank=True)
    related_object_id = models.PositiveIntegerField(null=True, blank=True)
    related_transaction_ids = models.JSONField(default=list, blank=True)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.ACTIVE)
    metadata = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["status", "-severity", "-estimated_saving", "title"]

    def __str__(self):
        return self.title


class ExchangeRateSnapshot(models.Model):
    base_currency = models.CharField(max_length=3)
    target_currency = models.CharField(max_length=3, default="IDR")
    rate = models.DecimalField(max_digits=20, decimal_places=8)
    provider = models.CharField(max_length=120, default="ExchangeRate-API Open Access")
    provider_url = models.URLField(blank=True)
    time_last_update = models.DateTimeField(null=True, blank=True)
    time_next_update = models.DateTimeField(null=True, blank=True)
    fetched_at = models.DateTimeField(default=timezone.now)
    raw_response = models.JSONField(default=dict, blank=True)

    class Meta:
        ordering = ["-fetched_at"]
        indexes = [
            models.Index(fields=["base_currency", "target_currency", "-fetched_at"]),
        ]

    def __str__(self):
        return f"{self.base_currency}/{self.target_currency} {self.rate}"


class CurrencyConversionCheck(models.Model):
    source_currency = models.CharField(max_length=3)
    source_amount = models.DecimalField(max_digits=20, decimal_places=4)
    idr_rate = models.DecimalField(max_digits=20, decimal_places=8)
    converted_idr_amount = models.DecimalField(max_digits=20, decimal_places=2)
    checked_at = models.DateTimeField(default=timezone.now)
    provider = models.CharField(max_length=120, default="ExchangeRate-API Open Access")
    rate_is_stale = models.BooleanField(default=False)
    snapshot = models.ForeignKey(
        ExchangeRateSnapshot,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="conversion_checks",
    )

    class Meta:
        ordering = ["-checked_at"]
        indexes = [
            models.Index(fields=["source_currency", "-checked_at"]),
        ]

    def __str__(self):
        return f"{self.source_amount} {self.source_currency} = {self.converted_idr_amount} IDR"


class InvestmentTransaction(models.Model):
    class Kind(models.TextChoices):
        BUY = "buy", "Buy"
        SELL = "sell", "Sell"
        DIVIDEND = "dividend", "Dividend"
        FEE = "fee", "Fee"
        SPLIT = "split", "Split"

    class Status(models.TextChoices):
        CONFIRMED = "confirmed", "Confirmed"
        DELETED = "deleted", "Deleted"

    date = models.DateField(default=timezone.localdate)
    kind = models.CharField(max_length=20, choices=Kind.choices)
    account = models.ForeignKey(InvestmentAccount, on_delete=models.PROTECT, related_name="investment_transactions")
    instrument = models.ForeignKey(Instrument, on_delete=models.PROTECT, related_name="investment_transactions")
    quantity = models.DecimalField(max_digits=20, decimal_places=4, default=0)
    price = models.DecimalField(max_digits=20, decimal_places=4, default=0)
    fee_amount = models.DecimalField(max_digits=20, decimal_places=2, default=0)
    cash_amount = models.DecimalField(max_digits=20, decimal_places=2, default=0)
    currency = models.CharField(max_length=3, default="IDR")
    note = models.CharField(max_length=255, blank=True)
    source = models.CharField(max_length=20, choices=Transaction.Source.choices, default=Transaction.Source.WEB)
    source_user_id = models.CharField(max_length=80, blank=True)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.CONFIRMED)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-date", "-created_at"]
        indexes = [
            models.Index(fields=["date", "kind", "status"]),
            models.Index(fields=["instrument", "status"]),
        ]

    def __str__(self):
        return f"{self.date} {self.kind} {self.instrument.symbol}"


class PriceSnapshot(models.Model):
    instrument = models.ForeignKey(Instrument, on_delete=models.CASCADE, related_name="price_snapshots")
    price = models.DecimalField(max_digits=20, decimal_places=4)
    currency = models.CharField(max_length=3, default="IDR")
    provider = models.CharField(max_length=80, default="Manual")
    fetched_at = models.DateTimeField(default=timezone.now)
    is_stale = models.BooleanField(default=False)
    raw_response = models.JSONField(default=dict, blank=True)

    class Meta:
        ordering = ["-fetched_at"]
        indexes = [
            models.Index(fields=["instrument", "-fetched_at"]),
        ]

    def __str__(self):
        return f"{self.instrument.symbol} {self.price} {self.currency}"


class AllocationTarget(models.Model):
    asset_class = models.CharField(max_length=30, choices=Instrument.AssetClass.choices, unique=True)
    target_percent = models.DecimalField(max_digits=5, decimal_places=2)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["asset_class"]

    def __str__(self):
        return f"{self.get_asset_class_display()} {self.target_percent}%"


class FinancialFreedomProfile(models.Model):
    class RiskProfile(models.TextChoices):
        CONSERVATIVE = "conservative", "Conservative"
        BALANCED = "balanced", "Balanced"
        AGGRESSIVE = "aggressive", "Aggressive"

    name = models.CharField(max_length=80, default="Default", unique=True)
    annual_expense = models.DecimalField(max_digits=20, decimal_places=2, default=0)
    fire_multiplier = models.DecimalField(max_digits=6, decimal_places=2, default=25)
    target_monthly_contribution = models.DecimalField(max_digits=20, decimal_places=2, default=0)
    emergency_fund_months = models.DecimalField(max_digits=5, decimal_places=2, default=6)
    risk_profile = models.CharField(max_length=20, choices=RiskProfile.choices, default=RiskProfile.BALANCED)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["name"]

    def __str__(self):
        return self.name


class InvestmentInsight(models.Model):
    class Severity(models.TextChoices):
        INFO = "info", "Info"
        WARNING = "warning", "Warning"
        CRITICAL = "critical", "Critical"

    class Status(models.TextChoices):
        ACTIVE = "active", "Active"
        IGNORED = "ignored", "Ignored"
        DONE = "done", "Done"

    fingerprint = models.CharField(max_length=160, unique=True)
    type = models.CharField(max_length=60)
    severity = models.CharField(max_length=20, choices=Severity.choices, default=Severity.INFO)
    title = models.CharField(max_length=160)
    reason = models.TextField()
    estimated_amount = models.DecimalField(max_digits=20, decimal_places=2, default=0)
    action_type = models.CharField(max_length=80, blank=True)
    related_model = models.CharField(max_length=80, blank=True)
    related_object_id = models.PositiveIntegerField(null=True, blank=True)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.ACTIVE)
    metadata = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["status", "-severity", "-estimated_amount", "title"]

    def __str__(self):
        return self.title
