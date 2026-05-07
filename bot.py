from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, filters, ContextTypes

BOT_TOKEN = "8603637828:AAFpmlp1Q_nFxMJIljb1ZyQkDCFxUIXVrWA"
YOUR_USER_ID = 6513668645

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Привет! Я передам ваше сообщение владельцу.")

async def forward_to_owner(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    await context.bot.send_message(
        chat_id=YOUR_USER_ID,
        text=f"От @{user.username or 'нет'} ({user.full_name}, ID: {user.id}):\n\n{update.message.text}"
    )

async def reply_to_user(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != YOUR_USER_ID:
        return
    if not update.message.reply_to_message or not update.message.reply_to_message.text:
        await update.message.reply_text("Нажмите Reply на сообщении бота.")
        return
    for line in update.message.reply_to_message.text.split("\n"):
        if "ID:" in line:
            user_id = int(line.split(":")[1].strip().rstrip(")"))
            break
    else:
        await update.message.reply_text("Не удалось найти ID.")
        return
    await context.bot.send_message(chat_id=user_id, text=f"Ответ:\n\n{update.message.text}")
    await update.message.reply_text("Отправлено!")

def main():
    app = ApplicationBuilder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND & ~filters.REPLY, forward_to_owner))
    app.add_handler(MessageHandler(filters.TEXT & filters.REPLY, reply_to_user))
    print("Бот запущен...")
    app.run_polling()

if __name__ == "__main__":
    main()
