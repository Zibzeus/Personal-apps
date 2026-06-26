from django.core.management.base import BaseCommand

from finance.models import Account, Category


DEFAULT_ACCOUNTS = [
    ("CASH", Account.Type.CASH),
    ("BCA", Account.Type.BANK),
    ("OVO", Account.Type.E_WALLET),
]

DEFAULT_CATEGORIES = [
    ("Makan", Category.Type.EXPENSE, False, True, "makan,food,kopi,snack,restaurant,cafe"),
    ("Groceries", Category.Type.EXPENSE, False, False, "groceries,belanja bulanan,supermarket"),
    ("Transport", Category.Type.EXPENSE, False, True, "transport,gojek,grab,bensin,tol,parkir"),
    ("Shopping", Category.Type.EXPENSE, False, True, "shopping,belanja,marketplace,tokopedia,shopee"),
    ("Entertainment", Category.Type.EXPENSE, False, True, "hiburan,cinema,game,concert"),
    ("Subscription", Category.Type.EXPENSE, True, True, "subscription,langganan,netflix,spotify,icloud"),
    ("Bills", Category.Type.EXPENSE, True, False, "listrik,internet,air,pdam,pulsa"),
    ("Rent", Category.Type.EXPENSE, True, False, "sewa,kontrakan,rent"),
    ("Health", Category.Type.EXPENSE, False, False, "health,dokter,obat,rumah sakit"),
    ("Education", Category.Type.EXPENSE, False, False, "course,buku,education,kursus"),
    ("Travel", Category.Type.EXPENSE, False, True, "travel,hotel,tiket,liburan"),
    ("Uncategorized", Category.Type.EXPENSE, False, True, ""),
    ("Salary", Category.Type.INCOME, True, False, "gaji,salary"),
    ("Bonus", Category.Type.INCOME, False, False, "bonus,thr"),
    ("Other Income", Category.Type.INCOME, False, False, "income,pemasukan,masuk"),
]


class Command(BaseCommand):
    help = "Create default accounts and categories."

    def handle(self, *args, **options):
        for name, account_type in DEFAULT_ACCOUNTS:
            Account.objects.get_or_create(name=name, defaults={"type": account_type})
        for name, category_type, is_fixed, is_discretionary, keywords in DEFAULT_CATEGORIES:
            Category.objects.update_or_create(
                name=name,
                type=category_type,
                defaults={
                    "is_fixed": is_fixed,
                    "is_discretionary": is_discretionary,
                    "keywords": keywords,
                },
            )
        self.stdout.write(self.style.SUCCESS("Default accounts and categories are ready."))

