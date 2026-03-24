import telebot
import requests
import threading
import time
from datetime import datetime, timedelta
from telebot.types import ReplyKeyboardMarkup, KeyboardButton, InlineKeyboardMarkup, InlineKeyboardButton

TOKEN = "YOUR TOKEN"
bot = telebot.TeleBot(TOKEN)

CRYPTO_LIST = ['BTC', 'ETH', 'SOL', 'BNB', 'XRP', 'ADA', 'DOGE']

price_cache = {}
CACHE_TTL = 60

# === АЛЕРТЫ ===
# Структура: {user_id: [{"symbol": "BTC", "threshold": 65000.0, "direction": "ниже", "alerted": False}, ...]}
user_alerts = {}

def get_crypto_keyboard():
    markup = ReplyKeyboardMarkup(resize_keyboard=True, row_width=3)
    buttons = [KeyboardButton(crypto) for crypto in CRYPTO_LIST]
    markup.add(*buttons)
    markup.add(KeyboardButton("Обновить все"))
    return markup

def get_coin_inline_keyboard(symbol):
    markup = InlineKeyboardMarkup(row_width=4)

    btn_1h  = InlineKeyboardButton("1ч",  callback_data=f"time_{symbol}_1")
    btn_6h  = InlineKeyboardButton("6ч",  callback_data=f"time_{symbol}_6")
    btn_12h = InlineKeyboardButton("12ч", callback_data=f"time_{symbol}_12")
    btn_24h = InlineKeyboardButton("24ч", callback_data=f"time_{symbol}_24")

    btn_graph = InlineKeyboardButton(
        text="📊 График", 
        url=f"https://www.tradingview.com/symbols/{symbol}USDT/" 
    )

    markup.add(btn_1h, btn_6h, btn_12h, btn_24h)
    markup.add(btn_graph)
    return markup

def get_crypto_data(symbol):
    now = datetime.now()
    
    # Кэш
    if symbol in price_cache:
        cached = price_cache[symbol]
        if (now - cached["timestamp"]) < timedelta(seconds=CACHE_TTL):
            return (
                cached["price"],
                cached["change24"],
                cached.get("high24", None),
                cached.get("low24", None),
                cached.get("volume24", None),
                True
            )
    
    try:
        url = f"https://api.binance.com/api/v3/ticker/24hr?symbol={symbol}USDT"
        resp = requests.get(url, timeout=6)
        
        print(f"[{symbol}] Status: {resp.status_code}, URL: {url}")
        
        resp.raise_for_status()
        
        data = resp.json()
        
        print(f"[{symbol}] Тип data: {type(data)}")
        
        ticker = data
        
        if "lastPrice" not in ticker or "priceChangePercent" not in ticker:
            raise KeyError(f"Нет нужных ключей. Доступные: {list(ticker.keys())}")
        
        price = float(ticker["lastPrice"])
        change24 = float(ticker["priceChangePercent"])
        high24 = float(ticker.get("highPrice", 0))
        low24 = float(ticker.get("lowPrice", 0))
        volume24 = float(ticker.get("quoteVolume", 0))
        
        price_cache[symbol] = {
            "price": price,
            "change24": change24,
            "high24": high24,
            "low24": low24,
            "volume24": volume24,
            "timestamp": now
        }
        
        return price, change24, high24, low24, volume24, False
    
    except Exception as e:
        print(f"Ошибка загрузки {symbol}: {type(e).__name__}: {str(e)}")
        if 'resp' in locals():
            print(f"Ответ сервера (первые 300 символов): {resp.text[:300]}...")
        return None, None, None, None, None, False

