import os
import logging
import csv
import io
import json
import zipfile
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

# Получаем список ID администраторов
admin_ids = [int(x.strip()) for x in ADMIN_ID.split(',')] if ADMIN_ID else []

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
        # Администраторы не могут участвовать в опросе
        if user_id in admin_ids:
            return False
            
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
            return True
        return False
    
    def get_user_progress(self, user_id: int):
        return self.user_progress.get(user_id, {})
    
    def get_next_question(self, user_id: int):
        # Администраторы не могут участвовать в опросе
        if user_id in admin_ids:
            return None
            
        user_progress = self.get_user_progress(user_id)
        for i in range(len(QUESTIONS)):
            if i not in user_progress:
                return i
        return None  # Все вопросы пройдены
    
    def get_completion_percentage(self, user_id: int):
        # Администраторы не могут участвовать в опросе
        if user_id in admin_ids:
            return 0
            
        user_progress = self.get_user_progress(user_id)
        return (len(user_progress) / len(QUESTIONS)) * 100
    
    def reset_results(self):
        """Сброс всех результатов (только для админа)"""
        self.results = {i: {"yes": 0, "no": 0} for i in range(len(QUESTIONS))}
        self.user_progress = {}
        self.user_answers = {}
    
    def export_to_csv(self):
        """Экспорт результатов в CSV формат для Google Sheets"""
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
    
    def export_to_simple_html(self):
        """Создание упрощенного HTML отчета без сложных графиков"""
        total_answers = sum(sum(stats.values()) for stats in self.results.values())
        total_participants = len(self.user_info)
        
        html_content = f"""
        <!DOCTYPE html>
        <html>
        <head>
            <title>Результаты опроса - Практикум для воспитателей</title>
            <meta charset="utf-8">
            <style>
                body {{ font-family: Arial, sans-serif; max-width: 1000px; margin: 0 auto; padding: 20px; }}
                .header {{ background: #4CAF50; color: white; padding: 20px; border-radius: 10px; margin-bottom: 20px; }}
                .stats-card {{ background: white; padding: 15px; border-radius: 8px; box-shadow: 0 2px 5px rgba(0,0,0,0.1); margin-bottom: 15px; }}
                .question-card {{ background: #f8f9fa; padding: 12px; border-radius: 6px; margin: 10px 0; border-left: 4px solid #007bff; }}
                .summary-grid {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(150px, 1fr)); gap: 10px; margin: 15px 0; }}
                .summary-item {{ background: white; padding: 12px; border-radius: 6px; text-align: center; box-shadow: 0 1px 3px rgba(0,0,0,0.1); }}
                .percentage {{ font-size: 20px; font-weight: bold; color: #007bff; }}
                .progress-bar {{ background: #e0e0e0; border-radius: 5px; margin: 5px 0; }}
                .progress {{ background: #4CAF50; height: 20px; border-radius: 5px; }}
            </style>
        </head>
        <body>
            <div class="header">
                <h1>📊 Результаты опроса</h1>
                <p>Практикум для воспитателей - {datetime.now().strftime("%d.%m.%Y %H:%M")}</p>
                <p>Участников: {total_participants} | Ответов: {total_answers}</p>
            </div>

            <div class="summary-grid">
                <div class="summary-item">
                    <div class="percentage">{total_participants}</div>
                    <div>Участников</div>
                </div>
                <div class="summary-item">
                    <div class="percentage">{total_answers}</div>
                    <div>Всего ответов</div>
                </div>
                <div class="summary-item">
                    <div class="percentage">{len(QUESTIONS)}</div>
                    <div>Вопросов</div>
                </div>
            </div>
        """
        
        for i, question in enumerate(QUESTIONS):
            stats = self.results[i]
            total = stats["yes"] + stats["no"]
            yes_percent = (stats["yes"] / total * 100) if total > 0 else 0
            no_percent = (stats["no"] / total * 100) if total > 0 else 0
            
            html_content += f"""
            <div class="stats-card">
                <h3>Вопрос {i+1}</h3>
                <div class="question-card">
                    <p><strong>{question}</strong></p>
                </div>
                <p><strong>Результаты:</strong></p>
                <p>✅ Да: {stats['yes']} ({yes_percent:.1f}%)</p>
                <div class="progress-bar">
                    <div class="progress" style="width: {yes_percent}%"></div>
                </div>
                <p>❌ Нет: {stats['no']} ({no_percent:.1f}%)</p>
                <div class="progress-bar">
                    <div class="progress" style="width: {no_percent}%; background: #f44336;"></div>
                </div>
                <p><em>Всего ответов: {total}</em></p>
            </div>
            """
        
        html_content += """
        </body>
        </html>
        """
        
        return html_content
    
    def export_to_text_report(self):
        """Создание текстового отчета для отправки в Telegram"""
        total_answers = sum(sum(stats.values()) for stats in self.results.values())
        total_participants = len(self.user_info)
        
        text = f"📊 ОТЧЕТ ОПРОСА\n"
        text += f"Дата: {datetime.now().strftime('%d.%m.%Y %H:%M')}\n"
        text += f"Участников: {total_participants}\n"
        text += f"Всего ответов: {total_answers}\n"
        text += f"Вопросов: {len(QUESTIONS)}\n\n"
        
        for i, question in enumerate(QUESTIONS):
            stats = self.results[i]
            total = stats["yes"] + stats["no"]
            yes_percent = (stats["yes"] / total * 100) if total > 0 else 0
            no_percent = (stats["no"] / total * 100) if total > 0 else 0
            
            text += f"ВОПРОС {i+1}:\n"
            text += f"{question}\n"
            text += f"✅ Да: {stats['yes']} ({yes_percent:.1f}%)\n"
            text += f"❌ Нет: {stats['no']} ({no_percent:.1f}%)\n"
            text += f"Всего: {total}\n\n"
        
        return text

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
            body { font-family: Arial, sans-serif; max-width: 1200px; margin: 0 auto; padding: 20px; }
            .status { background: #f0f8ff; padding: 20px; border-radius: 10px; margin-bottom: 20px; }
            .export-buttons { display: grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); gap: 15px; margin: 20px 0; }
            .export-btn { background: white; padding: 15px; border-radius: 8px; text-align: center; box-shadow: 0 2px 5px rgba(0,0,0,0.1); text-decoration: none; color: #333; border: 2px solid #007bff; }
            .export-btn:hover { background: #007bff; color: white; }
        </style>
    </head>
    <body>
        <h1>🤖 Опрос практикума для воспитателей</h1>
        
        <div class="status">
            <p><strong>Статус:</strong> ✅ Активен</p>
            <p><strong>Версия:</strong> Упрощенная с текстовыми отчетами</p>
            <p><strong>Количество вопросов:</strong> {{ questions_count }}</p>
            <p><strong>Участников:</strong> {{ participants }}</p>
            <p><strong>Всего ответов:</strong> {{ total_answers }}</p>
            <p><strong>Для начала опроса:</strong> Перейдите в Telegram и напишите боту команду <code>/start</code></p>
        </div>

        <h2>📤 Экспорт результатов</h2>
        <div class="export-buttons">
            <a href="/export/html" class="export-btn" target="_blank">
                <strong>🌐 HTML Отчет</strong><br>
                Упрощенный HTML отчет
            </a>
            <a href="/export/csv" class="export-btn" download>
                <strong>📊 Google Sheets</strong><br>
                CSV для импорта в таблицы
            </a>
            <a href="/export/text" class="export-btn" target="_blank">
                <strong>📝 Текст</strong><br>
                Текстовый отчет
            </a>
        </div>

        <div class="status">
            <h3>👑 Информация для администраторов:</h3>
            <p>Администраторы не участвуют в опросе, а только управляют статистикой.</p>
            <p>Используйте команду <code>/admin</code> в Telegram для управления.</p>
        </div>
    </body>
    </html>
    """
    
    total_answers = sum(sum(stats.values()) for stats in results_storage.results.values())
    
    return render_template_string(html, 
                                questions_count=len(QUESTIONS),
                                participants=len(results_storage.user_info),
                                total_answers=total_answers)

@app.route('/export/html')
def export_html():
    """Экспорт в HTML отчет"""
    html_content = results_storage.export_to_simple_html()
    return html_content

@app.route('/export/text')
def export_text():
    """Экспорт в текстовый отчет"""
    text_content = results_storage.export_to_text_report()
    return f"<pre>{text_content}</pre>"

@app.route('/export/csv')
def export_csv():
    """Экспорт в CSV"""
    csv_data = results_storage.export_to_csv()
    response = app.response_class(
        response=csv_data,
        status=200,
        mimetype='text/csv',
        headers={'Content-Disposition': f'attachment; filename=survey_results_{datetime.now().strftime("%Y%m%d_%H%M")}.csv'}
    )
    return response

@app.route('/health')
def health():
    """Эндпоинт для проверки здоровья приложения"""
    total_answers = sum(sum(stats.values()) for stats in results_storage.results.values())
    return {
        "status": "healthy", 
        "questions_count": len(QUESTIONS),
        "participants": len(results_storage.user_info),
        "total_answers": total_answers,
        "admin_ids": admin_ids
    }

def is_admin(user_id: int) -> bool:
    """Проверяет, является ли пользователь администратором"""
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
        [InlineKeyboardButton("📝 Текстовый отчет", callback_data="admin_text")],
        [InlineKeyboardButton("🔄 Сбросить результаты", callback_data="admin_reset")],
        [InlineKeyboardButton("❌ Закрыть", callback_data="admin_close")],
    ]
    return InlineKeyboardMarkup(keyboard)

def get_continue_keyboard(next_question_id: int):
    """Клавиатура для продолжения опроса"""
    keyboard = [
        [InlineKeyboardButton("➡️ Следующий вопрос", callback_data=f"continue_{next_question_id}")],
    ]
    return InlineKeyboardMarkup(keyboard)

def get_question_text(question_id: int, user_id: int):
    """Форматирует текст вопроса"""
    progress = results_storage.get_completion_percentage(user_id)
    completed = len(results_storage.get_user_progress(user_id))
    
    text = (
        f"<b>Вопрос {question_id + 1}/{len(QUESTIONS)}</b>\n\n"
        f"{QUESTIONS[question_id]}\n\n"
        f"📊 <b>Прогресс:</b> {completed}/{len(QUESTIONS)} ({progress:.0f}%)"
    )
    
    return text

def get_answer_confirmation_text(question_id: int, answer: str, user_id: int):
    """Форматирует текст подтверждения ответа"""
    answer_text = "✅ Да" if answer == "yes" else "❌ Нет"
    progress = results_storage.get_completion_percentage(user_id)
    completed = len(results_storage.get_user_progress(user_id))
    
    text = (
        f"<b>Вопрос {question_id + 1}/{len(QUESTIONS)}</b>\n\n"
        f"{QUESTIONS[question_id]}\n\n"
        f"<b>Ваш ответ:</b> {answer_text}\n\n"
        f"📈 <b>Прогресс:</b> {completed}/{len(QUESTIONS)} ({progress:.0f}%)"
    )
    
    return text

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Отправляет приветственное сообщение и первый вопрос"""
    user = update.effective_user
    user_id = user.id
    
    # Проверяем, является ли пользователь администратором
    if is_admin(user_id):
        admin_text = (
            "👑 <b>Панель администратора</b>\n\n"
            "Вы являетесь администратором этого бота. "
            "Администраторы не участвуют в опросе, а только управляют статистикой.\n\n"
            "Используйте команду /admin для просмотра статистики и управления опросом."
        )
        await update.message.reply_text(admin_text, parse_mode='HTML')
        return
    
    # Проверяем прогресс пользователя
    completed = len(results_storage.get_user_progress(user_id))
    progress = results_storage.get_completion_percentage(user_id)
    
    welcome_text = (
        "📝 <b>Опрос практикума для воспитателей</b>\n\n"
        f"<i>Ваш прогресс: {completed}/{len(QUESTIONS)} вопросов ({progress:.0f}%)</i>\n\n"
        "Ответьте на вопросы, используя кнопки ниже.\n"
        "После ответа на вопрос в чате останется сообщение с вашим ответом.\n\n"
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
    
    # Отправляем первый вопрос
    question_text = get_question_text(next_question, user_id)
    await update.message.reply_text(
        text=question_text,
        reply_markup=get_question_keyboard(next_question),
        parse_mode='HTML'
    )

async def handle_answer(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обрабатывает нажатия кнопок"""
    query = update.callback_query
    user = update.effective_user
    user_id = user.id
    
    # Администраторы не могут участвовать в опросе
    if is_admin(user_id):
        await query.answer("❌ Администраторы не могут участвовать в опросе.", show_alert=True)
        return
        
    await query.answer()
    
    data = query.data
    question_id = int(data[1])
    answer = data.split("_")[1]
    
    # Обновляем результаты
    success = results_storage.add_vote(question_id, answer, user_id, user.username, user.first_name)
    
    if not success:
        await query.answer("❌ Произошла ошибка при сохранении ответа.", show_alert=True)
        return
    
    # Удаляем сообщение с вопросом (чтобы не было дублирования)
    await query.delete_message()
    
    # Отправляем сообщение с подтверждением ответа (фиксируем ответ в чате)
    confirmation_text = get_answer_confirmation_text(question_id, answer, user_id)
    await context.bot.send_message(
        chat_id=user_id,
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
        
        question_text = get_question_text(next_question, user_id)
        await context.bot.send_message(
            chat_id=user_id,
            text=question_text,
            reply_markup=get_question_keyboard(next_question),
            parse_mode='HTML'
        )
    else:
        # Все вопросы пройдены
        completion_text = (
            "🎉 <b>Поздравляем! Вы завершили опрос!</b>\n\n"
            "Спасибо за ваше время и участие. "
            "Ваши ответы помогут улучшить образовательный процесс."
        )
        
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
        try:
            csv_data = results_storage.export_to_csv()
            csv_file = io.BytesIO(csv_data.encode('utf-8'))
            csv_file.seek(0)
            csv_file.name = f"survey_results_{datetime.now().strftime('%Y%m%d_%H%M')}.csv"
            
            await context.bot.send_document(
                chat_id=user_id,
                document=csv_file,
                filename=csv_file.name,
                caption="📥 <b>Результаты опроса в CSV формате</b>\n\nИмпортируйте в Google Sheets для анализа.",
                parse_mode='HTML'
            )
        except Exception as e:
            logging.error(f"Error exporting CSV: {e}")
            await context.bot.send_message(
                chat_id=user_id,
                text="❌ <b>Ошибка при создании CSV файла</b>",
                parse_mode='HTML'
            )
    
    elif action == "admin_text":
        # Отправляем текстовый отчет
        try:
            text_report = results_storage.export_to_text_report()
            
            # Если отчет слишком длинный, разбиваем на части
            if len(text_report) > 4000:
                parts = [text_report[i:i+4000] for i in range(0, len(text_report), 4000)]
                for part in parts:
                    await context.bot.send_message(
                        chat_id=user_id,
                        text=f"<pre>{part}</pre>",
                        parse_mode='HTML'
                    )
            else:
                await context.bot.send_message(
                    chat_id=user_id,
                    text=f"<pre>{text_report}</pre>",
                    parse_mode='HTML'
                )
                
            # Также отправляем ссылку на веб-версию
            try:
                repl_slug = os.environ.get('REPL_SLUG', 'unknown')
                web_url = f"https://{repl_slug}.repl.co/export/html"
                await context.bot.send_message(
                    chat_id=user_id,
                    text=f"🔗 <b>Веб-версия HTML отчета:</b>\n{web_url}",
                    parse_mode='HTML'
                )
            except Exception as e:
                logging.error(f"Error sending web URL: {e}")
                
        except Exception as e:
            logging.error(f"Error generating text report: {e}")
            await context.bot.send_message(
                chat_id=user_id,
                text="❌ <b>Ошибка при создании отчета</b>",
                parse_mode='HTML'
            )
    
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
    
    # Администраторы не могут участвовать в опросе
    if is_admin(user_id):
        await update.message.reply_text(
            "👑 <b>Вы администратор</b>\n\n"
            "Администраторы не участвуют в опросе, а только управляют статистикой.\n"
            "Используйте команду /admin для просмотра статистики.",
            parse_mode='HTML'
        )
        return
    
    completed = len(results_storage.get_user_progress(user_id))
    progress = results_storage.get_completion_percentage(user_id)
    
    progress_text = (
        "📊 <b>Ваш прогресс:</b>\n\n"
        f"• Завершено вопросов: {completed}/{len(QUESTIONS)}\n"
        f"• Процент выполнения: {progress:.1f}%\n\n"
    )
    
    if completed == len(QUESTIONS):
        progress_text += "🎉 Вы ответили на все вопросы опроса!"
        await update.message.reply_text(progress_text, parse_mode='HTML')
    else:
        next_question = results_storage.get_next_question(user_id)
        progress_text += f"Следующий вопрос: {next_question + 1}/{len(QUESTIONS)}"
        
        # Кнопка для продолжения
        await update.message.reply_text(
            progress_text,
            reply_markup=get_continue_keyboard(next_question),
            parse_mode='HTML'
        )

async def handle_continue(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обрабатывает продолжение опроса"""
    query = update.callback_query
    user_id = update.effective_user.id
    
    # Администраторы не могут участвовать в опросе
    if is_admin(user_id):
        await query.answer("❌ Администраторы не могут участвовать в опросе.", show_alert=True)
        return
        
    await query.answer()
    
    # Получаем номер вопроса из callback_data
    question_id = int(query.data.split("_")[1])
    
    # Удаляем сообщение с прогрессом
    await query.delete_message()
    
    # Отправляем вопрос
    question_text = get_question_text(question_id, user_id)
    await context.bot.send_message(
        chat_id=user_id,
        text=question_text,
        reply_markup=get_question_keyboard(question_id),
        parse_mode='HTML'
    )

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
    logging.info(f"Администраторы: {admin_ids}")
    application.run_polling(drop_pending_updates=True)

if __name__ == "__main__":
    # Запускаем Flask в отдельном потоке для Replit
    from threading import Thread
    flask_thread = Thread(target=lambda: app.run(host='0.0.0.0', port=PORT, debug=False, use_reloader=False))
    flask_thread.daemon = True
    flask_thread.start()
    
    # Запускаем бота в основном потоке
    main()
