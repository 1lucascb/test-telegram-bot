import os, sys, telebot

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
if not TELEGRAM_BOT_TOKEN:
    raise Exception("environment variable 'TELEGRAM_BOT_TOKEN' is not set")

bot = telebot.TeleBot(TELEGRAM_BOT_TOKEN)

bot.set_my_name("Imaculado")

@bot.message_handler()
def fallback(message: telebot.types.Message):
    try:
        bot.set_message_reaction(message.chat.id, message.id, [telebot.types.ReactionTypeEmoji("❤️")])
    except:
        bot.reply_to(message, "Sorry, I couldn't process that.")


@bot.message_handler(commands=['repeat'])
def repeat_message(message: telebot.types.Message):
    text_to_repeat = message.text.split(' ', 1)

    if len(text_to_repeat) > 1:
        bot.reply_to(message, text_to_repeat[1])
    else:
        bot.reply_to(message, "Please provide a message to repeat! (e.g., /repeat Hello)")

if __name__ == "__main__":
    bot.infinity_polling()
