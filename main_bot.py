import os
import logging
from flask import Flask, render_template_string
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, ContextTypes

# Настройка логирования
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)

# Конфигурация
BOT_TOKEN = os.environ.get("BOT_TOKEN")
ADMIN_ID = os.environ.get("ADMIN_ID", "")  # ID администратора через запятую
PORT = int(os.environ.get("PORT", 5000))

QUESTIONS = [
    "Рабочая группа Минпросвещения разработала Программу просвещения по запросу родителей. Программа просвещения родителей – это нормативный документ, по которому должны работать все детские сады.",
    "Один из принципов просвещения – приоритет семьи в вопросах воспитания, обучения и развития.",
    "Основной адресат Программы просвещения – педагоги дошкольных образовательных организаций.",
    "Никто, кроме воспитателей, не может просвещать родителей воспитанников.",
    "Программа просвещения родителей – это новый дополнительный пункт в ФОП ДО",
    "Тематика и формы взаимодействия и педагогического просвещения родителей, которые содержит Программа, – примерные. Педагоги могут их самостоятельно преобразовывать.",
    "Программа просвещения родителей обязательна для реализации во всех дошкольных образовательных организациях."  # 7-й вопрос
]

# Хранилище результатов
class ResultsStorage:
    def __init__(self):
        self.results = {i: {"yes": 0, "no": 0} for i in range(len(QUESTIONS))}
        self.user_progress = {}  # Храним прогресс пользователей
    
    def add_vote(self, question_id: int, answer: str, user_id: int):
        if question_id in self.results and answer in self.results[question_id]:
            self.results[question_id][answer] += 1
            # Сохраняем прогресс пользователя
            if user_id not in self.user_progress:
                self.user_progress[user_id] = {}
            self.user_progress[user_id][question_id] = answer
    
    def get_user_progress(self, user_id: int):
        return self.user_progress.get(user_id, {})
    
    def get_next_question(self, user_id: int):
        user_progress = self.get_user_progress(user_id)
        for i in range(len(QUESTIONS)):
            if i not in user_progress:
                return i
        return None  # Все вопросы пройдены

results_storage = ResultsStorage()

# Flask приложение для Replit
app = Flask(__name__)

@app.route('/')
def home():
    """Статусная страница для проверки работы бота"""
    html = """
    <!DOCTYPE html>
    <html>
    <head>
        <title>Опрос бот</title>
        <meta charset="utf-8">
        <style>
            body { font-family: Arial, sans-serif; max-width: 800px; margin: 0 auto; padding: 20px; }
            .status { background: #f0f8ff; padding: 20px; border-radius: 10px; }
            .question { margin: 15px 0; padding: 10px; background: #f9f9f9; border-left: 4px solid #4CAF50; }
            .stats { background: #e8f5e8; padding: 15px; border-radius: 8px; margin: 10px 0; }
        </style>
    </head>
    <body>
        <h1>🤖 Бот для интерактивного опроса</h1>
        <div class="status">
            <p><strong>Статус:</strong> ✅ Активен</p>
            <p><strong>Основной файл:</strong> main_bot.py</p>
            <p><strong>Количество вопросов:</strong> {{ questions_count }}</p>
            <p><strong>Для начала опроса:</strong> Перейдите в Telegram и напишите боту команду <code>/start</code></p>
        </div>
        
        <div class="stats">
            <h3>📊 Общая статистика (только для админа):</h3>
            {% for i in range(questions_count) %}
            <div class="question">
                <p><strong>Вопрос {{ i+1 }}:</strong></p>
                <p>✅ Да: {{ results[i]['yes'] }} ({{ (results[i]['yes'] / (results[i]['yes'] + results[i]['no']) * 100) if (results[i]['yes'] + results[i]['no']) > 0 else 0 | round(1) }}%)</p>
                <p>❌ Нет: {{ results[i]['no'] }} ({{ (results[i]['no'] / (results[i]['yes'] + results[i]['no']) * 100) if (results[i]['yes'] + results[i]['no']) > 0 else 0 | round(1) }}%)</p>
                <p>Всего: {{ results[i]['yes'] + results[i]['no'] }}</p>
            </div>
            {% endfor %}
        </div>
        
        <h2>Вопросы опроса:</h2>
        {% for i, question in questions %}
        <div class="question">
            <p><strong>Вопрос {{ i+1 }}:</strong> {{ question }}</p>
        </div>
        {% endfor %}
    </body>
    </html>
    """
    return render_template_string(html, 
                                questions_count=len(QUESTIONS), 
                                questions=enumerate(QUESTIONS),
                                results=results_storage.results)

