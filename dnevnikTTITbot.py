import logging
import httpx
import base64
import hashlib
from aiogram import Bot, Dispatcher, types
from aiogram.dispatcher.filters import Command
import aiosqlite
import json
import locale
BOT_TOKEN = 'ТОКЕН_БОТА'
bot = Bot(token=BOT_TOKEN)
LOGIN_URL = 'https://poo.tomedu.ru/services/security/login'
dp = Dispatcher(bot)
logging.basicConfig(level=logging.INFO)
def hash_and_base64_encode(password):
    password_bytes = password.encode('utf-8')
    sha256 = hashlib.sha256()
    sha256.update(password_bytes)
    password_hash_bytes = sha256.digest()
    password_base64 = base64.b64encode(password_hash_bytes).decode('utf-8')
    return password_base64

async def add_user_to_db(user_id, username):
    async with aiosqlite.connect("users.db") as db:
        cursor = await db.cursor()
        user_exists = await check_user_in_db(username)
        if not user_exists:
            await cursor.execute("INSERT INTO users (user_id, username) VALUES (?, ?)", (user_id, username))
            await db.commit()
        await cursor.close()

async def check_user_in_db(username):
    async with aiosqlite.connect("users.db") as db:
        cursor = await db.cursor()
        await cursor.execute("SELECT username FROM users WHERE username=?", (username,))
        user_data = await cursor.fetchone()
        return user_data is not None

async def extract_student_id(response):
    try:
        data = response.json()
        print("Ответ на запрос авторизации:", data)

        
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

@dp.message_handler(Command('start'))
async def start(message: types.Message):
    await message.reply("Привет! Для доступа к расписанию, введите свой логин и пароль через пробел.\n"
                        "Пример: Савиных162 1234567\n"
                        f"Телеграм автора @vitalik_savinih")
@dp.message_handler(lambda message: message.text.count(' ') == 1)
async def process_login_password(message: types.Message):
    login, password = message.text.split()
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
            student_id = await extract_student_id(response)
            print(f"student_id после извлечения: {student_id}")

            if not student_id:
                await message.reply("Не удалось получить student_id. Попробуйте позже или проверьте данные.")
            current_date = datetime.date.today()
            end_date = current_date + datetime.timedelta(days=10)
            schedule_url = f"https://poo.tomedu.ru/services/students/{student_id}/lessons/{current_date}/{end_date}"
            if response.status_code != 200:
                await message.reply("Авторизация не удалась. Проверьте логин и пароль и попробуйте снова.")
                return
            current_date = datetime.date.today()
            end_date = current_date + datetime.timedelta(days=10)
            schedule_url = f"https://poo.tomedu.ru/services/students/{student_id}/lessons/{current_date}/{end_date}"
            response = await client.get(schedule_url)
            if response.status_code == 200:
                schedule_data = json.loads(response.text)
                if schedule_data:
                    messages = process_schedule_data(schedule_data)
                    if messages:
                        await message.reply('\n'.join(messages))
                    else:
                        await message.reply("На данной странице нет расписания.")
                else:
                    await message.reply("Расписание не найдено.")
                    print("Запрос на получение расписания:")
                    print(f"Request URL: {schedule_url}")
                    print(f"Request Method: GET")
            else:
                await message.reply("Не удалось загрузить расписание. Попробуйте позже.")

        except Exception as e:
            error_message = f"Произошла ошибка: {str(e)}"
            await message.reply(error_message)
import datetime
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
                    message += f"Время: {lesson['startTime']} - {lesson['endTime']}\n"
                    message += f"Занятие: {lesson['name']}\n"
                    timetable = lesson.get("timetable", {})
                    if timetable:
                        classroom = timetable.get("classroom", {})
                        teacher = timetable.get("teacher", {})
                        message += f"Аудитория: {classroom.get('name', 'Не указана')}\n"
                        message += f"Преподаватель: {teacher.get('firstName', 'Не указан')} {teacher.get('lastName', 'Не указан')} {teacher.get('middleName', 'Не указан')}\n"
                    message += "\n"
            messages.append(message)
    print(schedule_data)
    return messages
if __name__ == '__main__':
    from aiogram import executor
    executor.start_polling(dp, skip_updates=True)
