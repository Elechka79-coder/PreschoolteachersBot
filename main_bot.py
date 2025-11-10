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
PORT = int(os.environ.get("PORT", 5000))

QUESTIONS = [
    "Рабочая группа Минпросвещения разработала Программу просвещения по запросу родителей. Программа просвещения родителей – это нормативный документ, по которому должны работать все детские сады.",
    "Один из принципов просвещения – приоритет семьи в вопросах воспитания, обучения и развития.",
    "Основной адресат Программы просвещения – педагоги дошкольных образовательных организаций.",
    "Никто, кроме воспитателей, не может просвещать родителей воспитанников.",
    "Программа просвещения родителей – это новый дополнительный пункт в ФОП ДО",
    "Тематика и формы взаимодействия и педагогического просвещения родителей, которые содержит Программа, – примерные. Педагоги могут их самостоятельно преобразовывать."
]

# Хранилище результатов
class ResultsStorage:
    def __init__(self):
        self.results = {i: {"yes": 0, "no": 0} for i in range(len(QUESTIONS))}
    
    def add_vote(self, question_id: int, answer: str):
        if question_id in self.results and answer in self.results[question_id]:
            self.results[question_id][answer] += 1

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
        
        <h2>Вопросы опроса:</h2>
        {% for i, question in questions %}
        <div class="question">
            <p><strong>Вопрос {{ i+1 }}:</strong> {{ question }}</p>
        </div>
        {% endfor %}
        
        <div class="status">
            <p><strong>GitHub репозиторий:</strong> Публичный</p>
            <p><strong>Размещение:</strong> Replit</p>
        </div>
    </body>
    </html>
    """
    return render_template_string(html, questions_count=len(QUESTIONS), questions=enumerate(QUESTIONS))

@app.route('/health')
def health():
    """Эндпоинт для проверки здоровья приложения"""
    return {"status": "healthy", "questions_count": len(QUESTIONS)}

# Функции бота
def get_question_keyboard(question_id: int):
    """Создает клавиатуру с кнопками Да/Нет для вопроса"""
    keyboard = [
        [InlineKeyboardButton("✅ Да", callback_data=f"q{question_id}_yes")],
        [InlineKeyboardButton("❌ Нет", callback_data=f"q{question_id}_no")],
    ]
    return InlineKeyboardMarkup(keyboard)

def get_results_text(question_id: int):
    """Форматирует текст вопроса с текущей статистикой"""
    stats = results_storage.results[question_id]
    total = stats["yes"] + stats["no"]
    yes_percent = (stats["yes"] / total * 100) if total > 0 else 0
    no_percent = (stats["no"] / total * 100) if total > 0 else 0
    
    return (
        f"<b>Вопрос {question_id + 1}:</b>\n"
        f"{QUESTIONS[question_id]}\n\n"
        f"📊 <b>Статистика ответов:</b>\n"
        f"✅ Да: {stats['yes']} ({yes_percent:.1f}%)\n"
        f"❌ Нет: {stats['no']} ({no_percent:.1f}%)\n"
        f"👥 Всего ответов: {total}"
    )

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Отправляет приветственное сообщение и первый вопрос"""
    welcome_text = (
        "📝 <b>Примите участие в опросе</b>\n\n"
        "Ответьте на вопросы, используя кнопки ниже. "
        "Статистика обновляется мгновенно после каждого ответа.\n\n"
        f"<i>Всего вопросов: {len(QUESTIONS)}</i>"
    )
    
    await update.message.reply_text(
        welcome_text,
        parse_mode='HTML'
    )
    
    await show_question(update, context, 0)

async def show_question(update: Update, context: ContextTypes.DEFAULT_TYPE, question_id: int):
    """Показывает конкретный вопрос"""
    query = update.callback_query if hasattr(update, 'callback_query') else None
    
    message_text = get_results_text(question_id)
    
    if query:
        await query.edit_message_text(
            text=message_text,
            reply_markup=get_question_keyboard(question_id),
            parse_mode='HTML'
        )
    else:
        await update.message.reply_text(
            text=message_text,
            reply_markup=get_question_keyboard(question_id),
            parse_mode='HTML'
        )

async def handle_answer(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обрабатывает нажатия кнопок"""
    query = update.callback_query
    await query.answer()
    
    data = query.data
    question_id = int(data[1])
    answer = data.split("_")[1]
    
    # Обновляем результаты
    results_storage.add_vote(question_id, answer)
    
    # Показываем обновленную статистику
    await show_question(update, context, question_id)

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
