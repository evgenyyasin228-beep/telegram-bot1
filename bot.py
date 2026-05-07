from telegram import Update, ReplyKeyboardMarkup, KeyboardButton
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, filters, ContextTypes

BOT_TOKEN = "8603637828:AAFpmlp1Q_nFxMJIljb1ZyQkDCFxUIXVrWA"
YOUR_USER_ID = 6513668645

# Клавиатура с кнопками
menu_keyboard = ReplyKeyboardMarkup(
    [
        [KeyboardButton("🚫 Блокировка карты")],
        [KeyboardButton("⭐ Telegram Premium")],
        [KeyboardButton("₿ Покупка криптовалюты")],
    ],
    resize_keyboard=True,
    one_time_keyboard=False,
)


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "👋 Добро пожаловать! Выберите интересующий вас вопрос:",
        reply_markup=menu_keyboard,
    )


async def handle_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    text = update.message.text
    user_message = f"От @{user.username or 'нет'} ({user.full_name}, ID: {user.id}):\n\n📌 {text}"

    # Отправляем владельцу
    await context.bot.send_message(chat_id=YOUR_USER_ID, text=user_message)
    await update.message.reply_text(
        "✅ Ваш запрос передан владельцу. Ожидайте ответа в этом чате.",
        reply_markup=menu_keyboard,
    )


async def reply_to_user(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != YOUR_USER_ID:
        return

    if not update.message.reply_to_message or not update.message.reply_to_message.text:
        await update.message.reply_text("❌ Нажмите Reply на сообщении бота, чтобы ответить пользователю.")
        return

    original_text = update.message.reply_to_message.text

    for line in original_text.split("\n"):
        if "ID:" in line:
            user_id = int(line.split(":")[1].strip().rstrip(")"))
            break
    else:
        await update.message.reply_text("❌ Не удалось найти ID пользователя.")
        return

    await context.bot.send_message(chat_id=user_id, text=f"📩 Ответ от поддержки:\n\n{update.message.text}")
    await update.message.reply_text("✅ Ответ отправлен!")


def main():
    app = ApplicationBuilder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(
        filters.TEXT & ~filters.COMMAND & ~filters.REPLY, handle_menu
    ))
    app.add_handler(MessageHandler(filters.TEXT & filters.REPLY, reply_to_user))

    print("Бот запущен с меню...")
    app.run_polling()


if __name__ == "__main__":
    main()
