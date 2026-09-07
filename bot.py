"""
Telegram-бот: показывает клиентов (сделки Bitrix24) на заданной стадии,
позволяет любому сотруднику открыть карточку клиента, увидеть все
заметки, оставленные коллегами, и добавить свою.

Запуск:
    python bot.py
Настройки — в файле .env (см. .env.example)
"""

import os
import logging

from dotenv import load_dotenv
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import (
    Application,
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
)

import bitrix
import storage

load_dotenv()

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger(__name__)

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
DEAL_STAGE_ID = os.getenv("DEAL_STAGE_ID", "")
DEAL_CATEGORY_ID = os.getenv("DEAL_CATEGORY_ID")  # опционально

# ключ user_data, хранящий id сделки, для которой сейчас ждём текст заметки
AWAITING_NOTE_KEY = "awaiting_note_for_deal_id"


def _deal_title(deal: dict) -> str:
    title = deal.get("TITLE") or f"Сделка №{deal.get('ID')}"
    amount = deal.get("OPPORTUNITY")
    if amount and float(amount) > 0:
        currency = deal.get("CURRENCY_ID", "")
        title += f" — {amount} {currency}"
    return title


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    context.user_data.pop(AWAITING_NOTE_KEY, None)
    keyboard = InlineKeyboardMarkup(
        [[InlineKeyboardButton("📋 Показать клиентов на стадии", callback_data="show_deals")]]
    )
    await update.message.reply_text(
        "Привет! Я показываю клиентов из Bitrix24 на нужной стадии "
        "и веду общие заметки по каждому — их видят все сотрудники.",
        reply_markup=keyboard,
    )


async def show_deals(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()
    context.user_data.pop(AWAITING_NOTE_KEY, None)

    if not DEAL_STAGE_ID:
        await query.edit_message_text("⚠️ DEAL_STAGE_ID не задан в .env")
        return

    try:
        deals = bitrix.get_deals_by_stage(DEAL_STAGE_ID, DEAL_CATEGORY_ID)
    except Exception as e:
        log.exception("Ошибка запроса к Bitrix24")
        await query.edit_message_text(f"⚠️ Не удалось получить данные из Bitrix24:\n{e}")
        return

    if not deals:
        await query.edit_message_text("На этой стадии сейчас нет сделок.")
        return

    buttons = [
        [InlineKeyboardButton(_deal_title(d), callback_data=f"deal:{d['ID']}")]
        for d in deals
    ]
    await query.edit_message_text(
        f"Клиенты на стадии (найдено {len(deals)}):",
        reply_markup=InlineKeyboardMarkup(buttons),
    )


async def show_deal_card(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()
    context.user_data.pop(AWAITING_NOTE_KEY, None)

    deal_id = int(query.data.split(":", 1)[1])

    try:
        deal = bitrix.get_deal(deal_id)
    except Exception as e:
        await query.edit_message_text(f"⚠️ Не удалось загрузить сделку: {e}")
        return

    contact_name = bitrix.get_contact_name(deal.get("CONTACT_ID"))
    notes = storage.get_notes(deal_id)

    lines = [f"👤 <b>{_deal_title(deal)}</b>"]
    if contact_name:
        lines.append(f"Контакт: {contact_name}")
    lines.append("")

    if notes:
        lines.append("📝 <b>Заметки:</b>")
        for author, text, created_at in notes:
            lines.append(f"• <i>{author}, {created_at}</i>:\n{text}")
    else:
        lines.append("Заметок пока нет.")

    keyboard = InlineKeyboardMarkup(
        [
            [InlineKeyboardButton("✏️ Добавить заметку", callback_data=f"addnote:{deal_id}")],
            [InlineKeyboardButton("⬅️ К списку клиентов", callback_data="show_deals")],
        ]
    )
    await query.edit_message_text("\n".join(lines), reply_markup=keyboard, parse_mode="HTML")


async def ask_for_note(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()

    deal_id = int(query.data.split(":", 1)[1])
    context.user_data[AWAITING_NOTE_KEY] = deal_id

    keyboard = InlineKeyboardMarkup(
        [[InlineKeyboardButton("⬅️ Отмена", callback_data=f"deal:{deal_id}")]]
    )
    await query.edit_message_text(
        "Напишите текст заметки следующим сообщением — я прикреплю её к этому клиенту.",
        reply_markup=keyboard,
    )


async def receive_note_text(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    deal_id = context.user_data.get(AWAITING_NOTE_KEY)
    if not deal_id:
        return  # обычное сообщение вне сценария добавления заметки — игнорируем

    user = update.effective_user
    author_name = user.full_name or user.username or str(user.id)
    text = update.message.text.strip()

    if not text:
        await update.message.reply_text("Заметка не может быть пустой. Напишите текст ещё раз.")
        return

    storage.add_note(deal_id, author_name, user.id, text)
    context.user_data.pop(AWAITING_NOTE_KEY, None)

    try:
        deal = bitrix.get_deal(deal_id)
        title = _deal_title(deal)
    except Exception:
        title = f"сделке №{deal_id}"

    keyboard = InlineKeyboardMarkup(
        [
            [InlineKeyboardButton("✏️ Ещё заметка", callback_data=f"addnote:{deal_id}")],
            [InlineKeyboardButton("⬅️ К списку клиентов", callback_data="show_deals")],
        ]
    )
    await update.message.reply_text(
        f"✅ Заметка добавлена к «{title}». Её увидят все сотрудники, открывшие эту карточку.",
        reply_markup=keyboard,
    )


def main() -> None:
    if not TELEGRAM_BOT_TOKEN:
        raise SystemExit("TELEGRAM_BOT_TOKEN не задан в .env")

    storage.init_db()

    app = Application.builder().token(TELEGRAM_BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CallbackQueryHandler(show_deals, pattern="^show_deals$"))
    app.add_handler(CallbackQueryHandler(show_deal_card, pattern=r"^deal:\d+$"))
    app.add_handler(CallbackQueryHandler(ask_for_note, pattern=r"^addnote:\d+$"))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, receive_note_text))

    log.info("Бот запущен")
    app.run_polling()


if __name__ == "__main__":
    main()
