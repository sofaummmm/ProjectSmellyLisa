import requests
from telegram import Update, ReplyKeyboardMarkup
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, ContextTypes, filters
from googletrans import Translator  # pip install googletrans==4.0.0-rc1

TOKEN = '7905088913:AAE1ZE8Y24DKgmdO_nRVUrqeDLoyFl8tIqk'

translator = Translator()

def get_random_word():
    try:
        word = requests.get("https://random-word-api.herokuapp.com/word").json()[0]
        return word
    except Exception:
        return None

def get_word_info(word):
    try:
        url = f"https://api.dictionaryapi.dev/api/v2/entries/en/{word}"
        resp = requests.get(url)
        if resp.status_code == 200:
            data = resp.json()
            meanings = data[0].get('meanings', [])
            definitions = []
            for meaning in meanings:
                for d in meaning.get('definitions', []):
                    definitions.append(d.get('definition', ''))
            examples = []
            for meaning in meanings:
                for d in meaning.get('definitions', []):
                    if 'example' in d:
                        examples.append(d['example'])
            return {
                'word': word,
                'meaning': definitions[0] if definitions else '',
                'example': examples[0] if examples else '',
            }
        return None
    except Exception:
        return None

def translate_text(text):
    # Переводим значение на русский язык
    try:
        result = translator.translate(text, dest="ru").text
        return result
    except Exception:
        return text  # если перевод не сработал, вернем оригинальный текст

def generate_tasks(word, meaning):
    return [
        f"Придумайте предложение с английским словом '{word}'.",
        f"Переведите это значение на русский: {meaning}",
        f"Подберите синоним к слову '{word}' (на английском)."
    ]

current_word_info = {'word': '', 'meaning': '', 'meaning_ru': '', 'example': '', 'tasks': []}

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    buttons = [
        ['Проверить задание', 'Показать ответы'],
        ['Получить слово', 'Получить задание'],
        ['Помощь']
    ]
    keyboard = ReplyKeyboardMarkup(buttons, resize_keyboard=True)
    welcome = (
        "👋 Привет! Я помогу тебе выучить новые английские слова.\n\n"
        "Нажми «Получить слово» чтобы начать, а потом попробуй задания!"
    )
    await update.message.reply_text(welcome, reply_markup=keyboard)

async def send_word(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global current_word_info
    word = get_random_word()
    if not word:
        await update.message.reply_text('Не получилось получить случайное слово. Попробуйте ещё раз.')
        return
    info = get_word_info(word)
    if not info or not info['meaning']:
        await update.message.reply_text(f"{word} — нет значения. Попробуйте получить новое слово.")
        return
    meaning_ru = translate_text(info['meaning'])
    current_word_info['word'] = info['word']
    current_word_info['meaning'] = info['meaning']
    current_word_info['meaning_ru'] = meaning_ru
    current_word_info['example'] = info['example']
    current_word_info['tasks'] = generate_tasks(info['word'], meaning_ru)

    msg = (
        f"Слово дня: {info['word']}\n"
        f"Значение: {meaning_ru}\n"
        f"Пример: {info['example']}\n"
        "Нажмите 'Получить задание', чтобы попробовать упражнения по этому слову!"
    )
    await update.message.reply_text(msg)

async def send_tasks(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global current_word_info
    if not current_word_info['word']:
        await update.message.reply_text('Сначала получите слово!')
        return
    tasks = current_word_info['tasks']
    text = "Задания:\n"
    for i, t in enumerate(tasks, 1):
        text += f"{i}. {t}\n"
    await update.message.reply_text(text)

async def check_task(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text('Проверка ответов шаблонная — если нужна автоматическая, дай знать!')

async def show_answers(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global current_word_info
    msg = "Возможные ответы:\n"
    msg += f"- Синоним к слову '{current_word_info['word']}' ищите в словаре.\n"
    msg += f"- Значение: {current_word_info['meaning_ru']}\n"
    msg += f"- Свой пример на английском."
    await update.message.reply_text(msg)

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    help_text = (
        "1. Получите слово — бот пришлет новое английское слово.\n"
        "2. Получите задания — выполните упражнения для лучшего запоминания.\n"
        "3. Можете проверить себя и посмотреть ответы.\n"
        "Учитесь каждый день, и вы заметите результат!"
    )
    await update.message.reply_text(help_text)

async def message_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.strip()
    if text == 'Проверить задание':
        await update.message.reply_text('Пожалуйста, отправьте ваши ответы на задания.')
    elif text == 'Показать ответы':
        await show_answers(update, context)
    elif text == 'Помощь':
        await help_command(update, context)
    elif text == 'Получить слово':
        await send_word(update, context)
    elif text == 'Получить задание':
        await send_tasks(update, context)
    else:
        await check_task(update, context)

def main():
    app = ApplicationBuilder().token(TOKEN).build()

    app.add_handler(CommandHandler('start', start))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, message_handler))

    app.run_polling()

if __name__ == "__main__":
    main()