@app.route('/health')
def health():
    """Эндпоинт для проверки здоровья приложения"""
    return {"status": "healthy", "questions_count": len(QUESTIONS)}

def is_admin(user_id: int) -> bool:
    """Проверяет, является ли пользователь администратором"""
    if not ADMIN_ID:
        return False
    admin_ids = [int(x.strip()) for x in ADMIN_ID.split(',')]
    return user_id in admin_ids

def get_question_keyboard(question_id: int):
    """Создает клавиатуру с кнопками Да/Нет для вопроса"""
    keyboard = [
        [InlineKeyboardButton("✅ Да", callback_data=f"q{question_id}_yes")],
        [InlineKeyboardButton("❌ Нет", callback_data=f"q{question_id}_no")],
    ]
    return InlineKeyboardMarkup(keyboard)

def get_question_text(question_id: int, user_id: int, show_stats: bool = False):
    """Форматирует текст вопроса"""
    text = f"<b>Вопрос {question_id + 1}/7:</b>\n{QUESTIONS[question_id]}"
    
    if show_stats and is_admin(user_id):
        stats = results_storage.results[question_id]
        total = stats["yes"] + stats["no"]
        yes_percent = (stats["yes"] / total * 100) if total > 0 else 0
        no_percent = (stats["no"] / total * 100) if total > 0 else 0
        
        text += f"\n\n📊 <b>Статистика ответов:</b>\n"
        text += f"✅ Да: {stats['yes']} ({yes_percent:.1f}%)\n"
        text += f"❌ Нет: {stats['no']} ({no_percent:.1f}%)\n"
        text += f"👥 Всего ответов: {total}"
    
    return text

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Отправляет приветственное сообщение и первый вопрос"""
    user_id = update.effective_user.id
    
    welcome_text = (
        "📝 <b>Опрос практикума для воспитателей</b>\n\n"
        "Ответьте на 7 вопросов, используя кнопки ниже.\n"
        "После ответа на вопрос автоматически появится следующий.\n\n"
        "<i>Статистика доступна только администраторам</i>"
    )
    
    await update.message.reply_text(
        welcome_text,
        parse_mode='HTML'
    )
    
    # Находим следующий вопрос для пользователя
    next_question = results_storage.get_next_question(user_id)
    if next_question is None:
        # Все вопросы пройдены
        await update.message.reply_text(
            "🎉 <b>Вы уже ответили на все вопросы опроса!</b>\nСпасибо за участие!",
            parse_mode='HTML'
        )
        return
    
    await send_question(update, context, next_question)

async def send_question(update: Update, context: ContextTypes.DEFAULT_TYPE, question_id: int):
    """Отправляет вопрос пользователю"""
    user_id = update.effective_user.id
    is_user_admin = is_admin(user_id)
    
    question_text = get_question_text(question_id, user_id, show_stats=False)
    
    # Для callback query редактируем сообщение, для нового - отправляем
    if hasattr(update, 'callback_query') and update.callback_query:
        await update.callback_query.edit_message_text(
            text=question_text,
            reply_markup=get_question_keyboard(question_id),
            parse_mode='HTML'
        )
    else:
        await update.message.reply_text(
            text=question_text,
            reply_markup=get_question_keyboard(question_id),
            parse_mode='HTML'
        )

async def handle_answer(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обрабатывает нажатия кнопок"""
    query = update.callback_query
    user_id = update.effective_user.id
    await query.answer()
    
    data = query.data
    question_id = int(data[1])
    answer = data.split("_")[1]
    
    # Обновляем результаты
    results_storage.add_vote(question_id, answer, user_id)
    
    # Показываем подтверждение ответа
    confirmation_text = f"<b>Вопрос {question_id + 1}/7:</b>\n{QUESTIONS[question_id]}\n\n"
    confirmation_text += "✅ <b>Ваш ответ принят!</b>"
    
    if is_admin(user_id):
        # Показываем статистику админу
        stats = results_storage.results[question_id]
        total = stats["yes"] + stats["no"]
        yes_percent = (stats["yes"] / total * 100) if total > 0 else 0
        no_percent = (stats["no"] / total * 100) if total > 0 else 0
        
        confirmation_text += f"\n\n📊 <b>Статистика:</b>\n"
        confirmation_text += f"✅ Да: {stats['yes']} ({yes_percent:.1f}%)\n"
        confirmation_text += f"❌ Нет: {stats['no']} ({no_percent:.1f}%)"
    
    await query.edit_message_text(
        text=confirmation_text,
        parse_mode='HTML'
    )
    
    # Отправляем следующий вопрос
    next_question = results_storage.get_next_question(user_id)
    if next_question is not None:
        # Создаем fake update для отправки следующего вопроса
        fake_update = Update(update.update_id + 1, message=update.effective_message)
        await send_question(fake_update, context, next_question)
    else:
        # Все вопросы пройдены
        completion_text = "🎉 <b>Спасибо за участие в опросе!</b>\nВы ответили на все вопросы."
        
        if is_admin(user_id):
            completion_text += "\n\n📊 <b>Полная статистика доступна в веб-интерфейсе</b>"
        
        await context.bot.send_message(
            chat_id=user_id,
            text=completion_text,
            parse_mode='HTML'
        )

