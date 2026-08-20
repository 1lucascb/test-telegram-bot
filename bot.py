import os
import sys
import time
import telebot
from telebot.apihelper import ApiTelegramException

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
if not TELEGRAM_BOT_TOKEN:
    raise Exception("environment variable 'TELEGRAM_BOT_TOKEN' is not set")

bot = telebot.TeleBot(TELEGRAM_BOT_TOKEN)

try:
    bot.set_my_name("Imaculado")
except ApiTelegramException as e:
    if e.error_code == 429:
        time.sleep(e.result_json.get('parameters', {}).get('retry_after', 1))

def safe_api_call(func, *args, **kwargs):
    """Executes a bot API function and retries automatically if rate-limited."""
    max_retries = 3
    for attempt in range(max_retries):
        try:
            return func(*args, **kwargs)
        except ApiTelegramException as e:
            if e.error_code == 429:
                # Extract the wait time suggested by Telegram, default to 2 seconds
                retry_after = e.result_json.get('parameters', {}).get('retry_after', 2)
                time.sleep(retry_after)
            else:
                raise e
    return None

@bot.message_handler(commands=['repeat'])
def repeat_message(message: telebot.types.Message):
    text_to_repeat = message.text.split(' ', 1)

    if len(text_to_repeat) > 1:
        safe_api_call(bot.reply_to, message, text_to_repeat[1])
    else:
        safe_api_call(bot.reply_to, message, "Please provide a message to repeat! (e.g., /repeat Hello)")

@bot.message_handler(func=lambda message: True)
def fallback(message: telebot.types.Message):
    try:
        reaction = telebot.types.ReactionTypeEmoji("❤️")
        safe_api_call(bot.set_message_reaction, message.chat.id, message.id, [reaction])
    except Exception:
        safe_api_call(bot.reply_to, message, "Sorry, I couldn't process that.")

if __name__ == "__main__":
    bot.infinity_polling(timeout=20, long_polling_timeout=10)