# Personal Apps

Local-first personal operating system built with Django and SQLite. The project started as a Money Manager, then grew into a single local workspace for finance, productivity execution, and daily journaling.

Everything runs in one Django project, one login/session system, one SQLite database, and one local web server on port `8000`.

## Apps

- App chooser: `http://127.0.0.1:8000/`
- Money Manager: `http://127.0.0.1:8000/money/`
- Productivity: `http://127.0.0.1:8000/productivity/`
- Daily Journal: `http://127.0.0.1:8000/journal/`

## Main Features

### Money Manager

- Local finance dashboard with cashflow, account balances, saving rate, spending trends, and budget visibility.
- CRUD for accounts, categories, transactions, transfers, budgets, recurring rules, debt/receivables, and savings goals.
- Telegram parser for finance entries such as expense, income, transfer, debt, investment buy/sell/dividend, and manual prices.
- Currency checker with cached ExchangeRate-API snapshots.
- Investment portfolio with holdings, cost basis, market value, gain/loss, allocation, watchlist, and stale/manual price support.
- FIRE planner with FIRE number, runway, net worth, monthly contribution simulation, and allocation targets.
- Financial Coach for monthly audit, subscription detection, leak/spending analysis, goal routing, and 90-day cashflow forecast.
- CSV export and SQLite backup.

### Productivity

- Daily execution dashboard with quick capture, overdue tasks, planned-today tasks, and energy-based suggestions.
- Kanban board for Inbox, Next, Doing, Waiting, and Done.
- Non-financial goals and projects kept separate from finance goals.
- Weekly and monthly reviews with snapshots and current focus.
- Telegram productivity commands: `task`, `today`, `done <id>`, `goal`, and `review`.

### Daily Journal

- One journal entry per day with mood, energy, productivity, tags, and rich local editor data.
- Read mode is separate from edit mode, so past entries open like normal journal pages.
- Image attachments are stored locally under Django media storage and displayed in the read page.
- Mood analytics with heatmap, weekly trends, monthly summaries, and radar chart.

## Setup Windows

```powershell
.\scripts\setup.ps1
```

Create `.env`:

```env
DJANGO_SECRET_KEY=local-dev-secret
DJANGO_DEBUG=1
DJANGO_REQUIRE_LOGIN=1
DEFAULT_CURRENCY=IDR
```

Optional Telegram settings:

```env
TELEGRAM_BOT_TOKEN=token_dari_BotFather
TELEGRAM_ALLOWED_USER_IDS=id_telegram_kamu
TELEGRAM_BOT_ENABLED=0
```

The Telegram bot is disabled by default in `scripts/start-bot.ps1`. Set `TELEGRAM_BOT_ENABLED=1` or run `scripts/start-bot.ps1 -Force` only if you want the bot running.

If you are running from a Codex worktree but want to use the main database:

```env
SQLITE_DB_PATH=C:\Users\jalan\OneDrive\Documents\Money Manager\db.sqlite3
```

Optional market/currency settings:

```env
EXCHANGE_RATE_API_URL=https://open.er-api.com/v6/latest/{currency}
MARKET_DATA_PROVIDER=auto
ALPHA_VANTAGE_API_KEY=
```

## Run Locally

Start the web app:

```powershell
.\scripts\start-web.ps1
```

Stop the web app listener on the configured port:

```powershell
.\scripts\start-web.ps1 -Stop
```

`start-web.ps1` now clears duplicate listeners on `WEB_PORT` before starting Django. This prevents stale server processes from serving old routes/templates on `127.0.0.1:8000`.

Run Telegram bot manually:

```powershell
.\scripts\start-bot.ps1 -Force
```

Install scheduled tasks:

```powershell
.\scripts\install-task-scheduler.ps1
```

If `MoneyManagerBot` still exists in Windows Task Scheduler and you no longer use it, disable it from an Administrator PowerShell:

```powershell
schtasks /Change /TN "\MoneyManagerBot" /DISABLE
```

## Access From Android Or VM

Default web binding is local-only:

```env
WEB_HOST=127.0.0.1
WEB_PORT=8000
```

For a VM or another device on the same network:

```env
WEB_HOST=0.0.0.0
WEB_PORT=8000
DJANGO_ALLOWED_HOSTS=127.0.0.1,localhost,IP_VM_KAMU
```

Then open:

```text
http://IP_VM_KAMU:8000/
```

For HTTPS/domain/tunnel access, also configure:

```env
DJANGO_ALLOWED_HOSTS=domain-kamu.example
DJANGO_CSRF_TRUSTED_ORIGINS=https://domain-kamu.example
```

## Telegram Examples

Finance commands:

- `makan 35000 bca`
- `gaji 15000000 bca`
- `tf bca ovo 200000`
- `utang ke budi 100000`
- `piutang andi 250000`
- `buy bbca 10 lot 10000 ajaib`
- `sell bbca 2 lot 11000`
- `dividend bbca 150000`
- `price bbca 10500`

Productivity commands:

- `task follow up vendor`
- `today`
- `done 12`
- `goal lulus sertifikasi`
- `review`

Finance inputs use confirmation before writing important data. Productivity capture commands save directly for low-friction task capture.

## Validation

Run before publishing changes:

```powershell
python manage.py check
python manage.py makemigrations --check --dry-run
python manage.py test
```

## Notes

Recommendations are rule-based local audit and planning aids, not financial or investment advice. There is no bank/e-wallet auto-sync in this version.

Uploaded journal images live in local `media/` storage and are intentionally ignored by git.

## Deploy Online

For PythonAnywhere Free, see [deploy/PYTHONANYWHERE.md](deploy/PYTHONANYWHERE.md).