def get_price_change_for_period(symbol, hours):
    try:
        # Binance Kline API: interval = 1h, количество свечей = hours + 1
        interval = "1h"
        limit = hours + 1   # берём на 1 свечу больше, чтобы посчитать изменение
        
        url = f"https://api.binance.com/api/v3/klines?symbol={symbol}USDT&interval={interval}&limit={limit}"
        resp = requests.get(url, timeout=8)
        resp.raise_for_status()
        
        data = resp.json()
        
        if len(data) < 2:
            return None, None, None
        
        # data[-1] — самая новая свеча
        # data[0]  — самая старая свеча за период
        old_price = float(data[0][4])      # цена закрытия первой свечи
        current_price = float(data[-1][4]) # цена закрытия последней свечи
        
        if old_price == 0:
            return current_price, 0.0, f"{hours}ч"
        
        change_percent = ((current_price - old_price) / old_price) * 100
        
        return current_price, round(change_percent, 2), f"{hours}ч"
        
    except Exception as e:
        print(f"Ошибка получения изменения за {hours}ч для {symbol}: {e}")
        return None, None, None

@bot.message_handler(commands=['start'])
def start(message):
    welcome_text =(
        "Салам! 👋\n"
        "Я показываю актуальные цены популярных криптовалют в USDT.\n\n"
        "Нажми на любую монету ниже или напиши /kurs"
    )
    bot.reply_to(message, welcome_text, reply_markup=get_crypto_keyboard())

@bot.message_handler(commands=['myalerts'])
def my_alerts(message):
    user_id = message.chat.id
    alerts = user_alerts.get(user_id, [])

    if not alerts:
        bot.reply_to(message, "У тебя пока нет активных алертов.\n\nНапиши например:\n`BTC 65000`\nили\n`ETH ниже 2100`")
        return
    
    text = "📌 Твои алерты:\n\n"
    for i, alert in enumerate(alerts):
        text += f"{i+1}. {alert['symbol']} {alert['direction']} {alert['threshold']:,.2f} $\n"

    text += "\nЧтобы удалить алерт — напиши `/delete 1` (номер алерта)"
    bot.reply_to(message, text)

@bot.message_handler(commands=['delete'])
def delete_alert(message):
    user_id = message.chat.id
    alerts = user_alerts.get(user_id, [])

    try:
        # Берём число после /delete
        index = int(message.text.split()[1]) - 1 # пользователь пишет 1, а индекс начинается с 0
        if 0 <= index < len(alerts):
            deleted = alerts.pop(index)
            bot.reply_to(message, f"✅ Алерт удалён:\n{deleted['symbol']} {deleted['direction']} {deleted['threshold']:,.2f} $")

            # Если алертов больше нет — удаляем пользователя полностью
            if not alerts:
                del user_alerts[user_id]
        else:
            bot.reply_to(message, "Неверный номер алерта.")
    except:
        bot.reply_to(message, "Использование: `/delete 1` (укажи номер алерта из /myalerts)")

@bot.message_handler(commands=['clearalerts'])
def clear_alerts(message):
    user_id = message.chat.id
    if user_id in user_alerts:
        del user_alerts[user_id]
        bot.reply_to(message, "✅ Все алерты удалены.")
    else:
        bot.reply_to(message, "У тебя и так нет алертов.")

@bot.message_handler(func=lambda message: True)
def handle_text(message):
    text = message.text.strip().upper()

    if len(text.split()) >= 2 and text[0].isalpha():
        try:
            parts = message.text.split() # используем оригинальный текст, чтобы сохранить регистр
            symbol = parts[0].upper()
            rest = " ".join(parts[1:]).lower()

            if "ниже" in rest or "below" in rest or "<" in rest:
                direction = "ниже"
                threshold_str = rest.replace("ниже", "").replace("below", "").replace("<", "").strip()
            elif "выше" in rest or "above" in rest or ">" in rest:
                direction = "выше"
                threshold_str = rest.replace("выше", "").replace("above", "").replace(">", "").strip()
            else:
                direction = "ниже" if "<" in rest or "ниже" in rest else "выше"
                threshold_str = rest.replace("ниже", "").replace("выше", "").strip()
            
            threshold = float(threshold_str)

            user_id = message.chat.id
            if user_id not in user_alerts:
                user_alerts[user_id] = []
            
            # Добавляем алерт
            user_alerts[user_id].append({
                "symbol": symbol,
                "threshold": threshold,
                "direction": direction,
                "alerted": False
            })
            
            bot.reply_to(message, f"✅ Алерт создан!\n{symbol} {direction} {threshold:,.2f} $")
            return  # выходим, чтобы не обрабатывать как обычную кнопку
        except:
            pass  # если не получилось распарсить — продолжаем как раньше

    if text in CRYPTO_LIST:
        show_single_crypto(message, text)
    elif text == "ОБНОВИТЬ ВСЕ":
        show_all_crypto(message)
    else:
        bot.reply_to(message, "Выбери монету из кнопок или напиши /start")


