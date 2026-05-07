import os
import asyncio
from decimal import Decimal, ROUND_UP
from datetime import datetime, timedelta
from telegram import Update, ReplyKeyboardMarkup, KeyboardButton, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    ApplicationBuilder, CommandHandler, MessageHandler,
    filters, ContextTypes, CallbackQueryHandler, ConversationHandler
)
import httpx

BOT_TOKEN = "8603637828:AAFpmlp1Q_nFxMJIljb1ZyQkDCFxUIXVrWA"
YOUR_USER_ID = 6513668645
YOUR_TRC20_ADDRESS = "TBn2tgjPg3xcTYhHMrjTQYzHm4NubpXjnU"
TRONGRID_API_KEY = "774a391e-b8ef-4dc4-9cb1-fee98e53c408"

# Адрес контракта USDT (Tether) в сети TRC20
USDT_CONTRACT = "TR7NHqjeKQxGTCi8q8ZY4pL8otSzgjLj6t"

# Цены и состояния
PRICE_3_MONTH = 900
PRICE_6_MONTH = 1300
PRICE_12_MONTH = 2200
WAITING_HASH = 1
WAITING_USERNAME = 2

# Хранилища
pending_transactions = {}
completed_orders = {}
processing_hashes = set()

# Основное меню
menu_keyboard = ReplyKeyboardMarkup(
    [
        [KeyboardButton("🚫 Блокировка карты")],
        [KeyboardButton("⭐ Telegram Premium")],
    ],
    resize_keyboard=True,
    one_time_keyboard=False,
)

# Клавиатура ТОЛЬКО с кнопкой отмены (для этапа ожидания хэша)
cancel_only_keyboard = ReplyKeyboardMarkup(
    [
        [KeyboardButton("❌ Отменить платёж")],
    ],
    resize_keyboard=True,
    one_time_keyboard=False,
)


async def get_usd_rate() -> Decimal:
    """Получает текущий курс доллара ЦБ РФ"""
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            response = await client.get("https://www.cbr-xml-daily.ru/daily_json.js")
            data = response.json()
            return Decimal(str(data["Valute"]["USD"]["Value"]))
    except Exception:
        return Decimal("85.0")


async def verify_trc20_payment(tx_hash: str, expected_amount: Decimal) -> tuple:
    """Точная проверка транзакции USDT TRC20"""
    tx_hash = tx_hash.strip()
    
    if tx_hash in processing_hashes:
        return False, "⏳ Эта транзакция уже проверяется."
    
    processing_hashes.add(tx_hash)
    
    try:
        url = f"https://api.trongrid.io/v1/transactions/{tx_hash}"
        headers = {"TRON-PRO-API-KEY": TRONGRID_API_KEY}
        
        async with httpx.AsyncClient(timeout=20) as client:
            response = await client.get(url, headers=headers)
            
            if response.status_code == 404:
                return False, "❌ Транзакция не найдена."
            if response.status_code != 200:
                return False, f"⚠️ Ошибка API (код {response.status_code})"
            
            data = response.json()
            
            # Проверка статуса
            if data.get("ret", [{}])[0].get("contractRet") != "SUCCESS":
                return False, "❌ Транзакция не выполнена."
            
            # Проверка типа контракта
            contract_call = data["raw_data"]["contract"][0]
            if contract_call["type"] != "TriggerSmartContract":
                return False, "❌ Не смарт-контракт."
            
            # Проверка адреса контракта USDT
            called_contract = contract_call["parameter"]["value"]["contract_address"]
            if called_contract != USDT_CONTRACT:
                return False, "❌ Не контракт USDT."
            
            # Парсинг данных transfer(address,uint256)
            raw_data = contract_call["parameter"]["value"]["data"]
            if not raw_data.startswith("a9059cbb"):
                return False, "❌ Не метод transfer."
            
            # Извлечение адреса получателя
            to_address_hex = raw_data[8:72]
            to_address = "41" + to_address_hex[24:]
            
            # Проверка адреса получателя
            expected_hex = _base58_to_hex(YOUR_TRC20_ADDRESS)
            if to_address.lower() != expected_hex.lower():
                return False, "❌ Получатель не совпадает."
            
            # Извлечение суммы
            amount_hex = raw_data[72:136]
            raw_amount = int(amount_hex, 16)
            actual_amount = Decimal(str(raw_amount)) / Decimal(10**6)
            
            min_expected = expected_amount * Decimal("0.99")
            if actual_amount < min_expected:
                return False, f"❌ Недостаточно. Получено: {actual_amount} USDT, нужно: {expected_amount} USDT."
            
            return True, f"✅ Платёж подтверждён: {actual_amount} USDT"
    
    except Exception as e:
        return False, f"❌ Ошибка: {str(e)}"
    finally:
        processing_hashes.discard(tx_hash)


