import logging
from aiogram import types
from aiogram.dispatcher.middlewares import BaseMiddleware
from aiogram import Bot, Dispatcher, types
from aiogram.dispatcher.filters import Command, Text
from aiogram.contrib.middlewares.logging import LoggingMiddleware
import httpx
import base64
import hashlib
import json
import locale
import datetime
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from aiogram import types

bot = Bot(token="")
dp = Dispatcher(bot)
dp.middleware.setup(LoggingMiddleware())

student_ids = {}

channel_username = "@vitalik_savinih"

LOGIN_URL = 'https://poo.tomedu.ru/services/security/login'

async def save_cookies(response, user_id):
    if user_id not in sessions:
        sessions[user_id] = httpx.AsyncClient()
    cookies = response.cookies
    sessions[user_id].cookies.update(cookies)
async def fetch_schedule(schedule_url, user_id):
    try:
        response = await sessions[user_id].get(schedule_url)
        response.raise_for_status()
        return response
    except Exception as e:
        print(f"Ошибка при загрузке расписания: {str(e)}")
        return None
def process_schedule_data(schedule_data):
    messages = []
    locale.setlocale(locale.LC_TIME, 'ru_RU.UTF-8')
    for day in schedule_data:
        date = datetime.datetime.strptime(day["date"][:-1], "%Y-%m-%dT%H:%M:%S.%f")
        formatted_date = date.strftime("%Y-%m-%d (%A)").capitalize()
        lessons = day.get("lessons", [])
        if lessons:
            message = f"Дата: {formatted_date}\n"
            for lesson in lessons:
                if "name" in lesson:
                    message += f"\nВремя: {lesson['startTime']} - {lesson['endTime']}\n"
                    message += f"Занятие: {lesson['name']}\n"
                    timetable = lesson.get("timetable", {})
                    if timetable:
                        classroom = timetable.get("classroom", {})
                        teacher = timetable.get("teacher", {})
                        message += f"Аудитория: {classroom.get('name', 'Не указана')}\n"
                        message += f"Преподаватель: {teacher.get('lastName', 'Не указан')} {teacher.get('firstName', 'Не указан')} {teacher.get('middleName', 'Не указан')}\n"
            messages.append(message)
    return messages

def hash_and_base64_encode(password):
    password_bytes = password.encode('utf-8')
    sha256 = hashlib.sha256()
    sha256.update(password_bytes)
    password_hash_bytes = sha256.digest()
    password_base64 = base64.b64encode(password_hash_bytes).decode('utf-8')
    return password_base64

async def extract_student_id(response):
    try:
        data = response.json()
        for key, value in data.get('tenants', {}).items():
            if key.startswith('SPO_') and 'studentRole' in value:
                student_id = value['studentRole']['id']
                print(f"Извлеченный studentID для {key}: {student_id}")
                return student_id

        print("Отсутствует ключ 'studentRole' в данных для всех значений SPO_XX.")
        return None

    except Exception as e:
        print(f"Ошибка при извлечении student_id: {str(e)}")
        return None
async def add_user_to_db(user_id, student_id):
    student_ids[user_id] = student_id

@dp.message_handler(Command('start'))
async def start(message: types.Message):
    if await check_subscription(message):
        await message.reply("Вы уже подписаны на наш канал. Для доступа к расписанию, введите свой логин и пароль через пробел.\n"
                            "Пример: Савиных162 1234567")
    else:
        markup = types.ReplyKeyboardMarkup(resize_keyboard=True)
        item_subscribe = types.KeyboardButton("Подписаться на автора")
        markup.add(item_subscribe)
        await message.reply("Теперь введи свой логин и пароль")
class SubscriptionMiddleware(BaseMiddleware):
    async def on_pre_process_message(self, message: types.Message, data: dict):
        if message.text:
            subscribed = await check_subscription(message.from_user.id)
            print(f"User {message.from_user.id} is subscribed: {subscribed}")
            if not subscribed:
                data['subscribed'] = False
                await message.answer("Для использования бота, подпишитесь на наш канал @vitalik_savinih, если не интересно закиньте в архив  и выполните команду /start снова.")
            else:
                data['subscribed'] = True
dp.middleware.setup(SubscriptionMiddleware())

@dp.message_handler(Command('subscribe'))
async def subscribe(message: types.Message):
    user_id = message.from_user.id
    try:
        chat_member = await bot.get_chat_member(chat_id=channel_username, user_id=user_id)
        if chat_member.status == "member" or chat_member.status == "administrator":
            # Пользователь уже является подписчиком канала
            await message.reply("Вы уже подписаны на наш канал.")
        else:
            subscribe_markup = InlineKeyboardMarkup()
            subscribe_markup.add(InlineKeyboardButton("Подписаться на канал", "https://t.me/vitalik_savinih"))
            await message.reply("Подпишитесь на наш канал, если не интересно закиньте в архив  и выполните команду /start снова.",
                                reply_markup=subscribe_markup)
    except Exception as e:
        print(f"Ошибка при проверке подписки пользователя: {str(e)}")
