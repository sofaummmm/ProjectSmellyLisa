import random
import os
from telegram import Update, ReplyKeyboardMarkup, ReplyKeyboardRemove
from telegram.ext import (
    ApplicationBuilder, CommandHandler, MessageHandler,
    ContextTypes, filters, JobQueue
)
from datetime import datetime, time, timedelta
import json

TOKEN = os.environ.get('TOKEN')
LIMIT_MODE = "ON"
LIMIT_PER_DAY = 1
USERS_FILE = 'active_users.txt'
USER_SETTINGS_FILE = 'user_settings.json'
VIRTUAL_USERS_COUNT = 53
user_words_today = {}
user_words_today_date = {}

def register_user(user_id):
    try:
        if not os.path.exists(USERS_FILE):
            with open(USERS_FILE, 'w') as f:
                pass
        with open(USERS_FILE, 'r') as f:
            users = set(u.strip() for u in f.readlines())
        if str(user_id) not in users:
            with open(USERS_FILE, 'a') as f:
                f.write(f"{user_id}\n")
        if str(user_id) not in user_settings:
            user_settings[str(user_id)] = {"remind_time": "11:00"}
            save_user_settings(user_settings)
    except Exception as e:
        print(f"Ошибка записи user_id {user_id}: {e}")

def get_total_users():
    try:
        if not os.path.exists(USERS_FILE):
            return VIRTUAL_USERS_COUNT
        with open(USERS_FILE, 'r') as f:
            users = set(u.strip() for u in f.readlines())
        return len(users) + VIRTUAL_USERS_COUNT
    except Exception as e:
        print(f"Ошибка чтения статистики пользователей: {e}")
        return VIRTUAL_USERS_COUNT

def load_user_settings():
    if not os.path.exists(USER_SETTINGS_FILE):
        return {}
    try:
        with open(USER_SETTINGS_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)
    except Exception:
        return {}

def save_user_settings(settings):
    try:
        with open(USER_SETTINGS_FILE, 'w', encoding='utf-8') as f:
            json.dump(settings, f)
    except Exception as e:
        print(f"Ошибка сохранения настроек: {e}")

user_settings = load_user_settings()

def time_from_string(tstr):
    hour, minute = map(int, tstr.split(":"))
    return time(hour=hour, minute=minute)

def load_data():
    try:
        with open('words.txt', encoding='utf-8') as f1, \
             open('meanings_en.txt', encoding='utf-8') as f2, \
             open('meanings_ru.txt', encoding='utf-8') as f3, \
             open('examples.txt', encoding='utf-8') as f4, \
             open('synonyms.txt', encoding='utf-8') as f5:
            words = f1.read().splitlines()
            meanings_en = f2.read().splitlines()
            meanings_ru = f3.read().splitlines()
            examples = f4.read().splitlines()
            synonyms = [line.split(',') for line in f5.read().splitlines()]
        all_data = [
            dict(word=w, meaning_en=me, meaning_ru=mr, example=e, synonyms=s)
            for w, me, mr, e, s in zip(words, meanings_en, meanings_ru, examples, synonyms)
        ]
        return all_data
    except Exception as e:
        print(f"Ошибка загрузки данных: {e}")
        return []

words_data = load_data()

def load_spelling_choices():
    choices_dict = {}
    try:
        with open('spelling_choices.txt', encoding='utf-8') as f:
            for line in f:
                if ':' in line:
                    word, variants = line.strip().split(':', 1)
                    options = [v.strip() for v in variants.split(',')]
                    choices_dict[word] = options
    except Exception as e:
        print(f"Ошибка чтения spelling_choices.txt: {e}")
    return choices_dict

spelling_choices = load_spelling_choices()

def get_shuffled_spelling_task(word):
    options = spelling_choices.get(word, [])
    if not options:
        return [], None
    correct = options[-1]
    shuffled = options[:]
    random.shuffle(shuffled)
    correct_index = shuffled.index(correct)
    return shuffled, correct_index

def generate_tasks(word, meaning_en):
    base_tasks = [
        f"1️⃣ Придумайте предложение с английским словом «{word}».",
        f"2️⃣ Переведите это значение на русский: {meaning_en}",
        f"3️⃣ Подберите синоним к слову «{word}».",
    ]
    if word in spelling_choices:
        options, correct_index = get_shuffled_spelling_task(word)
        if options:
            task_str = f"📝 Выберите правильное написание слова:"
            keyboard = ReplyKeyboardMarkup([[opt] for opt in options], resize_keyboard=True)
            spelling_task = (task_str, options, correct_index, keyboard)
            idx = random.randint(0, len(base_tasks))
            base_tasks.insert(idx, spelling_task)
    return base_tasks

