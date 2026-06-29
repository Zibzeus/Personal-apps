# Changelog

This project has changed from a single-purpose Money Manager into a local personal apps workspace. This changelog groups the major product milestones from the beginning to the current state.

## 2026-06-29 - Personal Apps Expansion

### Added

- Added root app chooser at `/` for selecting Money Manager, Productivity, and Daily Journal.
- Moved Money Manager under `/money/` while keeping one Django project, one SQLite database, and one login/session system.
- Added `productivity` app at `/productivity/`.
- Added productivity models for goals, projects, tasks, weekly reviews, and monthly reviews.
- Added productivity dashboard, quick task capture, energy-based suggestions, overdue/today sections, kanban board, goal tracker, and review pages.
- Added productivity Telegram commands: `task`, `today`, `done <id>`, `goal`, and `review`.
- Added `journal` app at `/journal/`.
- Added one-entry-per-day journal model with rich editor Delta JSON, plain text search, mood score, energy score, productivity score, and tags.
- Added journal read mode separate from edit mode, so history entries open as normal reading pages.
- Added journal image attachments with local media storage.
- Added journal history, daily dashboard, mood heatmap, weekly trend, monthly summary, and radar chart analytics.
- Added local static editor support for journal writing without CDN/runtime dependency.
- Added media serving in development for journal attachments.

### Changed

- Updated shared navigation/sidebar to switch between Money Manager, Productivity, and Journal workspaces.
- Updated static chart utilities to render journal analytics.
- Updated local styling with separate workspace colors and scoped Journal styling.
- Updated `scripts/start-web.ps1` with duplicate listener cleanup and a `-Stop` mode.
- Updated `scripts/start-bot.ps1` so Telegram bot is disabled by default unless `TELEGRAM_BOT_ENABLED=1` or `-Force` is used.
- Updated tests for app chooser, productivity routes, journal models/views, journal attachments, and Telegram productivity parser.

### Operational Notes

- Existing `MoneyManagerBot` scheduled task may still exist on Windows if it was created earlier, but `start-bot.ps1` now exits without running the bot by default.
- `start-web.ps1 -Stop` can be used to kill the web server listener on `WEB_PORT`, normally `8000`.
- Journal uploads are stored in local `media/` and ignored by git.

## Previous Milestones - Financial Coach And Forecasting

### Added

- Added Financial Coach surfaces for leak audit, action list, monthly audit, subscription review, and cashflow forecast.
- Added monthly audit close/reopen/recalculate workflow.
- Added recurring/subscription candidate detection from transaction history.
- Added 90-day cashflow forecast based on current balance, recurring rules, subscriptions, debt due dates, budget reserve, and priority goals.
- Added financial goal routing for emergency fund, debt payoff, FIRE, and savings targets.

### Changed

- Expanded the finance dashboard from transaction tracking into review-first finance operations.
- Kept forecasts simulation-only so they do not create transactions.

## Previous Milestones - Investments, FIRE, And Currency

### Added

- Added investment accounts, instruments, investment transactions, price snapshots, watchlist, and manual/API price refresh.
- Added portfolio views with holdings, market value, cost basis, realized/unrealized gain, dividends, and allocation.
- Added Financial Independence/FIRE planner with FIRE number, net worth, runway, gap, contribution simulation, and allocation targets.
- Added currency conversion checks and exchange-rate snapshots.

## Previous Milestones - Core Money Manager

### Added

- Added local Django/SQLite finance app for accounts, categories, transactions, transfers, budgets, debts, recurring rules, and savings goals.
- Added local web dashboard with cashflow charts, spending categories, balance trends, and saving rate.
- Added Telegram bot parser for natural-language finance input.
- Added export CSV and local SQLite backup.
- Added login protection for the local dashboard.

## Initial Commit

- Created the base Django project and repository structure.
