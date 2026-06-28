from django.urls import path

from . import views


app_name = "finance"

urlpatterns = [
    path("", views.dashboard, name="dashboard"),
    path("accounts/", views.accounts, name="accounts"),
    path("categories/", views.categories, name="categories"),
    path("transactions/", views.transactions, name="transactions"),
    path("transfers/", views.transfers, name="transfers"),
    path("investments/", views.investment_dashboard, name="investments"),
    path("investments/accounts/", views.investment_accounts, name="investment_accounts"),
    path("investments/instruments/", views.investment_instruments, name="investment_instruments"),
    path("investments/instruments/<int:pk>/price/", views.investment_price, name="investment_price"),
    path("investments/transactions/", views.investment_transactions, name="investment_transactions"),
    path("financial-freedom/", views.financial_freedom, name="financial_freedom"),
    path("financial-freedom/allocation-targets/", views.allocation_targets, name="allocation_targets"),
    path("watchlist/", views.watchlist, name="watchlist"),
    path("budgets/", views.budgets, name="budgets"),
    path("debts/", views.debts, name="debts"),
    path("debts/<int:pk>/repay/", views.debt_repay, name="debt_repay"),
    path("currency/", views.currency, name="currency"),
    path("recurring/", views.recurring, name="recurring"),
    path("savings/", views.savings_goals, name="savings"),
    path("recommendations/<int:pk>/", views.recommendation_action, name="recommendation_action"),
    path("export.csv", views.export_csv, name="export_csv"),
    path("backup/", views.backup_database, name="backup"),
]