async def stats_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Команда для просмотра статистики (только для админов)"""
    user_id = update.effective_user.id
    
    if not is_admin(user_id):
        await update.message.reply_text("❌ Эта команда доступна только администраторам.")
        return
    
    stats_text = "📊 <b>Статистика опроса:</b>\n\n"
    
    for i in range(len(QUESTIONS)):
        stats = results_storage.results[i]
        total = stats["yes"] + stats["no"]
        yes_percent = (stats["yes"] / total * 100) if total > 0 else 0
        no_percent = (stats["no"] / total * 100) if total > 0 else 0
        
        stats_text += f"<b>Вопрос {i + 1}:</b>\n"
        stats_text += f"✅ Да: {stats['yes']} ({yes_percent:.1f}%)\n"
        stats_text += f"❌ Нет: {stats['no']} ({no_percent:.1f}%)\n"
        stats_text += f"👥 Всего: {total}\n\n"
    
    await update.message.reply_text(stats_text, parse_mode='HTML')

async def error_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик ошибок"""
    logging.error(f"Exception while handling an update: {context.error}")

def main():
    """Основная функция запуска"""
    if not BOT_TOKEN:
        logging.error("BOT_TOKEN не задан в переменных окружения!")
        return
    
    # Создаем приложение бота
    application = Application.builder().token(BOT_TOKEN).build()
    
    # Регистрируем обработчики
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("stats", stats_command))
    application.add_handler(CallbackQueryHandler(handle_answer))
    application.add_error_handler(error_handler)
    
    # Запускаем бота
    logging.info("Бот запускается из main_bot.py...")
    application.run_polling(drop_pending_updates=True)

if __name__ == "__main__":
    # Запускаем Flask в отдельном потоке для Replit
    from threading import Thread
    flask_thread = Thread(target=lambda: app.run(host='0.0.0.0', port=PORT, debug=False, use_reloader=False))
    flask_thread.daemon = True
    flask_thread.start()
    
    # Запускаем бота в основном потоке
    main()