def show_single_crypto(message, symbol):
    price, change24, high24, low24, volume24, from_cache = get_crypto_data(symbol)
    
    if price is None:
        text = f"❌ Не удалось загрузить {symbol}USDT\nПопробуй позже"
        bot.reply_to(message, text, reply_markup=get_crypto_keyboard())
        return
    
    # Стрелка и эмодзи для 24ч
    if change24 > 0:
        arrow = "↑"
        emoji = "🟢"
        change_text = f"+{change24:.2f}%"
    elif change24 < 0:
        arrow = "↓"
        emoji = "🔴"
        change_text = f"{change24:.2f}%"
    else:
        arrow = "→"
        emoji = "⚪"
        change_text = "0.00%"
    
    source = "Binance"
    cache_note = " (кэш)" if from_cache else ""
    now = datetime.now().strftime("%H:%M:%S")
    
    text = (
        f"**📈 {symbol}/USDT**\n\n"
        f"**Текущая цена:** {price:,.2f} $\n"
        f"**Изменение 24ч:** {emoji} {arrow} {change_text}\n"
        f"**Макс 24ч:** {high24:,.2f} $\n"
        f"**Мин 24ч:**  {low24:,.2f} $\n"
        f"**Объём 24ч:** {volume24:,.0f} $\n\n"
        f"_Обновлено: {now}{cache_note}_ • Источник: Binance\n\n"
        "Нажми кнопку ниже для графика или обновления"
    )

    inline_markup = get_coin_inline_keyboard(symbol)
    
    bot.reply_to(message, text, parse_mode="Markdown", reply_markup=inline_markup)


def show_all_crypto(message):
    try:
        lines = ["📊 Цены в USDT (Binance) — 24ч изменения\n"]
        now = datetime.now().strftime("%d.%m %H:%M")

        for symbol in CRYPTO_LIST:
            price, change24, high24, low24, volume24, from_cache = get_crypto_data(symbol)

            if price is not None:
                if change24 > 0:
                    arrow_emoji = "↑🟢"
                    change_str = f"+{change24:.2f}%"
                elif change24 < 0:
                    arrow_emoji = "↓🔴"
                    change_str = f"{change24:.2f}%"
                else:
                    arrow_emoji = "→⚪"
                    change_str = "0.00%"
                
                lines.append(
                    f"{symbol:<6} {price:>12,.2f} $   {arrow_emoji} {change_str}"
                )
            else:
                lines.append(f"{symbol:<6} — ошибка загрузки")
        
        lines.append(f"\nОбновлено: {now}")
        lines.append("\nНажми на монету для детального вида")

        full_text = "\n".join(lines)
        bot.reply_to(message, full_text, reply_markup=get_crypto_keyboard())
    
    except Exception as e:
        bot.reply_to(message, f"Не удалось обновить все цены\n{str(e)[:100]}...")


@bot.message_handler(commands=['kurs'])
def show_kurs(message):
    try:
        response = requests.get("https://api.binance.com/api/v3/ticker/price?symbol=BTCUSDT")

        data = response.json()

        btc_price = float(data['price'])

        text = f"₿ BTC/USDT сейчас: {btc_price:,.0f} $"

        bot.reply_to(message, text)

    except Exception as e:
        bot.reply_to(message, f"Не получилось взять курс 😅\nОшибка: {str(e)}\nПопробуй позже")

