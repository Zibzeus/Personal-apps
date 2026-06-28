from datetime import date
from decimal import Decimal, InvalidOperation

from django import forms
from django.core.exceptions import ValidationError
from django.utils import timezone

from .models import (
    Account,
    AllocationTarget,
    Budget,
    Category,
    Debt,
    FinancialFreedomProfile,
    Instrument,
    InvestmentAccount,
    InvestmentTransaction,
    PriceSnapshot,
    RecurringRule,
    SavingsGoal,
    Transaction,
    Transfer,
)


class DateInput(forms.DateInput):
    input_type = "date"


class GroupedDecimalField(forms.DecimalField):
    default_error_messages = {
        "invalid": "Masukkan nominal angka, contoh: 35000 atau 35.000.",
        "scientific": "Jangan pakai format e/scientific notation. Gunakan angka biasa, contoh: 100000.",
    }

    def to_python(self, value):
        if value in self.empty_values:
            return None
        raw = str(value).strip()
        if "e" in raw.lower():
            raise ValidationError(self.error_messages["scientific"], code="scientific")
        cleaned = raw.lower().replace("rp", "").replace(" ", "")
        cleaned = cleaned.replace("_", "")
        if "," in cleaned and "." in cleaned:
            cleaned = cleaned.replace(".", "").replace(",", ".")
        elif "," in cleaned:
            parts = cleaned.split(",")
            if len(parts[-1]) == 3 and all(part.isdigit() for part in parts):
                cleaned = "".join(parts)
            else:
                cleaned = cleaned.replace(",", ".")
        elif "." in cleaned:
            parts = cleaned.split(".")
            if all(part.isdigit() for part in parts) and all(len(part) == 3 for part in parts[1:]):
                cleaned = "".join(parts)
        try:
            return Decimal(cleaned)
        except (InvalidOperation, ValueError):
            raise ValidationError(self.error_messages["invalid"], code="invalid")


class RupiahDecimalField(GroupedDecimalField):
    default_error_messages = {
        "invalid": "Masukkan nominal Rupiah, contoh: 35000 atau 35.000.",
        "scientific": "Jangan pakai format e/scientific notation. Gunakan angka biasa, contoh: 100000.",
    }


def apply_field_style(fields):
    for name, field in list(fields.items()):
        if isinstance(field, forms.DecimalField) and not isinstance(field, GroupedDecimalField):
            fields[name] = RupiahDecimalField(
                required=field.required,
                max_digits=field.max_digits,
                decimal_places=field.decimal_places,
                min_value=field.min_value,
                max_value=field.max_value,
                label=field.label,
                help_text=field.help_text,
                initial=field.initial,
            )
            field = fields[name]
        if isinstance(field, RupiahDecimalField):
            field.widget = forms.TextInput()
            field.widget.attrs.update(
                {
                    "data-rupiah-input": "true",
                    "inputmode": "numeric",
                    "autocomplete": "off",
                    "placeholder": "Rp0",
                    "pattern": "[0-9RrPp., ]+",
                }
            )
        elif isinstance(field, GroupedDecimalField):
            field.widget = forms.TextInput()
            field.widget.attrs.update(
                {
                    "inputmode": "decimal",
                    "autocomplete": "off",
                    "placeholder": "100",
                    "pattern": "[0-9., ]+",
                }
            )
        field.widget.attrs.setdefault("class", "field-input")


class BaseStyledForm(forms.ModelForm):
    grouped_decimal_fields = set()

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for name in self.grouped_decimal_fields:
            field = self.fields.get(name)
            if isinstance(field, forms.DecimalField):
                self.fields[name] = GroupedDecimalField(
                    required=field.required,
                    max_digits=field.max_digits,
                    decimal_places=field.decimal_places,
                    min_value=field.min_value,
                    max_value=field.max_value,
                    label=field.label,
                    help_text=field.help_text,
                    initial=field.initial,
                )
        apply_field_style(self.fields)


class AccountForm(BaseStyledForm):
    class Meta:
        model = Account
        fields = ["name", "type", "opening_balance", "is_active"]


class CategoryForm(BaseStyledForm):
    class Meta:
        model = Category
        fields = ["name", "type", "is_fixed", "is_discretionary", "keywords"]


class TransactionForm(BaseStyledForm):
    class Meta:
        model = Transaction
        fields = ["date", "kind", "account", "category", "amount", "merchant", "note", "debt", "source"]
        widgets = {"date": DateInput()}


class TransferForm(BaseStyledForm):
    class Meta:
        model = Transfer
        fields = ["date", "from_account", "to_account", "amount", "fee_amount", "note", "source"]
        widgets = {"date": DateInput()}


class InstrumentForm(BaseStyledForm):
    grouped_decimal_fields = {"lot_size"}

    class Meta:
        model = Instrument
        fields = [
            "symbol",
            "provider_symbol",
            "name",
            "market",
            "currency",
            "asset_class",
            "lot_size",
            "is_active",
            "is_watchlisted",
            "watch_note",
        ]

    def clean_symbol(self):
        return self.cleaned_data["symbol"].strip().upper()

    def clean_provider_symbol(self):
        return self.cleaned_data["provider_symbol"].strip().upper()

    def clean_currency(self):
        return self.cleaned_data["currency"].strip().upper()


