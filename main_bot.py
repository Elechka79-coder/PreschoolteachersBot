import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, ContextTypes

# Настройки
BOT_TOKEN = "ВАШ_ТОКЕН_ОТ_BOTFATHER"
QUESTIONS = [
    "1. Рабочая группа Минпросвещения разработала Программу просвещения по запросу родителей. Программа просвещения родителей – это нормативный документ, по которому должны работать все детские сады.",
    "2. Один из принципов просвещения – приоритет семьи в вопросах воспитания, обучения и развития.",
    "3. Основной адресат Программы просвещения – педагоги дошкольных образовательных организаций.",
    "4. Никто, кроме воспитателей, не может просвещать родителей воспитанников.",
    "5. Программа просвещения родителей – это новый дополнительный пункт в ФОП ДО.",
    "6. Тематика и формы взаимодействия и педагогического просвещения родителей, которые содержит Программа, – примерные. Педагоги могут их самостоятельно преобразовывать."
]

# Хранилище результатов (в памяти)
results = {i: {"yes": 0, "no": 0} for i in range(len(QUESTIONS))}

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Отправляет приветственное сообщение и первый вопрос"""
    await update.message.reply_text(
        "Примите участие в опросе. Ответьте на вопросы:",
        reply_markup=get_question_keyboard(0)
    )

def get_question_keyboard(question_id):
    """Создает клавиатуру с кнопками Да/Нет для вопроса"""
    keyboard = [
        [InlineKeyboardButton("✅ Да", callback_data=f"q{question_id}_yes")],
        [InlineKeyboardButton("❌ Нет", callback_data=f"q{question_id}_no")],
    ]
    return InlineKeyboardMarkup(keyboard)

def get_results_text(question_id):
    """Форматирует текст вопроса с текущей статистикой"""
    return (
        f"{QUESTIONS[question_id]}\n\n"
        f"📊 Статистика ответов:\n"
        f"✅ Да: {results[question_id]['yes']}\n"
        f"❌ Нет: {results[question_id]['no']}"
    )

async def handle_answer(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обрабатывает нажатия кнопок"""
    query = update.callback_query
    await query.answer()

    # Парсим данные из callback_data
    data = query.data
    question_id = int(data[1])  # Извлекаем номер вопроса
    answer = data.split("_")[1]  # Извлекаем ответ

    # Обновляем результаты
    results[question_id][answer] += 1

    # Обновляем сообщение с новой статистикой
    await query.edit_message_text(
        text=get_results_text(question_id),
        reply_markup=get_question_keyboard(question_id)
    )

if __name__ == "__main__":
    # Настройка приложения
    application = Application.builder().token(BOT_TOKEN).build()

    # Регистрация обработчиков
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CallbackQueryHandler(handle_answer))

    # Запуск бота
    application.run_polling()