def check_alerts():
    while True:
        time.sleep(60) # Пауза 60 секунд между проверками

        # Проходим по всем пользователям и их алертам
        # list(user_alerts.items()) — чтобы можно было изменять словарь во время цикла
        for user_id, alerts in list(user_alerts.items()):
            remaining_alerts = []
            for alert in alerts:
                if alert.get("alerted", False):
                    continue
                
                # Получаем текущую цену монеты
                price, _, _, _, _, _ = get_crypto_data(alert["symbol"])

                # Если цену не удалось взять — пропускаем этот алерт
                if price is None:
                    continue

                threshold = alert['threshold']
                direction = alert["direction"]
                triggered = False

                # Проверяем, сработал ли алерт
                triggered = False
                if direction == "ниже" and price <= threshold:
                    triggered = True
                elif direction == "выше" and price >= threshold:
                    triggered = True

                if triggered:
                    text = (
                        f"🚨 АЛЕРТ СРАБОТАЛ!\n\n"
                        f"{alert['symbol']} сейчас {price:,.2f} $\n"
                        f"Твой порог: {direction} {threshold:,.2f} $\n\n"
                        f"Время: {datetime.now().strftime('%H:%M:%S')}"
                    )
                    try:
                        bot.send_message(user_id, text, parse_mode="Markdown")
                        alert['alerted'] = True # Помечаем — больше не спамим
                    except Exception as send_error:
                        print(f"Ошибка отправки алерта пользователю {user_id}: {send_error}")
                        remaining_alerts.append(alert)
                    
                else:
                    remaining_alerts.append(alert)
                
            if remaining_alerts:
                user_alerts[user_id] = remaining_alerts
            else:
                if user_id in user_alerts:
                    del user_alerts[user_id]

@bot.callback_query_handler(func=lambda call: True)
def callback_handler(call):
    """Обрабатывает все нажатия на inline-кнопки"""
    try:
        data = call.data
        
        if data.startswith("time_"):
            _, symbol, hours_str = data.split("_")
            hours = int(hours_str)
            
            # Обновляем сообщение с новым периодом
            update_price_message(call.message, symbol, hours)
            
            # Убираем ожидание на кнопке
            bot.answer_callback_query(call.id, f"Обновлено за {hours}ч")
            
        elif data.startswith("refresh_"):
            # Пока просто обновляем за 24ч при нажатии "Обновить"
            _, symbol = data.split("_")
            update_price_message(call.message, symbol, 24)
            bot.answer_callback_query(call.id, "Обновлено")
            
    except Exception as e:
        print(f"Ошибка callback: {e}")
        bot.answer_callback_query(call.id, "Ошибка 😅")

def update_price_message(message, symbol, hours):
    """Обновляет сообщение с % изменением за выбранный период"""
    current_price, change_percent, period_text = get_price_change_for_period(symbol, hours)
    
    if current_price is None:
        bot.answer_callback_query(call.id, "Не удалось получить данные 😅")
        return
    
    # Определяем стрелку и цвет
    if change_percent > 0:
        arrow = "↑"
        emoji = "🟢"
        change_text = f"+{change_percent:.2f}%"
    elif change_percent < 0:
        arrow = "↓"
        emoji = "🔴"
        change_text = f"{change_percent:.2f}%"
    else:
        arrow = "→"
        emoji = "⚪"
        change_text = "0.00%"
    
    now = datetime.now().strftime("%H:%M:%S")
    
    text = (
        f"**📈 {symbol}/USDT**\n\n"
        f"**Текущая цена:** {current_price:,.2f} $\n"
        f"**Изменение за {period_text}:** {emoji} {arrow} {change_text}\n\n"
        f"_Обновлено: {now}_ • Источник: Binance\n\n"
        "Выбери период ниже:"
    )
    
    try:
        bot.edit_message_text(
            text=text,
            chat_id=message.chat.id,
            message_id=message.message_id,
            parse_mode="Markdown",
            reply_markup=get_coin_inline_keyboard(symbol)
        )
    except Exception as e:
        print(f"Ошибка редактирования сообщения: {e}")

# Запускаем проверку алертов в отдельном потоке
# daemon=True — чтобы поток закрылся вместе с ботом
threading.Thread(target=check_alerts, daemon=True).start()

print("Бот запущен... ждём сообщений")
print("Фоновая проверка алертов запущена (каждые 60 сек)")
bot.infinity_polling()
