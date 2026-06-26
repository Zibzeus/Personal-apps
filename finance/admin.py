from django.contrib import admin

from .models import (
    Account,
    Budget,
    Category,
    CurrencyConversionCheck,
    Debt,
    ExchangeRateSnapshot,
    Recommendation,
    RecurringRule,
    SavingsGoal,
    Transaction,
    Transfer,
)


@admin.register(Account)
class AccountAdmin(admin.ModelAdmin):
    list_display = ("name", "type", "opening_balance", "is_active")
    list_filter = ("type", "is_active")
    search_fields = ("name",)


@admin.register(Category)
class CategoryAdmin(admin.ModelAdmin):
    list_display = ("name", "type", "is_fixed", "is_discretionary", "keywords")
    list_filter = ("type", "is_fixed", "is_discretionary")
    search_fields = ("name", "keywords")


@admin.register(Transaction)
class TransactionAdmin(admin.ModelAdmin):
    list_display = ("date", "kind", "account", "category", "amount", "source", "status")
    list_filter = ("kind", "source", "status", "category")
    search_fields = ("note", "merchant")
    date_hierarchy = "date"


admin.site.register(Transfer)
admin.site.register(Budget)
admin.site.register(Debt)
admin.site.register(RecurringRule)
admin.site.register(SavingsGoal)
admin.site.register(Recommendation)
admin.site.register(ExchangeRateSnapshot)
admin.site.register(CurrencyConversionCheck)
