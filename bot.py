import telebot
import requests
from datetime import datetime
from telebot.types import ReplyKeyboardMarkup, KeyboardButton


TOKEN = "YOUR-TOKEN-CODE"
bot = telebot.TeleBot(TOKEN)

CRYPTO_LIST = ['BTC', 'ETH', 'SOL', 'BNB', 'XRP', 'ADA', 'DOGE']

def get_crypto_keyboard():
    markup = ReplyKeyboardMarkup(resize_keyboard=True, row_width=3)
    buttons = [KeyboardButton(crypto) for crypto in CRYPTO_LIST]
    markup.add(*buttons)
    markup.add(KeyboardButton("Обновить все"))
    return markup

@bot.message_handler(commands=['start'])
def start(message):
    welcome_text =(
        "Салам! 👋\n"
        "Я показываю актуальные цены популярных криптовалют в USDT.\n\n"
        "Нажми на любую монету ниже или напиши /kurs"
    )
    bot.reply_to(message, welcome_text, reply_markup=get_crypto_keyboard())

@bot.message_handler(func=lambda message: True)
def handle_tex(message):
    text = message.text.strip().upper()

    if text in CRYPTO_LIST:
        show_single_crypto(message, text)
    elif text == "ОБНОВИТЬ ВСЕ":
        show_all_crypto(message)
    else:
        bot.reply_to(message, "Выбери монету из кнопок или напиши /start")

def show_single_crypto(message, symbol):
    try:
        url = f"https://api.binance.com/api/v3/ticker/price?symbol={symbol}USDT"
        resp = requests.get(url, timeout=6)
        resp.raise_for_status()

        data = resp.json()
        price = float(data['price'])

        now = datetime.now().strftime("%H:%M:%S")

        text = (
            f"📈 {symbol}/USDT\n"
            f"Цена: {price:,.2f} $\n"
            f"Обновлено: {now}\n\n"
            "Выбери другую монету или «Обновить все»"
        )

        bot.reply_to(message, text, reply_markup=get_crypto_keyboard())

    except requests.exceptions.RequestException as e:
        bot.reply_to(message, f"Не удалось взять цену {symbol}\nОшибка: {str(e)[:80]}...")
    except Exception as e:
        bot.reply_to(message, f"Неожиданная ошибка при {symbol}: {str(e)[:80]}...")


def show_all_crypto(message):
    try:
        lines = ["📊 Цены в USDT (Binance):\n"]
        now = datetime.now().strftime("%H:%M")

        for symbol in CRYPTO_LIST:
            url = f"https://api.binance.com/api/v3/ticker/price?symbol={symbol}USDT"
            resp = requests.get(url, timeout=5)

            if resp.status_code == 200:
                price = float(resp.json()['price'])
                lines.append(f"{symbol:<6} {price:>12,.2f} $")
            else:
                lines.append(f"{symbol:<6} — ошибка загрузки")
        
        lines.append(f"\nОбновлено: {now}")
        lines.append("\nНажми на монету для детального вида")

        full_text = "\n".join(lines)
        bot.reply_to(message, full_text, reply_markup=get_crypto_keyboard())
    
    except Exception as e:
        bot.reply(message, f"Не удалось обновить все цены\n{str(e)[:100]}...")


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

print("Бот запущен... ждём сообщений")
bot.infinity_polling()