current_word_info = {}
completed_today = []
task_position = 0

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        buttons = [
            ['Получить слово'],
            ['Настройки'],
            ['Помощь']
        ]
        keyboard = ReplyKeyboardMarkup(buttons, resize_keyboard=True)
        welcome = (
            "👋 Добро пожаловать!\n\n"
            "Здесь ты можешь выучить новые английские слова.\n"
            "Нажми «Получить слово», чтобы начать!"
        )
        await update.message.reply_text(welcome, reply_markup=keyboard)
    except Exception as e:
        print(f"Ошибка в start: {e}")

async def send_word(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global current_word_info, completed_today, task_position, user_words_today, user_words_today_date
    try:
        user_id = update.effective_user.id
        today_str = datetime.now().strftime('%Y-%m-%d')
        register_user(user_id)

        if user_words_today_date.get(user_id) != today_str:
            user_words_today[user_id] = 0
            user_words_today_date[user_id] = today_str

        if LIMIT_MODE == "ON" and user_words_today.get(user_id, 0) >= LIMIT_PER_DAY:
            await update.message.reply_text(
                "⏳ Сегодня лимит новых слов исчерпан. Вы сможете получить новое слово завтра!"
            )
            return

        info = random.choice(words_data) if words_data else None
        if info is None:
            await update.message.reply_text("База слов пуста или не загружена, обратитесь к администратору.")
            print("Пустая база слов для send_word.")
            return

        current_word_info.clear()
        current_word_info.update(info)
        if info['word'] in spelling_choices:
            options, correct_index = get_shuffled_spelling_task(info['word'])
            current_word_info['spelling_variants'] = options
            current_word_info['spelling_correct_index'] = correct_index
        else:
            current_word_info['spelling_variants'] = []
            current_word_info['spelling_correct_index'] = None
        current_word_info['tasks'] = generate_tasks(info['word'], info['meaning_en'])
        completed_today = []
        task_position = 0
        msg = (
            f"📗 <b>Слово дня:</b> <i>{info['word']}</i>\n"
            f"💬 <b>Значение:</b> <i>{info['meaning_ru']}</i>\n"
            f"✏️ <b>Пример:</b> <i>{info['example']}</i>"
        )
        await update.message.reply_text(msg, parse_mode='HTML')
        await update.message.reply_text("💡 Давай попрактикуемся! Сейчас будет задание…")
        await send_next_task(update, context)
        user_words_today[user_id] = user_words_today.get(user_id, 0) + 1
    except Exception as e:
        print(f"Ошибка send_word: {e}")

async def send_next_task(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global current_word_info, completed_today, task_position
    try:
        if ('tasks' not in current_word_info or not current_word_info['tasks']):
            await update.message.reply_text("Сначала получите слово — нажмите «Получить слово».")
            return
        tasks = current_word_info['tasks']
        if not isinstance(tasks, list) or len(tasks) == 0:
            await update.message.reply_text("Нет заданий для текущего слова. Попробуйте получить новое слово.")
            print("send_next_task: tasks пустой список!")
            return
        if task_position < len(tasks):
            t = tasks[task_position]
            if isinstance(t, tuple):
                await update.message.reply_text(f"{t[0]}", reply_markup=t[3], parse_mode='HTML')
            else:
                await update.message.reply_text(f"{t}", reply_markup=ReplyKeyboardRemove())
        else:
            await update.message.reply_text("🎉 Поздравляем, вы выполнили все задания на сегодня! Новое слово будет доступно завтра.", reply_markup=ReplyKeyboardRemove())
    except Exception as e:
        print(f"Ошибка send_next_task: {e}")

async def show_answers(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global current_word_info
    try:
        if not current_word_info:
            await update.message.reply_text("Нет активного слова или заданий! Для начала нажмите «Получить слово».")
            print("show_answers: current_word_info пустой!")
            return
        msg = "🟩 <b>Возможные ответы:</b>\n"
        msg += f"— <b>Синонимы:</b> <i>{', '.join(current_word_info.get('synonyms', []))}</i>\n"
        msg += f"— <b>Значение:</b> <i>{current_word_info.get('meaning_ru', '')}</i>\n"
        msg += f"— <b>Пример:</b> <i>{current_word_info.get('example', '')}</i>\n"
        if current_word_info.get('spelling_variants'):
            msg += f"— <b>Варианты написания:</b> <i>{', '.join(current_word_info['spelling_variants'])}</i>\n"
            if current_word_info['spelling_correct_index'] is not None:
                msg += f"— <b>Правильное написание:</b> <i>{current_word_info['spelling_variants'][current_word_info['spelling_correct_index']]}</i>\n"
        await update.message.reply_text(msg, parse_mode='HTML')
    except Exception as e:
        print(f"Ошибка show_answers: {e}")

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        help_text = (
            "📕 <b>Инструкция:</b>\n"
            "1. Получите слово — нажмите соответствующую кнопку.\n"
            "2. Выполняйте задания по очереди: после каждого ответа появится следующее!\n"
            "3. Посмотрите ответы.\n"
            "🎓 Учитесь легко и с удовольствием!"
        )
        await update.message.reply_text(help_text, parse_mode='HTML')
    except Exception as e:
        print(f"Ошибка help_command: {e}")

async def stats_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        total_users = get_total_users()
        await update.message.reply_text(
            f"🧑‍💻 Всего пользователей, заходивших в бота: <b>{total_users}</b>",
            parse_mode='HTML'
        )
        print(f"Статистика: всего пользователей {total_users}")
    except Exception as e:
        print(f"Ошибка stats_command: {e}")

# ====== ИЗМЕНЕНИЕ ЗДЕСЬ! Предупреждение о времени и смещении UTC+3 =======
async def ask_remind_time(update: Update, context: ContextTypes.DEFAULT_TYPE):
    utc_now = datetime.utcnow()
    msk_now = utc_now + timedelta(hours=3)
    await update.message.reply_text(
        f"⚠️ Внимание! Бот использует серверное время (UTC).\n"
        f"Москва (МСК) отличается на +3 часа.\n\n"
        f"Текущее время сервера: {utc_now.strftime('%H:%M')} UTC\n"
        f"Текущее время МСК: {msk_now.strftime('%H:%M')} МСК\n\n"
        "Укажите время напоминания по времени сервера (UTC).\n"
        "Например, для уведомления в 09:00 по Москве — укажите 06:00.\n"
        "Введите время в формате ЧЧ:ММ, например, 09:30, 18:00 и т.д."
    )
    context.user_data['waiting_for_remind_time'] = True

async def set_remind_time(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global user_settings
    text = update.message.text.strip()
    user_id = update.effective_user.id
    try:
        hour, minute = map(int, text.split(':'))
        if not (0 <= hour < 24 and 0 <= minute < 60):
            raise ValueError
        user_settings[str(user_id)] = user_settings.get(str(user_id), {})
        user_settings[str(user_id)]['remind_time'] = f"{hour:02d}:{minute:02d}"
        save_user_settings(user_settings)
        await update.message.reply_text(
            f"Готово! Теперь слово будет приходить каждый день в {hour:02d}:{minute:02d} (UTC).\n"
            f"Если вы хотите получать в определённое время по Москве, прибавьте 3 часа к серверному времени."
        )
        context.user_data['waiting_for_remind_time'] = False
        add_daily_reminder(context, user_id)
    except Exception:
        await update.message.reply_text("Ошибка формата времени. Наберите снова, например 09:00 или 15:45.")

# ======= run_daily: ежедневные напоминания =======
async def send_daily_word(context: ContextTypes.DEFAULT_TYPE):
    user_id = context.job.chat_id
    print(f"[DEBUG] send_daily_word вызвана для user_id: {user_id}, time: {datetime.now()}")
    try:
        info = random.choice(words_data) if words_data else None
        if info is None:
            await context.bot.send_message(chat_id=user_id, text="База слов пуста или не загружена!")
            return

        # Сохраняем инфу о слове пользователю, чтобы задания работали как в ручном сценарии
        current_word_info.clear()
        current_word_info.update(info)
        if info['word'] in spelling_choices:
            options, correct_index = get_shuffled_spelling_task(info['word'])
            current_word_info['spelling_variants'] = options
            current_word_info['spelling_correct_index'] = correct_index
        else:
            current_word_info['spelling_variants'] = []
            current_word_info['spelling_correct_index'] = None
        current_word_info['tasks'] = generate_tasks(info['word'], info['meaning_en'])
        global completed_today, task_position
        completed_today = []
        task_position = 0

        # Формируем основное сообщение
        msg = (
            f"📗 <b>Слово дня:</b> <i>{info['word']}</i>\n"
            f"💬 <b>Значение:</b> <i>{info['meaning_ru']}</i>\n"
            f"✏️ <b>Пример:</b> <i>{info['example']}</i>"
        )
        await context.bot.send_message(chat_id=user_id, text=msg, parse_mode='HTML')

        # Второе сообщение как при ручном получении
        await context.bot.send_message(chat_id=user_id, text="💡 Давай попрактикуемся! Сейчас будет задание…")

        # Первое задание, если оно есть
        tasks = current_word_info.get('tasks', [])
        if tasks:
            t = tasks[0]
            # Если задание на правописание — отправляем с клавиатурой-выбором
            if isinstance(t, tuple):
                await context.bot.send_message(
                    chat_id=user_id,
                    text=t[0],
                    reply_markup=t[3],
                    parse_mode='HTML'
                )
            else:
                await context.bot.send_message(
                    chat_id=user_id,
                    text=t,
                    reply_markup=ReplyKeyboardRemove()
                )
    except Exception as e:
        print(f"Ошибка отправки слова по расписанию: {e}")


def add_daily_reminder(context, user_id):
    remind_time_str = user_settings.get(str(user_id), {}).get('remind_time', "11:00")
    h, m = map(int, remind_time_str.split(":"))
    now = datetime.now()
    target = datetime.combine(now.date(), time(hour=h, minute=m))
    if now > target:
        target += timedelta(days=1)
    print(f"[DEBUG] add_daily_reminder вызвана: user_id={user_id}, time={h:02d}:{m:02d}, server_time={now}")
    context.job_queue.run_daily(
        send_daily_word,
        time=time(hour=h, minute=m),
        days=(0,1,2,3,4,5,6),
        chat_id=user_id,
        name=f"daily_word_{user_id}"
    )

async def check_task(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global current_word_info, completed_today, task_position
    try:
        user_answer = update.message.text.strip()
        if 'tasks' not in current_word_info or not current_word_info['tasks']:
            await update.message.reply_text("Для начала работы нажмите «Получить слово».")
            return
        tasks = current_word_info['tasks']
        if not isinstance(tasks, list) or len(tasks) == 0:
            await update.message.reply_text("Нет активных заданий — получите новое слово.")
            print("check_task: tasks пустой список!")
            return
        if task_position >= len(tasks):
            await update.message.reply_text("Все задания выполнены! Получите новое слово завтра.")
            print(f"check_task: task_position {task_position} вне диапазона ({len(tasks)})")
            return
        t = tasks[task_position]
        spelling_variants = current_word_info.get('spelling_variants', [])
        spelling_correct_index = current_word_info.get('spelling_correct_index', None)
        correct = False
        if isinstance(t, tuple) and spelling_variants and spelling_correct_index is not None:
            if user_answer in t[1] and t[1].index(user_answer) == t[2]:
                await update.message.reply_text('✅ Верно! Ты выбрал правильное написание слова.', reply_markup=ReplyKeyboardRemove())
                completed_today.append(task_position)
                task_position += 1
                await send_next_task(update, context)
                return
            else:
                keyboard_layout = [[opt] for opt in t[1]]
                keyboard_layout.append(['Показать ответы'])
                retry_keyboard = ReplyKeyboardMarkup(keyboard_layout, resize_keyboard=True)
                await update.message.reply_text(
                    'Неверно! Попробуй ещё раз выбрать правильный вариант или нажмите «Показать ответы».',
                    reply_markup=retry_keyboard
                )
                return
        word = current_word_info.get('word', '').lower()
        synonyms = [s.strip().lower() for s in current_word_info.get('synonyms', [])]
        meaning_parts = [part.strip().lower() for part in current_word_info.get('meaning_ru', '').replace('.', '').split(',')]
        base_example = current_word_info.get('example', '').strip().lower()
        if word and word in user_answer.lower() and user_answer != base_example and user_answer.isascii() and len(user_answer.split()) >= 3:
            await update.message.reply_text("✅ Молодец! Вы составили свой пример предложения с этим словом.", reply_markup=ReplyKeyboardRemove())
            correct = True
        elif any(part in user_answer.lower() for part in meaning_parts if part):
            await update.message.reply_text("✅ Правильно! Вы верно перевели значение.", reply_markup=ReplyKeyboardRemove())
            correct = True
        elif user_answer.lower() in synonyms:
            await update.message.reply_text("✅ Отлично! Ваш синоним подходит.", reply_markup=ReplyKeyboardRemove())
            correct = True
        if correct:
            completed_today.append(task_position)
            task_position += 1
            await send_next_task(update, context)
        else:
            show_answers_keyboard = ReplyKeyboardMarkup([['Показать ответы']], resize_keyboard=True)
            await update.message.reply_text(
                "Попробуйте еще раз или воспользуйтесь кнопкой ниже:",
                reply_markup=show_answers_keyboard
            )
    except Exception as e:
        print(f"Ошибка check_task: {e}")

async def message_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        text = update.message.text.strip()
        if context.user_data.get('waiting_for_remind_time'):
            await set_remind_time(update, context)
        elif text == 'Показать ответы':
            await show_answers(update, context)
        elif text == 'Помощь':
            await help_command(update, context)
        elif text == 'Получить слово':
            await send_word(update, context)
        elif text == 'Настройки':
            await ask_remind_time(update, context)
        else:
            await check_task(update, context)
    except Exception as e:
        print(f"Ошибка message_handler: {e}, text={update.message.text}")

def main():
    try:
        app = ApplicationBuilder().token(TOKEN).build()
        app.add_handler(CommandHandler('start', start))
        app.add_handler(CommandHandler('stats', stats_command))
        app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, message_handler))
        app.run_polling()
    except Exception as e:
        print(f"Ошибка main(): {e}")

if __name__ == "__main__":
    main()