class InvestmentAccountForm(BaseStyledForm):
    class Meta:
        model = InvestmentAccount
        fields = ["name", "platform", "currency", "linked_cash_account", "is_active"]

    def clean_currency(self):
        return self.cleaned_data["currency"].strip().upper()


class InvestmentTransactionForm(BaseStyledForm):
    grouped_decimal_fields = {"quantity", "price", "fee_amount", "cash_amount"}

    class Meta:
        model = InvestmentTransaction
        fields = [
            "date",
            "kind",
            "account",
            "instrument",
            "quantity",
            "price",
            "fee_amount",
            "cash_amount",
            "currency",
            "note",
            "source",
        ]
        widgets = {"date": DateInput()}

    def clean_currency(self):
        return self.cleaned_data["currency"].strip().upper()


class PriceSnapshotForm(BaseStyledForm):
    grouped_decimal_fields = {"price"}

    class Meta:
        model = PriceSnapshot
        fields = ["price", "currency", "provider", "is_stale"]

    def __init__(self, *args, instrument=None, **kwargs):
        self.instrument = instrument
        super().__init__(*args, **kwargs)
        if instrument and not self.initial.get("currency"):
            self.fields["currency"].initial = instrument.currency
        self.fields["provider"].initial = self.fields["provider"].initial or "Manual"

    def clean_currency(self):
        return self.cleaned_data["currency"].strip().upper()

    def save(self, commit=True):
        snapshot = super().save(commit=False)
        if self.instrument:
            snapshot.instrument = self.instrument
        if commit:
            snapshot.save()
        return snapshot


class AllocationTargetForm(BaseStyledForm):
    grouped_decimal_fields = {"target_percent"}

    class Meta:
        model = AllocationTarget
        fields = ["asset_class", "target_percent"]


class FinancialFreedomProfileForm(BaseStyledForm):
    grouped_decimal_fields = {"fire_multiplier", "emergency_fund_months"}

    class Meta:
        model = FinancialFreedomProfile
        fields = [
            "annual_expense",
            "fire_multiplier",
            "target_monthly_contribution",
            "emergency_fund_months",
            "risk_profile",
        ]


class BudgetForm(BaseStyledForm):
    class Meta:
        model = Budget
        fields = ["month", "category", "amount"]
        widgets = {"month": DateInput()}

    def clean_month(self):
        value = self.cleaned_data["month"]
        return date(value.year, value.month, 1)


class DebtForm(BaseStyledForm):
    class Meta:
        model = Debt
        fields = ["direction", "counterparty", "principal_amount", "current_balance", "due_date", "note"]
        widgets = {"due_date": DateInput()}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.instance and self.instance.pk:
            self.fields["current_balance"].disabled = True
            self.fields["current_balance"].required = False
            self.fields["current_balance"].help_text = "Balance otomatis berubah lewat Record Payment."
            self.fields["current_balance"].widget.attrs["readonly"] = "readonly"
        else:
            self.fields.pop("current_balance", None)

    def save(self, commit=True):
        is_new = not self.instance.pk
        debt = super().save(commit=False)
        if is_new:
            debt.current_balance = debt.principal_amount
            debt.status = Debt.Status.OPEN
        if commit:
            debt.save()
            self.save_m2m()
        return debt


class DebtRepaymentForm(forms.Form):
    account = forms.ModelChoiceField(queryset=Account.objects.none())
    amount = RupiahDecimalField(max_digits=14, decimal_places=2, min_value=Decimal("0.01"), label="Payment amount")
    date = forms.DateField(initial=timezone.localdate, widget=DateInput())
    note = forms.CharField(required=False, max_length=255, widget=forms.TextInput())

    def __init__(self, *args, debt=None, **kwargs):
        self.debt = debt
        super().__init__(*args, **kwargs)
        self.fields["account"].queryset = Account.objects.filter(is_active=True)
        if debt:
            self.fields["amount"].help_text = f"Current balance: Rp{int(debt.current_balance):,}".replace(",", ".")
        apply_field_style(self.fields)


class CurrencyConversionForm(forms.Form):
    currency = forms.CharField(max_length=3, min_length=3, label="Source currency")
    amount = GroupedDecimalField(max_digits=20, decimal_places=4, min_value=Decimal("0.0001"), label="Source amount")

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["currency"].widget.attrs.update(
            {
                "class": "field-input",
                "autocomplete": "off",
                "placeholder": "USD",
                "spellcheck": "false",
            }
        )
        apply_field_style(self.fields)

    def clean_currency(self):
        return self.cleaned_data["currency"].strip().upper()


class RecurringRuleForm(BaseStyledForm):
    class Meta:
        model = RecurringRule
        fields = [
            "name",
            "kind",
            "account",
            "to_account",
            "category",
            "amount",
            "interval",
            "next_due",
            "prompt_before_post",
            "note",
            "is_active",
        ]
        widgets = {"next_due": DateInput()}


class SavingsGoalForm(BaseStyledForm):
    class Meta:
        model = SavingsGoal
        fields = ["name", "target_amount", "current_amount", "target_date", "linked_account", "is_active"]
        widgets = {"target_date": DateInput()}
