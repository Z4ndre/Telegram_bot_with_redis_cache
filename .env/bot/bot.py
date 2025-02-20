import asyncio
import logging
import os
import csv
from aiogram import Bot, Dispatcher, types
from aiogram.enums import ParseMode
from aiogram.filters import CommandStart, Command
from aiogram.types import Message, FSInputFile
from aiogram.fsm.context import FSMContext
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.fsm.state import State, StatesGroup
from aiohttp import ClientSession
from dotenv import load_dotenv

load_dotenv()

load_dotenv()

API_URL = "http://localhost:8000"
bot = Bot(token=os.getenv("BOT_TOKEN"))
ADMIN_PASSWORD = "admin"
storage = MemoryStorage()
dp = Dispatcher(storage=storage)

class UserStates(StatesGroup):
    EDIT_SELF = State()
    EDIT_USER = State()
    AWAITING_ADMIN_PASSWORD = State()
    AWAITING_EDIT_USERNAME = State()
    AWAITING_EDIT_NAME = State()

class AdminEditUser(StatesGroup):
    AWAIT_USERNAME = State()
    AWAIT_NEW_NAME = State()

async def make_request(method: str, url: str, username: str, data=None):
    headers = {
        "X-Username": username,
        "Content-Type": "application/json"  # Добавлено
    }
    async with ClientSession() as session:
        async with session.request(method, f"{API_URL}{url}", json=data, headers=headers) as resp:
            return await resp.json(), resp.status

@dp.message(CommandStart())
async def command_start_handler(message: Message, state: FSMContext):
    username = message.from_user.username
    if not username:
        await message.answer("Установите username в Telegram для регистрации!")
        return
    
    response, status = await make_request("GET", "/users/me", username)
    if status == 404:
        user_data = {"full_name": message.from_user.full_name}
        await make_request("POST", "/users/", username, user_data)
        await message.answer(f"Вы успешно зарегистрированы как {message.from_user.full_name}!")
    else:
        await message.answer("Вы уже зарегистрированы.")

@dp.message(Command("edit_self"))
async def edit_self(message: types.Message, state: FSMContext):
    await message.answer("Введите новое имя:")
    await state.set_state(UserStates.EDIT_SELF)

@dp.message(UserStates.EDIT_SELF)
async def process_edit_self(message: types.Message, state: FSMContext):
    username = message.from_user.username
    new_name = message.text.strip()
    response, status = await make_request("PUT", "/users/me", username, {"full_name": new_name})
    if status == 200:
        await message.answer(f"Имя обновлено на: {new_name}")
    else:
        await message.answer("Ошибка обновления профиля")
    await state.clear()

@dp.message(Command("delete_self"))
async def delete_self(message: types.Message):
    username = message.from_user.username
    response, status = await make_request("DELETE", "/users/me", username)
    if status == 200:
        await message.answer("Ваш профиль удалён")
    else:
        await message.answer("Ошибка удаления профиля")

@dp.message(Command("add_admin"))
async def add_admin_command(message: types.Message, state: FSMContext):
    await message.answer("Введите пароль администратора:")
    await state.set_state(UserStates.AWAITING_ADMIN_PASSWORD)

@dp.message(UserStates.AWAITING_ADMIN_PASSWORD)
async def process_admin_password(message: types.Message, state: FSMContext):
    username = message.from_user.username
    admin_password = message.text.strip()


    #print("Полученный пароль админа:",admin_password)
    #print(type(admin_password))


    
    if admin_password == ADMIN_PASSWORD:
        response, status = await make_request("POST", "/add_admin", username, {"password": ADMIN_PASSWORD})
        if status == 200:
            await message.answer("Вы теперь администратор.")
        else:
            await message.answer(f"Ошибка: не удалось назначить администратора. Status ошибки:{status}")
    else:
        await message.answer("Ошибка: неверный пароль.")
    
    await state.clear()

@dp.message(Command("all_users"))
async def export_users_csv(message: types.Message):
    username = message.from_user.username

    headers = {
        "X-Username": username
    }
    
    async with ClientSession() as session:
        async with session.get(f"{API_URL}/admin/users/csv", headers=headers) as resp:
            if resp.status == 200:
                file_path = "users.csv"
                with open(file_path, "wb") as f:
                    f.write(await resp.read())  # Читаем бинарные данные
            
                await message.answer_document(FSInputFile(file_path), caption="Список пользователей в формате CSV.")
                os.remove(file_path)  # Удаляем локальный файл после отправки
            else:
                await message.answer("Ошибка: у вас нет прав для выполнения этой команды.")


@dp.message(Command("delete_user"))
async def delete_user(message: types.Message):
    username = message.from_user.username
    parts = message.text.split()
    if len(parts) < 2:
        await message.answer("Используйте: /delete_user @username")
        return
    target_user = parts[1].strip("@")
    response, status = await make_request("DELETE", f"/admin/users/{target_user}", username)
    if status == 200:
        await message.answer(f"Пользователь @{target_user} удалён.")
    else:
        await message.answer("Ошибка: у вас нет прав или пользователь не найден.")

@dp.message(Command("clear_redis"))
async def clear_redis(message: types.Message):
    username = message.from_user.username
    response, status = await make_request("DELETE", "/admin/clear_redis", username)
    if status == 200:
        await message.answer("Redis успешно очищен.")
    else:
        await message.answer("Ошибка: у вас нет прав на очистку Redis.")

@dp.message(Command("edit_user"))
async def edit_user_start(message: types.Message, state: FSMContext):
    username = message.from_user.username
    response, status = await make_request("GET", f"/check_admin", username)
    
    if status != 200:
        await message.answer("У вас нет прав администратора!")
        return
    
    await message.answer("Введите @username пользователя, которого хотите изменить:")
    await state.set_state(AdminEditUser.AWAIT_USERNAME)

@dp.message(AdminEditUser.AWAIT_USERNAME)
async def get_target_username(message: types.Message, state: FSMContext):
    target_username = message.text.strip().lstrip("@")
    await state.update_data(target_username=target_username)
    await message.answer("Введите новое имя пользователя:")
    await state.set_state(AdminEditUser.AWAIT_NEW_NAME)

@dp.message(AdminEditUser.AWAIT_NEW_NAME)
async def update_user_profile(message: types.Message, state: FSMContext):
    admin_username = message.from_user.username
    new_name = message.text.strip()
    data = await state.get_data()
    target_username = data.get("target_username")

    response, status = await make_request("PUT", f"/admin/users/{target_username}", admin_username, {"full_name": new_name})

    if status == 200:
        await message.answer(f"Имя пользователя @{target_username} изменено на '{new_name}'.")
    else:
        await message.answer("Ошибка: не удалось обновить профиль пользователя.")

    await state.clear()
async def main():
    logging.basicConfig(level=logging.INFO)
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())