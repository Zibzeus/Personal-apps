# Generated manually for the initial Money Manager schema.
import django.db.models.deletion
import django.utils.timezone
from django.db import migrations, models


class Migration(migrations.Migration):
    initial = True

    dependencies = []

    operations = [
        migrations.CreateModel(
            name="Account",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("name", models.CharField(max_length=80, unique=True)),
                (
                    "type",
                    models.CharField(
                        choices=[
                            ("cash", "Cash"),
                            ("bank", "Bank"),
                            ("e_wallet", "E-wallet"),
                            ("credit", "Credit"),
                            ("savings", "Savings"),
                        ],
                        default="cash",
                        max_length=20,
                    ),
                ),
                ("opening_balance", models.DecimalField(decimal_places=2, default=0, max_digits=14)),
                ("is_active", models.BooleanField(default=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
            ],
            options={"ordering": ["name"]},
        ),
        migrations.CreateModel(
            name="Category",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("name", models.CharField(max_length=80)),
                ("type", models.CharField(choices=[("income", "Income"), ("expense", "Expense")], max_length=20)),
                ("is_fixed", models.BooleanField(default=False)),
                ("is_discretionary", models.BooleanField(default=False)),
                ("keywords", models.CharField(blank=True, max_length=255)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
            ],
            options={"ordering": ["type", "name"]},
        ),
        migrations.CreateModel(
            name="Debt",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("direction", models.CharField(choices=[("payable", "Payable"), ("receivable", "Receivable")], max_length=20)),
                ("counterparty", models.CharField(max_length=120)),
                ("principal_amount", models.DecimalField(decimal_places=2, max_digits=14)),
                ("current_balance", models.DecimalField(decimal_places=2, max_digits=14)),
                ("due_date", models.DateField(blank=True, null=True)),
                ("note", models.CharField(blank=True, max_length=255)),
                ("status", models.CharField(choices=[("open", "Open"), ("closed", "Closed")], default="open", max_length=20)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
            ],
            options={"ordering": ["status", "due_date", "counterparty"]},
        ),
        migrations.CreateModel(
            name="Recommendation",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("fingerprint", models.CharField(max_length=160, unique=True)),
                ("generated_for_month", models.DateField()),
                ("type", models.CharField(max_length=60)),
                (
                    "severity",
                    models.CharField(
                        choices=[("info", "Info"), ("warning", "Warning"), ("critical", "Critical")],
                        default="info",
                        max_length=20,
                    ),
                ),
                ("title", models.CharField(max_length=160)),
                ("reason", models.TextField()),
                ("estimated_saving", models.DecimalField(decimal_places=2, default=0, max_digits=14)),
                ("action_type", models.CharField(blank=True, max_length=80)),
                ("related_model", models.CharField(blank=True, max_length=80)),
                ("related_object_id", models.PositiveIntegerField(blank=True, null=True)),
                ("related_transaction_ids", models.JSONField(blank=True, default=list)),
                ("status", models.CharField(choices=[("active", "Active"), ("ignored", "Ignored"), ("done", "Done")], default="active", max_length=20)),
                ("metadata", models.JSONField(blank=True, default=dict)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
            ],
            options={"ordering": ["status", "-severity", "-estimated_saving", "title"]},
        ),
        migrations.CreateModel(
            name="SavingsGoal",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("name", models.CharField(max_length=120)),
                ("target_amount", models.DecimalField(decimal_places=2, max_digits=14)),
                ("current_amount", models.DecimalField(decimal_places=2, default=0, max_digits=14)),
                ("target_date", models.DateField(blank=True, null=True)),
                ("is_active", models.BooleanField(default=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("linked_account", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, to="finance.account")),
            ],
            options={"ordering": ["-is_active", "target_date", "name"]},
        ),
        migrations.CreateModel(
            name="Budget",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("month", models.DateField()),
                ("amount", models.DecimalField(decimal_places=2, max_digits=14)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("category", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="budgets", to="finance.category")),
            ],
            options={"ordering": ["-month", "category__name"]},
        ),
        migrations.CreateModel(
            name="RecurringRule",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("name", models.CharField(max_length=120)),
                ("kind", models.CharField(choices=[("expense", "Expense"), ("income", "Income"), ("transfer", "Transfer")], max_length=20)),
                ("amount", models.DecimalField(decimal_places=2, max_digits=14)),
                ("interval", models.CharField(choices=[("daily", "Daily"), ("weekly", "Weekly"), ("monthly", "Monthly")], default="monthly", max_length=20)),
                ("next_due", models.DateField()),
                ("prompt_before_post", models.BooleanField(default=True)),
                ("note", models.CharField(blank=True, max_length=255)),
                ("is_active", models.BooleanField(default=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("account", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="recurring_rules", to="finance.account")),
                ("category", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, to="finance.category")),
                ("to_account", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name="incoming_recurring_rules", to="finance.account")),
            ],
            options={"ordering": ["next_due", "name"]},
        ),
        migrations.CreateModel(
            name="Transaction",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("date", models.DateField(default=django.utils.timezone.localdate)),
                ("kind", models.CharField(choices=[("expense", "Expense"), ("income", "Income"), ("adjustment", "Adjustment"), ("repayment", "Repayment")], max_length=20)),
                ("amount", models.DecimalField(decimal_places=2, max_digits=14)),
                ("merchant", models.CharField(blank=True, max_length=120)),
                ("note", models.CharField(blank=True, max_length=255)),
                ("source", models.CharField(choices=[("web", "Web"), ("telegram", "Telegram"), ("system", "System")], default="web", max_length=20)),
                ("source_user_id", models.CharField(blank=True, max_length=80)),
                ("status", models.CharField(choices=[("confirmed", "Confirmed"), ("deleted", "Deleted")], default="confirmed", max_length=20)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("account", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="transactions", to="finance.account")),
                ("category", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="transactions", to="finance.category")),
                ("debt", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, to="finance.debt")),
            ],
            options={"ordering": ["-date", "-created_at"]},
        ),
        migrations.CreateModel(
            name="Transfer",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("date", models.DateField(default=django.utils.timezone.localdate)),
                ("amount", models.DecimalField(decimal_places=2, max_digits=14)),
                ("fee_amount", models.DecimalField(decimal_places=2, default=0, max_digits=14)),
                ("note", models.CharField(blank=True, max_length=255)),
                ("source", models.CharField(choices=[("web", "Web"), ("telegram", "Telegram"), ("system", "System")], default="web", max_length=20)),
                ("source_user_id", models.CharField(blank=True, max_length=80)),
                ("status", models.CharField(choices=[("confirmed", "Confirmed"), ("deleted", "Deleted")], default="confirmed", max_length=20)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("from_account", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="outgoing_transfers", to="finance.account")),
                ("to_account", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="incoming_transfers", to="finance.account")),
            ],
            options={"ordering": ["-date", "-created_at"]},
        ),
        migrations.AddConstraint(
            model_name="category",
            constraint=models.UniqueConstraint(fields=("name", "type"), name="unique_category_name_type"),
        ),
        migrations.AddConstraint(
            model_name="budget",
            constraint=models.UniqueConstraint(fields=("month", "category"), name="unique_budget_month_category"),
        ),
        migrations.AddIndex(
            model_name="transaction",
            index=models.Index(fields=["date", "kind", "status"], name="finance_tra_date_f36d98_idx"),
        ),
        migrations.AddIndex(
            model_name="transaction",
            index=models.Index(fields=["source", "source_user_id"], name="finance_tra_source_58c028_idx"),
        ),
    ]
