import base64
import requests
import json
import aiohttp
import logging
import csv
from aiogram import Bot, Dispatcher, types
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from apscheduler.schedulers.asyncio import AsyncIOScheduler


import logging
from gigachat import GigaChat
from langchain.schema import HumanMessage, SystemMessage
from langchain_gigachat.chat_models import GigaChat

import tokens as tkk



logging.basicConfig(level=logging.INFO)
API_TOKEN = tkk.first
bot = Bot(token=API_TOKEN)



GigaChatKey = tkk.second

llm = GigaChat(
    credentials=GigaChatKey,
    scope="GIGACHAT_API_PERS",
    model="GigaChat",
    verify_ssl_certs=False, # Отключает проверку наличия сертификатов НУЦ Минцифры
    streaming=False,
)

# Регистрация роутера
dp = Dispatcher()
scheduler = AsyncIOScheduler()


class Form(StatesGroup):
    waiting_for_name = State()
    waiting_for_age = State()
    default_state = State()
    waiting_for_review = State()
    advice = State()
    monitoring = State()

# Работа с bd
def check_registration(user_tag):
    with open('bd/reg.csv', mode='r', newline='', encoding='utf-8') as file:
        reader = csv.reader(file)
        print(user_tag)
        for row in reader:
            if row[0] == user_tag:
                return True
    return False


def register_user(user_tag, user_name, age, chat_id):
    with open('bd/reg.csv', mode='a', newline='', encoding='utf-8') as file:
        writer = csv.writer(file)
        writer.writerow([user_tag, user_name, age, chat_id])

    with open("bd/user_message/" + user_tag + ".csv", mode='a', newline='', encoding='utf-8') as file1:
        pass

    with open("bd/user_rewiew/" + user_tag + ".csv", mode='a', newline='', encoding='utf-8') as file2:
        pass


def message_in_bd(user_tag, message):
    with open("bd/user_message/" + user_tag + ".csv", mode='a', newline='', encoding='utf-8') as file:
        writer = csv.writer(file)
        writer.writerow([message])


def review_in_bd(user_tag, message):
    with open("bd/user_rewiew/" + user_tag + ".csv", mode='a', newline='', encoding='utf-8') as file:
        writer = csv.writer(file)
        writer.writerow([message])


def get_access_token():
    url = "https://ngw.devices.sberbank.ru:9443/api/v2/oauth"
    payload = {
        'scope': 'GIGACHAT_API_PERS'
    }
    headers = {
        'Content-Type': 'application/x-www-form-urlencoded',
        'Accept': 'application/json',
        'RqUID': '0be5f38c-e863-48c2-8495-93f307cbadcd',
        'Authorization': 'Basic <ZTcyM2EzZmUtYjFlYi00ODVkLThjYmUtZGQ5ZTZmODZkZmJlOjYwMTg4NDhjLTFhZDktNDViNC05YjE5LTU0OWE3MWY3Njg3MQ==>'
    }

    response = requests.post(url, headers=headers, data=payload, verify=False)
    if response.status_code == 200:
        return response.json().get('access_token')
    else:
        print("Error getting access token:", response.text)
        return None


async def send_1(user_tag, message: types.Message):
    message_in_bd(user_tag, message.text)  
    user_message = message.text  
    
    messages_questions = [
        f"Дай мне советы по следующим экологически чистым покупкам: '{user_message}'."
    ]

    res = llm.invoke(messages_questions)
    chat_answer = res.content  
    await message.answer(chat_answer)  


async def send_2(user_tag, message: types.Message):
    message_in_bd(user_tag, message.text)  # Записываем сообщение в БД
    user_message = message.text  


    with open('bd/user_message/' + user_tag + '.csv', mode='r', newline='', encoding='utf-8') as file:
        reader = csv.reader(file)
        user_data = ""
        for row in reader:
            user_data += row[0] + " "

    consumption_question = f"проконтролируй потребление ресурсов с точки зрения экологии: '{user_message} учитывая данны:'{user_data}' (если данные непонятны или некорректны проигнорируй их)'?"

    
    consumption_response = llm.invoke([consumption_question])

    consumption_answer = consumption_response.content  
    await message.answer("Также, " + consumption_answer)  

    disposal_question = f"Что ты можешь посоветовать по утилизации остаточных материалов от покупки отвечай кратко: '{user_message}'?"
    disposal_response = llm.invoke([disposal_question])
    disposal_answer = disposal_response.content  
    await message.answer("Кроме того, " + disposal_answer)  


