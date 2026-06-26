# Money Manager Lokal

Aplikasi money manager pribadi yang berjalan di laptop Windows. Input utama lewat Telegram bot, dashboard lokal di browser, dan audit finansial rule-based untuk mencari area pengeluaran yang bisa dikurangi.

## Fitur

- Telegram bot dengan input bebas dan tombol konfirmasi.
- Dashboard lokal di `http://127.0.0.1:8000`.
- Grafik cashflow, kategori pengeluaran, spending harian, saldo akun, budget, dan saving rate.
- CRUD akun, kategori, transaksi, transfer, budget, recurring, hutang/piutang, dan savings goal.
- Debt repayment otomatis mengurangi current balance dan menutup debt saat sudah Rp0.
- Kurs check di `/currency/` untuk konversi mata uang asing ke Rupiah, dengan history tersimpan untuk audit/forecasting.
- Live Rupiah formatting di form nominal, contoh `12000` otomatis tampil `12.000`.
- Financial audit: over-budget, spending spike, discretionary saving opportunity, subscription review, duplikat transaksi, uncategorized, hutang jatuh tempo, dan saving rate gap.
- Export CSV dan backup SQLite lokal.

## Setup Windows

```powershell
.\scripts\setup.ps1
```

Isi `.env`:

```env
TELEGRAM_BOT_TOKEN=token_dari_BotFather
TELEGRAM_ALLOWED_USER_IDS=id_telegram_kamu
```

Kurs checker memakai ExchangeRate-API Open Access tanpa API key. Default endpoint sudah diset otomatis, tapi bisa dioverride kalau perlu:

```env
EXCHANGE_RATE_API_URL=https://open.er-api.com/v6/latest/{currency}
```

Jalankan dashboard:

```powershell
.\scripts\start-web.ps1
```

Jalankan bot Telegram:

```powershell
.\scripts\start-bot.ps1
```

Install auto-start saat login:

```powershell
.\scripts\install-task-scheduler.ps1
```

## Akses dari Android atau VM

Default dashboard hanya bind ke `127.0.0.1`, jadi aman untuk laptop lokal. Kalau dipindah ke VM dan ingin dibuka dari Android di network yang sama, isi `.env` seperti ini:

```env
WEB_HOST=0.0.0.0
WEB_PORT=8000
DJANGO_ALLOWED_HOSTS=127.0.0.1,localhost,IP_VM_KAMU
```

Lalu jalankan:

```powershell
.\scripts\start-web.ps1
```

Dari Android buka:

```text
http://IP_VM_KAMU:8000
```

Kalau akses lewat domain/tunnel HTTPS, tambahkan juga:

```env
DJANGO_ALLOWED_HOSTS=domain-kamu.example
DJANGO_CSRF_TRUSTED_ORIGINS=https://domain-kamu.example
```

## Contoh Input Telegram

- `makan 35000 bca`
- `gaji 15000000 bca`
- `tf bca ovo 200000`
- `utang ke budi 100000`
- `piutang andi 250000`

Semua input penting akan diminta konfirmasi sebelum masuk database.

## Catatan

Rekomendasi adalah audit cashflow dan kebiasaan belanja, bukan rekomendasi investasi. Tidak ada bank/e-wallet auto-sync pada v1.

## Deploy Online

Untuk PythonAnywhere Free, lihat [deploy/PYTHONANYWHERE.md](deploy/PYTHONANYWHERE.md).
