import os
import logging
import csv
import io
from datetime import datetime
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

# Обновленные вопросы согласно уточнению
QUESTIONS = [
    "Рабочая группа Минпросвещения разработала Программу просвещения по запросу родителей.",
    "Программа просвещения родителей – это нормативный документ, по которому должны работать все детские сады.",
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
        self.user_progress = {}  # Храним прогресс пользователей
        self.user_answers = {}   # Детальные ответы пользователей
        self.user_info = {}      # Информация о пользователях
    
    def add_vote(self, question_id: int, answer: str, user_id: int, username: str = "", first_name: str = ""):
        if question_id in self.results and answer in self.results[question_id]:
            # Обновляем общую статистику
            self.results[question_id][answer] += 1
            
            # Сохраняем прогресс пользователя
            if user_id not in self.user_progress:
                self.user_progress[user_id] = {}
                self.user_answers[user_id] = {}
                self.user_info[user_id] = {
                    "username": username,
                    "first_name": first_name,
                    "last_active": datetime.now().isoformat()
                }
            
            self.user_progress[user_id][question_id] = answer
            self.user_answers[user_id][question_id] = {
                "answer": answer,
                "timestamp": datetime.now().isoformat()
            }
            self.user_info[user_id]["last_active"] = datetime.now().isoformat()
    
    def get_user_progress(self, user_id: int):
        return self.user_progress.get(user_id, {})
    
    def get_next_question(self, user_id: int):
        user_progress = self.get_user_progress(user_id)
        for i in range(len(QUESTIONS)):
            if i not in user_progress:
                return i
        return None  # Все вопросы пройдены
    
    def get_completion_percentage(self, user_id: int):
        user_progress = self.get_user_progress(user_id)
        return (len(user_progress) / len(QUESTIONS)) * 100
    
    def reset_results(self):
        """Сброс всех результатов (только для админа)"""
        self.results = {i: {"yes": 0, "no": 0} for i in range(len(QUESTIONS))}
        self.user_progress = {}
        self.user_answers = {}
    
    def export_to_csv(self):
        """Экспорт результатов в CSV формат"""
        output = io.StringIO()
        writer = csv.writer(output)
        
        # Заголовок
        writer.writerow(["Question Number", "Question Text", "Yes", "No", "Total", "Yes %", "No %"])
        
        # Данные по вопросам
        for i, question in enumerate(QUESTIONS):
            stats = self.results[i]
            total = stats["yes"] + stats["no"]
            yes_percent = (stats["yes"] / total * 100) if total > 0 else 0
            no_percent = (stats["no"] / total * 100) if total > 0 else 0
            
            writer.writerow([
                f"Q{i+1}",
                question,
                stats["yes"],
                stats["no"],
                total,
                f"{yes_percent:.1f}%",
                f"{no_percent:.1f}%"
            ])
        
        # Пустая строка
        writer.writerow([])
        
        # Статистика по пользователям
        writer.writerow(["User Statistics"])
        writer.writerow(["User ID", "Username", "Name", "Completed Questions", "Completion %", "Last Active"])
        
        for user_id, info in self.user_info.items():
            completed = len(self.user_progress.get(user_id, {}))
            completion_pct = (completed / len(QUESTIONS)) * 100
            
            writer.writerow([
                user_id,
                info.get("username", ""),
                info.get("first_name", ""),
                completed,
                f"{completion_pct:.1f}%",
                info.get("last_active", "")
            ])
        
        return output.getvalue()

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
        <title>Опрос практикума для воспитателей</title>
        <meta charset="utf-8">
        <style>
            body { font-family: Arial, sans-serif; max-width: 800px; margin: 0 auto; padding: 20px; }
            .status { background: #f0f8ff; padding: 20px; border-radius: 10px; }
            .question { margin: 15px 0; padding: 10px; background: #f9f9f9; border-left: 4px solid #4CAF50; }
            .stats { background: #e8f5e8; padding: 15px; border-radius: 8px; margin: 10px 0; }
            .progress-bar { background: #ddd; border-radius: 5px; margin: 10px 0; }
            .progress { background: #4CAF50; height: 20px; border-radius: 5px; text-align: center; color: white; line-height: 20px; }
        </style>
    </head>
    <body>
        <h1>🤖 Опрос практикума для воспитателей</h1>
        <div class="status">
            <p><strong>Статус:</strong> ✅ Активен</p>
            <p><strong>Версия:</strong> Улучшенная 2.0</p>
            <p><strong>Количество вопросов:</strong> {{ questions_count }}</p>
            <p><strong>Участников:</strong> {{ participants }}</p>
            <p><strong>Всего ответов:</strong> {{ total_answers }}</p>
            <p><strong>Для начала опроса:</strong> Перейдите в Telegram и напишите боту команду <code>/start</code></p>
        </div>
        
        {% if admin %}
        <div class="stats">
            <h3>📊 Общая статистика:</h3>
            {% for i in range(questions_count) %}
            <div class="question">
                <p><strong>Вопрос {{ i+1 }}:</strong> {{ questions[i] }}</p>
                <p>✅ Да: {{ results[i]['yes'] }} ({{ (results[i]['yes'] / (results[i]['yes'] + results[i]['no']) * 100) if (results[i]['yes'] + results[i]['no']) > 0 else 0 | round(1) }}%)</p>
                <p>❌ Нет: {{ results[i]['no'] }} ({{ (results[i]['no'] / (results[i]['yes'] + results[i]['no']) * 100) if (results[i]['yes'] + results[i]['no']) > 0 else 0 | round(1) }}%)</p>
                <p>Всего ответов: {{ results[i]['yes'] + results[i]['no'] }}</p>
            </div>
            {% endfor %}
        </div>
        {% endif %}
    </body>
    </html>
    """
    
    # Определяем, админ ли смотрит страницу
    is_admin = True  # Для демонстрации
    total_answers = sum(sum(stats.values()) for stats in results_storage.results.values())
    
    return render_template_string(html, 
                                questions_count=len(QUESTIONS), 
                                questions=QUESTIONS,
                                results=results_storage.results,
                                participants=len(results_storage.user_info),
                                total_answers=total_answers,
                                admin=is_admin)

@app.route('/health')
def health():
    """Эндпоинт для проверки здоровья приложения"""
    total_answers = sum(sum(stats.values()) for stats in results_storage.results.values())
    return {
        "status": "healthy", 
        "questions_count": len(QUESTIONS),
        "participants": len(results_storage.user_info),
        "total_answers": total_answers
    }

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

def get_admin_keyboard():
    """Клавиатура для админ панели"""
    keyboard = [
        [InlineKeyboardButton("📊 Статистика", callback_data="admin_stats")],
        [InlineKeyboardButton("📥 Выгрузить CSV", callback_data="admin_export")],
        [InlineKeyboardButton("🔄 Сбросить результаты", callback_data="admin_reset")],
        [InlineKeyboardButton("❌ Закрыть", callback_data="admin_close")],
    ]
    return InlineKeyboardMarkup(keyboard)

def get_question_text(question_id: int, user_id: int, show_stats: bool = False):
    """Форматирует текст вопроса"""
    progress = results_storage.get_completion_percentage(user_id)
    text = f"<b>Вопрос {question_id + 1}/{len(QUESTIONS)}</b> ({progress:.0f}% завершено)\n\n{QUESTIONS[question_id]}"
    
    if show_stats and is_admin(user_id):
        stats = results_storage.results[question_id]
        total = stats["yes"] + stats["no"]
        yes_percent = (stats["yes"] / total * 100) if total > 0 else 0
        no_percent = (stats["no"] / total * 100) if total > 0 else 0
        
        text += f"\n\n📊 <b>Статистика:</b>\n"
        text += f"✅ Да: {stats['yes']} ({yes_percent:.1f}%)\n"
        text += f"❌ Нет: {stats['no']} ({no_percent:.1f}%)\n"
        text += f"👥 Всего: {total}"
    
    return text

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Отправляет приветственное сообщение и первый вопрос"""
    user = update.effective_user
    user_id = user.id
    
    # Проверяем прогресс пользователя
    completed = len(results_storage.get_user_progress(user_id))
    progress = results_storage.get_completion_percentage(user_id)
    
    welcome_text = (
        "📝 <b>Опрос практикума для воспитателей</b>\n\n"
        f"<i>Ваш прогресс: {completed}/{len(QUESTIONS)} вопросов ({progress:.0f}%)</i>\n\n"
        "Ответьте на вопросы, используя кнопки ниже.\n"
        "После ответа на вопрос автоматически появится следующий.\n\n"
    )
    
    if is_admin(user_id):
        welcome_text += "👑 <b>Вы администратор</b> - используйте /admin для управления\n\n"
    
    welcome_text += "<i>Статистика доступна только администраторам</i>"
    
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
    user = update.effective_user
    user_id = user.id
    await query.answer()
    
    data = query.data
    question_id = int(data[1])
    answer = data.split("_")[1]
    
    # Обновляем результаты
    results_storage.add_vote(question_id, answer, user_id, user.username, user.first_name)
    
    # Показываем подтверждение ответа
    confirmation_text = f"<b>Вопрос {question_id + 1}/{len(QUESTIONS)}:</b>\n{QUESTIONS[question_id]}\n\n"
    confirmation_text += "✅ <b>Ваш ответ принят!</b>"
    
    # Показываем прогресс
    completed = len(results_storage.get_user_progress(user_id))
    progress = results_storage.get_completion_percentage(user_id)
    confirmation_text += f"\n\n📈 <b>Прогресс:</b> {completed}/{len(QUESTIONS)} ({progress:.0f}%)"
    
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
        # Ждем 1 секунду перед показом следующего вопроса
        await context.bot.send_chat_action(chat_id=user_id, action="typing")
        import asyncio
        await asyncio.sleep(1)
        
        await send_question(update, context, next_question)
    else:
        # Все вопросы пройдены
        completion_text = (
            "🎉 <b>Поздравляем! Вы завершили опрос!</b>\n\n"
            "Спасибо за ваше время и участие. "
            "Ваши ответы помогут улучшить образовательный процесс."
        )
        
        if is_admin(user_id):
            completion_text += "\n\n👑 <b>Вы администратор</b> - используйте /admin для просмотра статистики"
        
        await context.bot.send_message(
            chat_id=user_id,
            text=completion_text,
            parse_mode='HTML'
        )

async def admin_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Команда для админ панели"""
    user_id = update.effective_user.id
    
    if not is_admin(user_id):
        await update.message.reply_text("❌ Эта команда доступна только администраторам.")
        return
    
    stats_text = "👑 <b>Панель администратора</b>\n\n"
    
    # Общая статистика
    total_answers = sum(sum(stats.values()) for stats in results_storage.results.values())
    total_participants = len(results_storage.user_info)
    
    stats_text += f"📊 <b>Общая статистика:</b>\n"
    stats_text += f"• Участников: {total_participants}\n"
    stats_text += f"• Всего ответов: {total_answers}\n"
    stats_text += f"• Вопросов: {len(QUESTIONS)}\n\n"
    
    # Прогресс по вопросам
    stats_text += "<b>Прогресс по вопросам:</b>\n"
    for i in range(len(QUESTIONS)):
        stats = results_storage.results[i]
        total = stats["yes"] + stats["no"]
        answered_pct = (total / total_participants * 100) if total_participants > 0 else 0
        
        stats_text += f"{i+1}. {total} ответов ({answered_pct:.1f}%)\n"
    
    await update.message.reply_text(
        stats_text,
        reply_markup=get_admin_keyboard(),
        parse_mode='HTML'
    )

async def handle_admin_actions(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обрабатывает действия админа"""
    query = update.callback_query
    user_id = update.effective_user.id
    await query.answer()
    
    if not is_admin(user_id):
        await query.edit_message_text("❌ Доступ запрещен.")
        return
    
    action = query.data
    
    if action == "admin_stats":
        # Показываем детальную статистику
        stats_text = "📊 <b>Детальная статистика:</b>\n\n"
        
        for i in range(len(QUESTIONS)):
            stats = results_storage.results[i]
            total = stats["yes"] + stats["no"]
            yes_percent = (stats["yes"] / total * 100) if total > 0 else 0
            no_percent = (stats["no"] / total * 100) if total > 0 else 0
            
            stats_text += f"<b>Вопрос {i + 1}:</b>\n"
            stats_text += f"✅ Да: {stats['yes']} ({yes_percent:.1f}%)\n"
            stats_text += f"❌ Нет: {stats['no']} ({no_percent:.1f}%)\n"
            stats_text += f"👥 Всего: {total}\n\n"
        
        await query.edit_message_text(stats_text, parse_mode='HTML')
    
    elif action == "admin_export":
        # Выгрузка в CSV
        csv_data = results_storage.export_to_csv()
        csv_file = io.BytesIO(csv_data.encode('utf-8'))
        csv_file.name = f"survey_results_{datetime.now().strftime('%Y%m%d_%H%M')}.csv"
        
        await context.bot.send_document(
            chat_id=user_id,
            document=csv_file,
            filename=csv_file.name,
            caption="📥 <b>Результаты опроса в CSV формате</b>",
            parse_mode='HTML'
        )
        
        # Возвращаемся к админ панели
        await admin_command(update, context)
    
    elif action == "admin_reset":
        # Подтверждение сброса
        confirm_keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("✅ Да, сбросить", callback_data="admin_confirm_reset")],
            [InlineKeyboardButton("❌ Отмена", callback_data="admin_cancel_reset")]
        ])
        
        await query.edit_message_text(
            "⚠️ <b>Внимание!</b>\n\n"
            "Вы уверены, что хотите сбросить ВСЕ результаты опроса?\n"
            "Это действие нельзя отменить!",
            reply_markup=confirm_keyboard,
            parse_mode='HTML'
        )
    
    elif action == "admin_confirm_reset":
        # Сброс результатов
        results_storage.reset_results()
        await query.edit_message_text(
            "✅ <b>Все результаты были сброшены!</b>",
            parse_mode='HTML'
        )
    
    elif action == "admin_cancel_reset":
        # Отмена сброса
        await admin_command(update, context)
    
    elif action == "admin_close":
        # Закрытие админ панели
        await query.edit_message_text("👑 Панель администратора закрыта.")

async def progress_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Показывает прогресс пользователя"""
    user_id = update.effective_user.id
    completed = len(results_storage.get_user_progress(user_id))
    progress = results_storage.get_completion_percentage(user_id)
    
    progress_text = (
        "📊 <b>Ваш прогресс:</b>\n\n"
        f"• Завершено вопросов: {completed}/{len(QUESTIONS)}\n"
        f"• Процент выполнения: {progress:.1f}%\n\n"
    )
    
    if completed == len(QUESTIONS):
        progress_text += "🎉 Вы ответили на все вопросы опроса!"
    else:
        next_question = results_storage.get_next_question(user_id)
        progress_text += f"Следующий вопрос: {next_question + 1}/{len(QUESTIONS)}"
        
        # Кнопка для продолжения
        keyboard = [[InlineKeyboardButton("➡️ Продолжить опрос", callback_data=f"continue_{next_question}")]]
        await update.message.reply_text(
            progress_text,
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode='HTML'
        )
        return
    
    await update.message.reply_text(progress_text, parse_mode='HTML')

async def handle_continue(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обрабатывает продолжение опроса"""
    query = update.callback_query
    user_id = update.effective_user.id
    await query.answer()
    
    # Получаем номер вопроса из callback_data
    question_id = int(query.data.split("_")[1])
    await send_question(update, context, question_id)

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
    application.add_handler(CommandHandler("admin", admin_command))
    application.add_handler(CommandHandler("progress", progress_command))
    application.add_handler(CallbackQueryHandler(handle_answer, pattern="^q[0-9]_(yes|no)$"))
    application.add_handler(CallbackQueryHandler(handle_admin_actions, pattern="^admin_"))
    application.add_handler(CallbackQueryHandler(handle_continue, pattern="^continue_[0-9]$"))
    application.add_error_handler(error_handler)
    
    # Запускаем бота
    logging.info("Бот запускается...")
    application.run_polling(drop_pending_updates=True)

if __name__ == "__main__":
    # Запускаем Flask в отдельном потоке для Replit
    from threading import Thread
    flask_thread = Thread(target=lambda: app.run(host='0.0.0.0', port=PORT, debug=False, use_reloader=False))
    flask_thread.daemon = True
    flask_thread.start()
    
    # Запускаем бота в основном потоке
    main()
