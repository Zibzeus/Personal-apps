from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

from finance.formatting import format_idr
from finance.parser import parse_message
from finance.services import (
    latest_telegram_item,
    monthly_summary,
    parsed_entry_summary,
    record_parsed_entry,
    soft_delete_item,
)


class Command(BaseCommand):
    help = "Run the Telegram bot with long polling."

    def handle(self, *args, **options):
        if not settings.TELEGRAM_BOT_TOKEN:
            raise CommandError("TELEGRAM_BOT_TOKEN is empty. Fill .env first.")
        if not settings.TELEGRAM_ALLOWED_USER_IDS:
            raise CommandError("TELEGRAM_ALLOWED_USER_IDS is empty. Fill .env first.")
        try:
            from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
            from telegram.ext import Application, CallbackQueryHandler, CommandHandler, ContextTypes, MessageHandler, filters
        except ImportError as exc:
            raise CommandError("python-telegram-bot is not installed. Run scripts/setup.ps1 first.") from exc

        allowed = set(settings.TELEGRAM_ALLOWED_USER_IDS)
        pending = {}
        wizard = {}

        def is_allowed(update: Update) -> bool:
            user = update.effective_user
            return bool(user and str(user.id) in allowed)

        async def reject(update: Update):
            if update.effective_message:
                await update.effective_message.reply_text("User Telegram ini belum diizinkan.")

        async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
            if not is_allowed(update):
                await reject(update)
                return
            keyboard = InlineKeyboardMarkup(
                [
                    [
                        InlineKeyboardButton("Expense", callback_data="wizard:expense"),
                        InlineKeyboardButton("Income", callback_data="wizard:income"),
                    ],
                    [
                        InlineKeyboardButton("Transfer", callback_data="wizard:transfer"),
                        InlineKeyboardButton("Report", callback_data="report"),
                    ],
                    [
                        InlineKeyboardButton("Undo last", callback_data="undo"),
                    ],
                ]
            )
            await update.message.reply_text(
                "Money Manager aktif.\n"
                "Contoh: makan 35000 bca, gaji 15000000 bca, tf bca ovo 200000, utang ke budi 100000.",
                reply_markup=keyboard,
            )

        async def help_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
            if not is_allowed(update):
                await reject(update)
                return
            await update.message.reply_text(
                "Command:\n"
                "/report - ringkasan bulan ini\n"
                "/undo - hapus item Telegram terakhir\n\n"
                "Input bebas:\n"
                "makan 35000 bca\n"
                "gaji 15000000 bca\n"
                "tf bca ovo 200000\n"
                "utang ke budi 100000"
            )

        async def report(update: Update, context: ContextTypes.DEFAULT_TYPE):
            if not is_allowed(update):
                await reject(update)
                return
            summary = monthly_summary()
            await update.effective_message.reply_text(
                f"Bulan ini\nIncome: {format_idr(summary['income'])}\n"
                f"Expense: {format_idr(summary['expense'])}\n"
                f"Net: {format_idr(summary['net'])}\n"
                f"Saving rate: {summary['saving_rate'] * 100:.1f}%"
            )

        async def undo(update: Update, context: ContextTypes.DEFAULT_TYPE):
            if not is_allowed(update):
                await reject(update)
                return
            user_id = str(update.effective_user.id)
            item = latest_telegram_item(user_id)
            if not item:
                await update.effective_message.reply_text("Belum ada item Telegram yang bisa di-undo.")
                return
            soft_delete_item(item)
            await update.effective_message.reply_text("Item terakhir sudah dihapus dari laporan.")

        async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
            if not is_allowed(update):
                await reject(update)
                return
            user_id = str(update.effective_user.id)
            text = update.message.text.strip()
            mode = wizard.pop(user_id, "")
            if mode and mode in {"expense", "income"}:
                text = f"{mode} {text}"
            parsed = parse_message(text)
            pending[user_id] = parsed
            keyboard = InlineKeyboardMarkup(
                [
                    [
                        InlineKeyboardButton("Confirm", callback_data="confirm"),
                        InlineKeyboardButton("Cancel", callback_data="cancel"),
                    ],
                    [InlineKeyboardButton("Edit", callback_data="edit")],
                ]
            )
            await update.message.reply_text(parsed_entry_summary(parsed), reply_markup=keyboard)

        async def callbacks(update: Update, context: ContextTypes.DEFAULT_TYPE):
            if not is_allowed(update):
                await reject(update)
                return
            query = update.callback_query
            await query.answer()
            user_id = str(update.effective_user.id)
            data = query.data
            if data.startswith("wizard:"):
                mode = data.split(":", 1)[1]
                wizard[user_id] = mode
                examples = {
                    "expense": "Ketik: makan 35000 bca",
                    "income": "Ketik: gaji 15000000 bca",
                    "transfer": "Ketik: tf bca ovo 200000",
                }
                await query.edit_message_text(examples.get(mode, "Ketik transaksi."))
                return
            if data == "report":
                await report(update, context)
                return
            if data == "undo":
                await undo(update, context)
                return
            if data == "cancel":
                pending.pop(user_id, None)
                await query.edit_message_text("Dibatalkan.")
                return
            if data == "edit":
                await query.edit_message_text("Kirim ulang transaksi dengan format yang benar.")
                return
            if data == "confirm":
                parsed = pending.pop(user_id, None)
                if not parsed:
                    await query.edit_message_text("Tidak ada transaksi pending.")
                    return
                try:
                    item = record_parsed_entry(parsed, source_user_id=user_id)
                except Exception as exc:
                    await query.edit_message_text(f"Gagal simpan: {exc}")
                    return
                await query.edit_message_text(f"Tersimpan: {item}")

        app = Application.builder().token(settings.TELEGRAM_BOT_TOKEN).build()
        app.add_handler(CommandHandler("start", start))
        app.add_handler(CommandHandler("help", help_cmd))
        app.add_handler(CommandHandler("report", report))
        app.add_handler(CommandHandler("undo", undo))
        app.add_handler(CallbackQueryHandler(callbacks))
        app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))

        self.stdout.write(self.style.SUCCESS("Telegram bot polling started."))
        app.run_polling()