# start и регистрация
@dp.message(Command("start"))
async def cmd_start(message: types.Message, state: FSMContext):

    user = message.from_user
    verdict = check_registration(user.username)

    if not verdict:
        scheduler.add_job(send_reminder, 'interval', minutes=1, args=[message.chat.id])
        scheduler.start()
        await message.answer("Вы не зарегистрированы. Введите свое имя")
        await state.set_state(Form.waiting_for_name)
    else:
        await message.answer("Готов к работе!")


@dp.message(Form.waiting_for_name)
async def process_name(message: types.Message, state: FSMContext):
    user_name = message.text
    await state.update_data(user_name=user_name)
    await message.answer("Введите ваш возвраст.")
    await state.set_state(Form.waiting_for_age)


@dp.message(Form.waiting_for_age)
async def process_age(message: types.Message, state: FSMContext):
    user_age = message.text
    if not user_age.isdigit():
        await message.answer("Некторектные данные! Повтори.")
        await state.set_state(Form.waiting_for_age)
    else:
        user_data = await state.get_data()
        user_name = user_data.get('user_name')
        user_tag = message.from_user.username or message.from_user.id

        register_user(user_tag, user_name, user_age, message.chat.id)
        await message.answer(
            f'Ты зарегистрирован как {user_name}, возвраст: {user_age}. Теперь можешь отправить свой запрос.')
        await state.set_state(Form.advice)


# review
@dp.message(Command("review"))
async def cmd_review(message: types.Message, state: FSMContext):
    if not check_registration(message.from_user.username):
        await message.answer("Вы не зарегистрированы. Используйте /start")
    else:
        await message.answer("Напиши свой отзыв:!")
        await state.set_state(Form.waiting_for_review)

@dp.message(Form.waiting_for_review)
async def process_review(message: types.Message, state: FSMContext):
    review = message.text
    review_in_bd(message.from_user.username, review)
    await message.answer("Спасибо за отклик!")
    await state.set_state(Form.advice)


@dp.message(Command("advice"))
async def cmd_review(message: types.Message, state: FSMContext):
    user = message.from_user
    verdict = check_registration(user.username)

    if not verdict:
        await message.answer("Вы не зарегистрированы. Используйте /start")
    else:
        await message.answer("Включен режим советов.")
        await state.set_state(Form.advice)

@dp.message(Command("monitoring"))
async def cmd_review(message: types.Message, state: FSMContext):
    user = message.from_user
    verdict = check_registration(user.username)

    if not verdict:
        await message.answer("Вы не зарегистрированы. Используйте /start")
    else:
        await message.answer("Включен режим мониторинг.")
        await state.set_state(Form.monitoring)

@dp.message(Form.advice)
async def process_message(message: types.Message, state: FSMContext):
    user = message.from_user
    verdict = check_registration(user.username)

    if not verdict:
        await message.answer("Вы не зарегистрированы. Используйте /start")
    else:
        await send_1(user.username, message)     

@dp.message(Form.monitoring)
async def process_message(message: types.Message, state: FSMContext):
    user = message.from_user
    verdict = check_registration(user.username)

    if not verdict:
        await message.answer("Вы не зарегистрированы. Используйте /start")
    else:
        await send_2(user.username, message) 

@dp.message()
async def process_message(message: types.Message, state: FSMContext):
    user = message.from_user
    verdict = check_registration(user.username)

    if not verdict:
        await message.answer("Вы не зарегистрированы. Используйте /start")
    else:
        await state.set_state(Form.advice)
        await send_1(user.username, message) 

# Напоминания
async def send_reminder(chat_id):
    await bot.send_message(chat_id, "Напиши новый отзыв об опыте использования бота: /review")


if __name__ == '__main__':
    dp.run_polling(bot, skip_updates=True)