def _base58_to_hex(address: str) -> str:
    """Конвертирует Base58 адрес в HEX"""
    try:
        import base58
        decoded = base58.b58decode_check(address)
        return decoded.hex()
    except:
        return ""


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Стартовое сообщение с главным меню"""
    await update.message.reply_text(
        "👋 Добро пожаловать! Выберите интересующий вас вопрос:",
        reply_markup=menu_keyboard,
    )


async def handle_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик главного меню"""
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
    elif text == "❌ Отменить платёж":
        # Нажата кнопка отмены на этапе хэша
        await cancel_payment(update, context)
    else:
        await context.bot.send_message(
            chat_id=YOUR_USER_ID,
            text=f"От @{user.username or 'нет'} ({user.full_name}, ID: {user.id}):\n\n{text}"
        )
        await update.message.reply_text(
            "✅ Ваш запрос передан владельцу.",
            reply_markup=menu_keyboard,
        )


async def cancel_payment(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Отмена платежа и возврат в главное меню"""
    user_id = update.effective_user.id
    if user_id in pending_transactions:
        del pending_transactions[user_id]
    
    await update.message.reply_text(
        "❌ Платёж отменён. Вы вернулись в главное меню.",
        reply_markup=menu_keyboard,
    )


async def premium_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Показывает цену, адрес TRC20 и запрашивает хэш"""
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id

    tariff_map = {
        "premium_3": ("3 месяца", PRICE_3_MONTH),
        "premium_6": ("6 месяцев", PRICE_6_MONTH),
        "premium_12": ("1 год", PRICE_12_MONTH),
    }
    tariff_name, rub_price = tariff_map[query.data]
    usd_rate = await get_usd_rate()
    usdt_amount = (Decimal(str(rub_price)) / usd_rate).quantize(Decimal("0.01"), rounding=ROUND_UP)

    pending_transactions[user_id] = {
        "tariff": tariff_name,
        "rub_price": rub_price,
        "usdt_amount": usdt_amount,
    }

    # Inline-кнопка отмены под сообщением с адресом
    cancel_inline = InlineKeyboardMarkup([
        [InlineKeyboardButton("❌ Отменить заказ", callback_data="cancel_order")]
    ])

    await query.edit_message_text(
        f"💳 <b>Telegram Premium — {tariff_name}</b>\n\n"
        f"💰 Цена: <b>{rub_price} ₽</b>\n"
        f"💵 Курс ЦБ: <b>{usd_rate:.2f} ₽/$</b>\n"
        f"🪙 Сумма к оплате: <b>{usdt_amount} USDT</b>\n\n"
        f"📤 Адрес TRC20:\n<code>{YOUR_TRC20_ADDRESS}</code>\n\n"
        f"⚠️ Отправьте хэш транзакции после оплаты\n"
        f"Или нажмите кнопку ниже для отмены 👇",
        parse_mode="HTML",
        reply_markup=cancel_inline,
    )
    
    # Показываем клавиатуру с кнопкой отмены платежа
    await context.bot.send_message(
        chat_id=user_id,
        text="⏳ Ожидаю хэш транзакции...",
        reply_markup=cancel_only_keyboard,
    )
    
    return WAITING_HASH


async def cancel_order_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Отмена заказа через inline-кнопку под сообщением с адресом"""
    query = update.callback_query
    await query.answer()
    
    user_id = query.from_user.id
    if user_id in pending_transactions:
        del pending_transactions[user_id]
    
    await query.edit_message_text(
        "❌ Заказ отменён.",
        reply_markup=None,
    )
    
    # Отправляем главное меню
    await context.bot.send_message(
        chat_id=user_id,
        text="Вы вернулись в главное меню:",
        reply_markup=menu_keyboard,
    )
    
    return ConversationHandler.END


async def receive_hash(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Принимает хэш и проверяет транзакцию"""
    user = update.effective_user
    text = update.message.text.strip()
    
    # Проверка на кнопку отмены платежа
    if text == "❌ Отменить платёж":
        await cancel_payment(update, context)
        return ConversationHandler.END
    
    if user.id not in pending_transactions:
        await update.message.reply_text(
            "❌ Нет активного заказа.",
            reply_markup=menu_keyboard,
        )
        return ConversationHandler.END

    order = pending_transactions[user.id]
    status_msg = await update.message.reply_text(
        "⏳ Проверяю транзакцию в Tron...",
    )

    success, message = await verify_trc20_payment(text, order["usdt_amount"])

    if success:
        order_id = f"ORD{int(datetime.now().timestamp())}"
        completed_orders[order_id] = {
            "customer_id": user.id,
            "tariff": order["tariff"],
            "usdt_amount": order["usdt_amount"],
            "hash": text,
            "username": None,
        }

        await context.bot.send_message(
            chat_id=YOUR_USER_ID,
            text=f"💰 <b>Новый платёж!</b>\n\n"
                 f"📦 Заказ: {order_id}\n"
                 f"⭐ Тариф: {order['tariff']}\n"
                 f"🪙 Сумма: {order['usdt_amount']} USDT\n"
                 f"👤 Покупатель: @{user.username or 'нет'} (ID: {user.id})\n"
                 f"🔗 Хэш: <code>{text}</code>\n\n"
                 f"Ожидаю username для подарка.",
            parse_mode="HTML",
        )

        await status_msg.edit_text(
            f"{message}\n\nВведите @username получателя Premium:",
        )
        
        # Возвращаем главное меню (без кнопки отмены)
        await update.message.reply_text(
            "Введите username:",
            reply_markup=menu_keyboard,
        )
        
        context.user_data["current_order_id"] = order_id
        return WAITING_USERNAME
    else:
        await status_msg.edit_text(
            f"{message}\n\nПроверьте хэш и отправьте снова.",
        )
        # Оставляем кнопку отмены платежа
        await update.message.reply_text(
            "Отправьте хэш ещё раз:",
            reply_markup=cancel_only_keyboard,
        )
        return WAITING_HASH


async def receive_username(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Принимает username для подарка"""
    user = update.effective_user
    text = update.message.text.strip()
    
    # Проверка на кнопку отмены (на всякий случай)
    if text == "❌ Отменить платёж":
        await cancel_payment(update, context)
        return ConversationHandler.END
    
    order_id = context.user_data.get("current_order_id")

    if not order_id or order_id not in completed_orders:
        await update.message.reply_text(
            "❌ Заказ не найден.",
            reply_markup=menu_keyboard,
        )
        return ConversationHandler.END

    username = text
    completed_orders[order_id]["username"] = username

    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("✅ Заказ выполнен", callback_data=f"complete_{order_id}")]
    ])

    await context.bot.send_message(
        chat_id=YOUR_USER_ID,
        text=f"📦 <b>Заказ {order_id} готов</b>\n\n"
             f"⭐ Тариф: {completed_orders[order_id]['tariff']}\n"
             f"🎁 Кому: {username}\n\n"
             f"Нажмите кнопку после отправки подарка 👇",
        reply_markup=keyboard,
        parse_mode="HTML",
    )

    await update.message.reply_text(
        "✅ Premium будет подарен в ближайшее время.",
        reply_markup=menu_keyboard,
    )

    del pending_transactions[user.id]
    del context.user_data["current_order_id"]
    return ConversationHandler.END


async def complete_order(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обрабатывает 'Заказ выполнен' от вас"""
    query = update.callback_query
    await query.answer()

    if query.from_user.id != YOUR_USER_ID:
        return

    order_id = query.data.replace("complete_", "")
    order = completed_orders.get(order_id)

    if not order:
        await query.edit_message_text("❌ Заказ не найден.")
        return

    await context.bot.send_message(
        chat_id=order["customer_id"],
        text=f"🎉 <b>Premium подарен!</b>\n\n"
             f"⭐ Тариф: {order['tariff']}\n"
             f"🎁 Получатель: {order['username']}\n\n"
             f"Спасибо за покупку!",
        parse_mode="HTML",
    )

    await query.edit_message_text(
        f"✅ Заказ {order_id} выполнен!\n\n"
        f"Premium подарен пользователю {order['username']}.",
        parse_mode="HTML",
    )


async def reply_to_user(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Ответ владельца пользователю"""
    if update.effective_user.id != YOUR_USER_ID:
        return

    if not update.message.reply_to_message or not update.message.reply_to_message.text:
        await update.message.reply_text("❌ Нажмите Reply на сообщении бота.")
        return

    original_text = update.message.reply_to_message.text
    for line in original_text.split("\n"):
        if "ID:" in line:
            user_id = int(line.split(":")[1].strip().rstrip(")"))
            break
    else:
        await update.message.reply_text("❌ Не удалось найти ID.")
        return

    await context.bot.send_message(chat_id=user_id, text=f"📩 Ответ:\n\n{update.message.text}")
    await update.message.reply_text("✅ Ответ отправлен!")


def main():
    app = ApplicationBuilder().token(BOT_TOKEN).build()

    conv_handler = ConversationHandler(
        entry_points=[CallbackQueryHandler(premium_callback, pattern="^premium_")],
        states={
            WAITING_HASH: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, receive_hash),
                CallbackQueryHandler(cancel_order_callback, pattern="^cancel_order$"),
            ],
            WAITING_USERNAME: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, receive_username),
            ],
        },
        fallbacks=[
            MessageHandler(filters.Regex("^❌ Отменить платёж$"), cancel_payment),
        ],
    )

    app.add_handler(CommandHandler("start", start))
    app.add_handler(conv_handler)
    app.add_handler(CallbackQueryHandler(complete_order, pattern="^complete_"))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND & ~filters.REPLY, handle_menu))
    app.add_handler(MessageHandler(filters.TEXT & filters.REPLY, reply_to_user))

    print("Бот запущен...")
    app.run_polling()


if __name__ == "__main__":
    main()
