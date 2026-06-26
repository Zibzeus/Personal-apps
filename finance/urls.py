from django.urls import path

from . import views


app_name = "finance"

urlpatterns = [
    path("", views.dashboard, name="dashboard"),
    path("accounts/", views.accounts, name="accounts"),
    path("categories/", views.categories, name="categories"),
    path("transactions/", views.transactions, name="transactions"),
    path("transfers/", views.transfers, name="transfers"),
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
