import os
import logging
from aiogram import Bot, Dispatcher, types
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from aiogram.utils import executor
import asyncio
import concurrent.futures
from db import connect_db
from parsing import parse_habr
import dotenv

dotenv.load_dotenv()

logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)

TOKEN = os.environ.get('TELEGRAM_TOKEN')

bot = Bot(token=TOKEN)
dp = Dispatcher(bot)

@dp.message_handler(commands=['start'])
async def start(message: types.Message):
    await message.reply('Используйте /search <запрос>, чтобы искать вакансии.\nДля остального функционала можно задействовать /help')

@dp.message_handler(commands=['help'])
async def help_command(message: types.Message):
    await message.reply('Краткая сводка по командам\n/start - запуск/перезапуск бота\n/search <запрос> - поиск вакансий по запросу\n/recent - вывод 5 случайных вакансий\n/count - вывод общего кол-ва вакансий в бд\n/grafic - вывод на выбор режима раб. дня\n/search_company - поиск вакансий по компании из бд\n/search_vacancy - поиск вакансий по названию вакансии из бд')

@dp.message_handler(commands=['search'])
async def search(message: types.Message):
    query = message.get_args()
    logging.info(f"Получен запрос для поиска: {query}")
    if not query:
        await message.reply('Пожалуйста, введите запрос после команды /search.')
        return

    conn = connect_db()
    with conn.cursor() as cur:
        cur.execute("SELECT COUNT(*) FROM vacancies;")
        initial_count = cur.fetchone()[0]
    conn.close()

    await message.reply(f'Ищу вакансии для: {query}')
    await run_parse_habr(query)
    await message.reply('Поиск завершен. Проверьте свою базу данных.')

    conn = connect_db()
    with conn.cursor() as cur:
        cur.execute("SELECT company, vacancy, location, salary, skills, link FROM vacancies WHERE id > %s ORDER BY id LIMIT 5;", (initial_count,))
        rows = cur.fetchall()
    conn.close()

    if not rows:
        await message.reply('Новые вакансии не найдены.')
    else:
        await message.reply('Ниже представлены 5 новых вакансий:')
        for row in rows:
            await message.reply(f'Компания: {row[0]}\nВакансия: {row[1]}\nМестоположение: {row[2]}\nЗарплата: {row[3]}\nСкиллы: {row[4]}\nСсылка: {row[5]}\n')

async def run_parse_habr(query: str):
    loop = asyncio.get_event_loop()
    executor = concurrent.futures.ThreadPoolExecutor()
    await loop.run_in_executor(executor, parse_habr, query)

@dp.message_handler(commands=['recent'])
async def recent(message: types.Message):
    conn = connect_db()
    with conn.cursor() as cur:
        cur.execute("SELECT company, vacancy, location, salary, skills, link FROM vacancies ORDER BY RANDOM() LIMIT 5;")
        rows = cur.fetchall()
    conn.close()

    if not rows:
        await message.reply('Вакансии не найдены.')
    else:
        for row in rows:
            await message.reply(f'Компания: {row[0]}\nВакансия: {row[1]}\nМестоположение: {row[2]}\nЗарплата: {row[3]}\nСкиллы: {row[4]}\nСсылка: {row[5]}\n')

@dp.message_handler(commands=['count'])
async def count(message: types.Message):
    conn = connect_db()
    with conn.cursor() as cur:
        cur.execute("SELECT COUNT(*) FROM vacancies;")
        count = cur.fetchone()[0]
    conn.close()
    await message.reply(f'Общее количество вакансий в базе данных: {count}')

@dp.message_handler(commands=['grafic'])
async def grafic(message: types.Message):
    keyboard = InlineKeyboardMarkup(row_width=2)
    buttons = [
        InlineKeyboardButton(text="Неполный рабочий день", callback_data='part_time'),
        InlineKeyboardButton(text="Полный рабочий день", callback_data='full_time')
    ]
    keyboard.add(*buttons)
    await message.reply("Выберите график работы:", reply_markup=keyboard)

@dp.callback_query_handler(lambda c: c.data in ['part_time', 'full_time'])
async def button(callback_query: types.CallbackQuery):
    query_data = callback_query.data

    conn = connect_db()
    with conn.cursor() as cur:
        if query_data == 'part_time':
            cur.execute("SELECT COUNT(*) FROM vacancies WHERE location ILIKE '%Неполный рабочий день%';")
        elif query_data == 'full_time':
            cur.execute("SELECT COUNT(*) FROM vacancies WHERE location ILIKE '%Полный рабочий день%';")
        count = cur.fetchone()[0]
    conn.close()

    await bot.answer_callback_query(callback_query.id)
    await bot.edit_message_text(text=f'Количество вакансий с графиком "{query_data}": {count}',
                                chat_id=callback_query.message.chat.id,
                                message_id=callback_query.message.message_id)

@dp.message_handler(commands=['search_company'])
async def search_by_company(message: types.Message):
    company_name = message.get_args()
    logging.info(f"Получен запрос для поиска по компании: {company_name}")
    if not company_name:
        await message.reply('Пожалуйста, введите название компании после команды /search_company.')
        return

    conn = connect_db()
    with conn.cursor() as cur:
        cur.execute("SELECT company, vacancy, location, salary, skills, link FROM vacancies WHERE company ILIKE %s ORDER BY RANDOM() LIMIT 5;", (f"%{company_name}%",))
        rows = cur.fetchall()
    conn.close()

    if not rows:
        await message.reply(f'Вакансии компании "{company_name}" не найдены.')
    else:
        for row in rows:
            await message.reply(f'Компания: {row[0]}\nВакансия: {row[1]}\nМестоположение: {row[2]}\nЗарплата: {row[3]}\nСкиллы: {row[4]}\nСсылка: {row[5]}\n')

@dp.message_handler(commands=['search_vacancy'])
async def search_by_vacancy(message: types.Message):
    vacancy_query = message.get_args()
    logging.info(f"Получен запрос для поиска по вакансии: {vacancy_query}")
    if not vacancy_query:
        await message.reply('Пожалуйста, введите название вакансии после команды /search_vacancy.')
        return

    conn = connect_db()
    with conn.cursor() as cur:
        cur.execute("SELECT company, vacancy, location, salary, skills, link FROM vacancies WHERE vacancy ILIKE %s ORDER BY RANDOM() LIMIT 5;", (f"%{vacancy_query}%",))
        rows = cur.fetchall()
    conn.close()

    if not rows:
        await message.reply(f'Вакансии по запросу "{vacancy_query}" не найдены.')
    else:
        for row in rows:
            await message.reply(f'Компания: {row[0]}\nВакансия: {row[1]}\nМестоположение: {row[2]}\nЗарплата: {row[3]}\nСкиллы: {row[4]}\nСсылка: {row[5]}\n')

if __name__ == '__main__':
    executor.start_polling(dp, skip_updates=True)