@dp.message_handler(lambda message: True)
async def process_text_message(message: types.Message):
    user_id = message.from_user.id
    user_text = message.text
    if user_id in student_ids:
        subscribed = await check_subscription(user_id)
        if not subscribed:
            return
        if user_text == "Расписание":
            await get_schedule(message)
        elif user_text == "Подписаться на автора":
            await message.reply("Подпишитесь на автора по ссылке: https://t.me/vitalik_savinih")
        elif user_text == "Оценки":
            await get_marks(message)
        else:
            await message.reply("Используйте кнопки меню или введите 'Оценки' или 'Расписание'.")
    else:
        login_password = user_text.split()
        if len(login_password) == 2:
            login, password = login_password
            async with httpx.AsyncClient() as client:
                try:
                    login_data = {
                        'login': login,
                        'password': hash_and_base64_encode(password),
                        'isRemember': True,
                    }

                    headers = {
                        'Content-Type': 'application/json',
                    }
                    response = await client.post(LOGIN_URL, json=login_data, headers=headers)
                    await save_cookies(response, user_id)  # Сохраняем куки в сессии пользователя

                    student_id = await extract_student_id(response)

                    if student_id:
                        # Сохраняем student_id для данного пользователя
                        await add_user_to_db(user_id, student_id)
                        keyboard = generate_menu_keyboard()
                        await message.reply(f"Авторизация успешна! "
                                            "Теперь ты можешь посмотреть свои оцеки или расписание :)",
                                            reply_markup=keyboard)
                    else:
                        await message.reply("Не удалось получить student_id. Проверьте логин и пароль и попробуйте снова.")
                except Exception as e:
                    error_message = f"Произошла ошибка: {str(e)}"
                    await message.reply(error_message)
        else:
            await message.reply("Неправильный формат ввода. Введите логин и пароль через пробел.")
async def is_subscribed(user_id):
    try:
        chat_member = await bot.get_chat_member(chat_id=channel_username, user_id=user_id)
        return chat_member.status == "member" or chat_member.status == "administrator"
    except Exception as e:
        logging.error(f"Ошибка при проверке подписки пользователя: {str(e)}")
        return False

@dp.message_handler(lambda message: message.text.lower() == "оценки" and is_subscribed(message.from_user.id))
async def get_marks(message: types.Message):
    user_id = message.from_user.id
    student_id = student_ids.get(user_id)

    if student_id:
        grades_url = f"https://poo.tomedu.ru/services/reports/current/performance/{student_id}"
        response = await fetch_grades(grades_url, user_id)

        if response and response.status_code == 200:
            grades_data = json.loads(response.text)
            if grades_data:
                grades_text = generate_grades_text(grades_data)
                await message.answer(grades_text)
            else:
                await message.answer("Оценки не найдены.")
        else:
            await message.answer("Не удалось загрузить оценки. Попробуйте позже.")
    else:
        await message.answer("Сначала авторизуйтесь, чтобы получить оценки.")

async def check_subscription(user_id):
    try:
        chat_member = await bot.get_chat_member(chat_id=channel_username, user_id=user_id)
        if chat_member.status not in ("member", "administrator", "creator"):
            return False

        return True  # Возвращаем True, если пользователь подписан

    except Exception as e:
        logging.error(f"Ошибка при проверке подписки пользователя: {str(e)}")
        return False

async def fetch_grades(grades_url, user_id):
    try:
        response = await sessions[user_id].get(grades_url)
        response.raise_for_status()
        return response
    except Exception as e:
        print(f"Ошибка при загрузке оценок: {str(e)}")
        return None
def generate_grades_text(grades_data):
    subject_grades = grades_data.get("daysWithMarksForSubject", [])

    if subject_grades:
        grades_text = "Оценки:\n"
        for subject in subject_grades:
            subject_name = subject.get("subjectName", "Не указано")
            days_with_marks = subject.get("daysWithMarks", [])
            if days_with_marks:
                marks = []
                for day_with_marks in days_with_marks:
                    absence_type = day_with_marks.get("absenceType", None)
                    mark_values = day_with_marks.get("markValues", [])
                    if mark_values:
                        marks.extend(mark_values)
                    elif absence_type:
                        marks.append("Н")
                # Заменяем словесные оценки на числовые
                marks = [grade_to_number(mark) for mark in marks]
                if marks:
                    grades_text += f"{subject_name} {', '.join(marks)}\n"
                else:
                    grades_text += f"{subject_name}, Оценки отсутствуют\n"
        return grades_text
    else:
        return "Данные об оценках не найдены."
def grade_to_number(grade):
    if grade == "Five":
        return "5"
    elif grade == "Four":
        return "4"
    elif grade == "Three":
        return "3"
    elif grade == "Two":
        return "2"
    elif grade == "One":
        return "1"
    else:
        return grade

@dp.message_handler(lambda message: message.text.lower() == "расписание" and is_subscribed(message.from_user.id))
async def get_schedule(message: types.Message):
    user_id = message.from_user.id
    student_id = student_ids.get(user_id)

    if student_id:
        await send_schedule(message, student_id)
    else:
        await message.answer("Сначала авторизуйтесь, чтобы получить расписание.")
async def send_schedule(message: types.Message, student_id: int):
    current_date = datetime.date.today()
    end_date = current_date + datetime.timedelta(days=10)
    schedule_url = f"https://poo.tomedu.ru/services/students/{student_id}/lessons/{current_date}/{end_date}"
    response = await fetch_schedule(schedule_url, message.from_user.id)  # Передаем user_id

    if response and response.status_code == 200:
        schedule_data = json.loads(response.text)
        if schedule_data:
            messages = process_schedule_data(schedule_data)
            if messages:
                for message_text in messages:
                    await message.answer(message_text)
            else:
                await message.answer("На данной странице нет расписания.")
        else:
            await message.answer("Расписание не найдено.")
    else:
        await message.answer("Не удалось загрузить расписание. Попробуйте позже.")
def generate_menu_keyboard():
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True)
    item_schedule = types.KeyboardButton("Расписание")
    item_grades = types.KeyboardButton("Оценки")

    markup.add(item_schedule, item_grades)
    return markup
if __name__ == '__main__':
    try:
        from aiogram import executor
        sessions = {}
        executor.start_polling(dp, skip_updates=True)
    finally:
        for session in sessions.values():
            session.aclose()
