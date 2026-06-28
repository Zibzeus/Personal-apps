# Money Manager Lokal

Aplikasi money manager pribadi yang berjalan di laptop Windows. Input utama lewat Telegram bot, dashboard lokal di browser, dan audit finansial rule-based untuk mencari area pengeluaran yang bisa dikurangi.

## Fitur

- Telegram bot dengan input bebas dan tombol konfirmasi.
- Dashboard lokal di `http://127.0.0.1:8000`.
- Grafik cashflow, kategori pengeluaran, spending harian, saldo akun, budget, dan saving rate.
- CRUD akun, kategori, transaksi, transfer, budget, recurring, hutang/piutang, dan savings goal.
- Debt repayment otomatis mengurangi current balance dan menutup debt saat sudah Rp0.
- Kurs check di `/currency/` untuk konversi mata uang asing ke Rupiah, dengan history tersimpan untuk audit/forecasting.
- Investment portfolio di `/investments/` dengan holdings, market value, cost basis, gain/loss, allocation, watchlist, manual/API price cache.
- Financial freedom/FIRE planner di `/financial-freedom/` dengan FIRE number, net worth, gap, runway, dan simulasi kontribusi bulanan.
- Financial Coach di `/coach/` untuk monthly audit, bocor halus, action list, subscription candidates, goal routing, dan cashflow forecast.
- Monthly audit di `/monthly-audit/` dengan close/reopen/recalculate dan tampilan print-friendly untuk Save as PDF dari browser.
- Subscription center di `/subscriptions/` untuk confirmed subscription dan auto-detected recurring candidates.
- Cashflow forecast di `/forecast/` untuk proyeksi saldo harian 90 hari dan checkpoint 30/60/90 hari.
- Financial goals di `/goals/` untuk dana darurat, debt payoff, FIRE, dan target tabungan prioritas.
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

Market data investasi local-first. Manual price selalu bisa dipakai. Untuk API gratis opsional:

```env
MARKET_DATA_PROVIDER=auto
ALPHA_VANTAGE_API_KEY=
```

`yfinance` juga didukung kalau kamu install sendiri di environment lokal. Kalau API gagal, app memakai cached/manual price terakhir dan menandainya stale.

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
- `buy bbca 10 lot 10000 ajaib`
- `sell bbca 2 lot 11000`
- `dividend bbca 150000`
- `price bbca 10500`

Semua input penting akan diminta konfirmasi sebelum masuk database.

## Financial Coach

Alur rekomendasi v1 bersifat review-first:

1. Tambahkan transaksi dan recurring/subscription seperti biasa.
2. Buat goal prioritas di `/goals/`, misalnya dana darurat atau debt payoff.
3. Buka `/coach/` untuk melihat action list dan forecast.
4. Buka `/monthly-audit/` untuk close bulan, recalculate jika ada koreksi, lalu print/save as PDF dari browser.
5. Buka `/subscriptions/` untuk confirm atau ignore recurring candidates yang terdeteksi otomatis.

Forecast tidak membuat transaksi baru. Forecast hanya simulasi dari saldo sekarang, recurring, subscription, debt due, budget reserve, dan target goal prioritas.

## Catatan

Rekomendasi adalah audit cashflow dan kebiasaan belanja, bukan rekomendasi investasi. Tidak ada bank/e-wallet auto-sync pada v1.

## Deploy Online

Untuk PythonAnywhere Free, lihat [deploy/PYTHONANYWHERE.md](deploy/PYTHONANYWHERE.md).
