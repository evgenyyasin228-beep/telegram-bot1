import os
import asyncio
from decimal import Decimal, ROUND_UP
from telegram import Update, ReplyKeyboardMarkup, KeyboardButton, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, filters, ContextTypes, CallbackQueryHandler
import httpx

BOT_TOKEN = "8603637828:AAFpmlp1Q_nFxMJIljb1ZyQkDCFxUIXVrWA"
YOUR_USER_ID = 6513668645
YOUR_TRC20_ADDRESS = "TBn2tgjPg3xcTYhHMrjTQYzHm4NubpXjnU"

# Цены на тарифы в рублях
PRICE_3_MONTH = 900
PRICE_6_MONTH = 1300
PRICE_12_MONTH = 2200

# Основное меню
menu_keyboard = ReplyKeyboardMarkup(
    [
        [KeyboardButton("🚫 Блокировка карты")],
        [KeyboardButton("⭐ Telegram Premium")],
    ],
    resize_keyboard=True,
    one_time_keyboard=False,
)


async def get_usd_rate() -> Decimal:
    """Получает текущий курс доллара ЦБ РФ"""
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            response = await client.get(
                "https://www.cbr-xml-daily.ru/daily_json.js"
            )
            data = response.json()
            return Decimal(str(data["Valute"]["USD"]["Value"]))
    except Exception:
        # Резервный курс, если не удалось получить
        return Decimal("85.0")


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "👋 Добро пожаловать! Выберите интересующий вас вопрос:",
        reply_markup=menu_keyboard,
    )


async def handle_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    text = update.message.text

    if text == "🚫 Блокировка карты":
        await update.message.reply_text(
            "📝 Напишите ваш вопрос ниже, владелец постарается ответить как можно быстрее.",
            reply_markup=menu_keyboard,
        )
    elif text == "⭐ Telegram Premium":
        keyboard = [
            [InlineKeyboardButton("3 месяца — 900₽", callback_data="premium_3")],
            [InlineKeyboardButton("6 месяцев — 1300₽", callback_data="premium_6")],
            [InlineKeyboardButton("1 год — 2200₽", callback_data="premium_12")],
        ]
        await update.message.reply_text(
            "⭐ Выберите тариф Telegram Premium:",
            reply_markup=InlineKeyboardMarkup(keyboard),
        )
    else:
        # Любое другое сообщение — пересылается владельцу
        await context.bot.send_message(
            chat_id=YOUR_USER_ID,
            text=f"От @{user.username or 'нет'} ({user.full_name}, ID: {user.id}):\n\n{text}"
        )
        await update.message.reply_text(
            "✅ Ваш запрос передан владельцу. Ожидайте ответа в этом чате.",
            reply_markup=menu_keyboard,
        )


async def premium_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработка выбора тарифа Premium"""
    query = update.callback_query
    await query.answer()

    tariff_map = {
        "premium_3": ("3 месяца", PRICE_3_MONTH),
        "premium_6": ("6 месяцев", PRICE_6_MONTH),
        "premium_12": ("1 год", PRICE_12_MONTH),
    }

    tariff_name, rub_price = tariff_map.get(query.data, ("неизвестно", 0))

    # Получаем курс ЦБ
    usd_rate = await get_usd_rate()
    usdt_amount = (Decimal(str(rub_price)) / usd_rate).quantize(
        Decimal("0.01"), rounding=ROUND_UP
    )

    await query.edit_message_text(
        f"💳 <b>Telegram Premium — {tariff_name}</b>\n\n"
        f"💰 Цена: <b>{rub_price} ₽</b>\n"
        f"💵 Курс ЦБ: <b>{usd_rate:.2f} ₽/$</b>\n"
        f"🪙 Сумма к оплате в USDT TRC20: <b>{usdt_amount} USDT</b>\n\n"
        f"📤 Адрес для оплаты:\n<code>{YOUR_TRC20_ADDRESS}</code>\n\n"
        f"⚠️ Сеть: <b>TRC20 (Tron)</b>\n"
        f"Отправьте точную сумму. После получения средств подписка будет оформлена.",
        parse_mode="HTML",
    )


async def reply_to_user(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != YOUR_USER_ID:
        return

    if not update.message.reply_to_message or not update.message.reply_to_message.text:
        await update.message.reply_text(
            "❌ Нажмите Reply на сообщении бота, чтобы ответить пользователю."
        )
        return

    original_text = update.message.reply_to_message.text
    for line in original_text.split("\n"):
        if "ID:" in line:
            user_id = int(line.split(":")[1].strip().rstrip(")"))
            break
    else:
        await update.message.reply_text("❌ Не удалось найти ID пользователя.")
        return

    await context.bot.send_message(
        chat_id=user_id,
        text=f"📩 Ответ от поддержки:\n\n{update.message.text}",
    )
    await update.message.reply_text("✅ Ответ отправлен!")


def main():
    app = ApplicationBuilder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CallbackQueryHandler(premium_callback, pattern="^premium_"))
    app.add_handler(
        MessageHandler(
            filters.TEXT & ~filters.COMMAND & ~filters.REPLY, handle_menu
        )
    )
    app.add_handler(MessageHandler(filters.TEXT & filters.REPLY, reply_to_user))

    print("Бот запущен с Premium-расчётами...")
    app.run_polling()


if __name__ == "__main__":
    main()
