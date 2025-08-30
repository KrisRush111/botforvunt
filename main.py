import re
import threading
import unidecode
import requests
import asyncio
import random
import os
import http.server
import socketserver
import string
import secrets
import logging
from aiogram import Bot, Dispatcher, F, Router
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.enums import ParseMode
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.context import FSMContext
from aiogram.filters import Command
from aiogram.client.bot import DefaultBotProperties
import urllib.parse
import aiohttp
from config import BOT_TOKEN, ADMIN_BOT_TOKEN, ADMIN_CHAT_ID, SCHOOL_CODES, BANNED_WORDS, DB_URL, BOT_SESSION_ID
from db_storage import Database

db = Database(DB_URL)
from aiogram.exceptions import TelegramBadRequest


logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)

def generate_platform_user_id() -> str:
    return ''.join(random.choices(string.digits, k=8))


async def send_registration_to_api(user_data: dict, telegram_user_id: int) -> tuple[bool, str | None]:
    url = "https://vuntserver-csaq.onrender.com/register"

    # Всегда генерируем новый platform_user_id для регистрации
    # независимо от того, что пришло в user_data
    platform_user_id = generate_platform_user_id()
    user_data["platform_user_id"] = platform_user_id
    print(f"[DEBUG] Сгенерирован platform_user_id для регистрации: {platform_user_id}")

    payload = {
        "telegram_user_id": telegram_user_id,
        "nickname": user_data.get("nickname", "не указано"),
        "email": user_data.get("email", "не указано"),
        "password": user_data.get("password", "не указано"),
        "identity": user_data.get("identity", "не указано"),
        "main_school_code": user_data.get("main_school_code", "не указано"),
        "main_school_name": user_data.get("main_school_name", "не указано"),
        "class_number": user_data.get("class_number", "не указано"),
        "class_letter": user_data.get("class_letter", "не указано"),
        "additional_school_code": user_data.get("additional_school_code", "не указано"),
        "additional_school_name": user_data.get("additional_school_name", "не указано"),
        "specialization": user_data.get("specialization", "не указано"),
        "course": user_data.get("course", "не указано"),
        "platform_user_id": platform_user_id  # Всегда используем сгенерированный
    }

    try:
        print("[DEBUG] Отправляем данные на регистрацию:", payload)
        async with aiohttp.ClientSession() as session:
            async with session.post(url, json=payload) as response:
                print("[DEBUG] Статус ответа регистрации:", response.status)
                if response.status == 201:
                    response_data = await response.json()
                    platform_user_id_from_server = response_data.get("platform_user_id")

                    if platform_user_id_from_server and re.fullmatch(r"^\d{8,9}$", str(platform_user_id_from_server)):
                        print(f"[API SUCCESS ✅] Данные отправлены. Platform User ID: {platform_user_id_from_server}")
                        return True, str(platform_user_id_from_server)
                    else:
                        print(f"[API WARNING] Некорректный platform_user_id от сервера, используем сгенерированный: {platform_user_id}")
                        return True, platform_user_id
                else:
                    print("[API ERROR ❌]", await response.text())
                    return False, None
    except Exception as e:
        print("[API EXCEPTION ❌]", e)
        return False, None


async def send_update_to_api(user_data: dict, telegram_user_id: int) -> tuple[bool, str | None]:
    url = "https://vuntserver-csaq.onrender.com/update_user"

    if not user_data.get("platform_user_id") or user_data.get("platform_user_id") == "не указано":
        user_data["platform_user_id"] = generate_platform_user_id()
        print(f"[DEBUG] Сгенерирован новый platform_user_id для обновления: {user_data['platform_user_id']}")

    payload = {
        "telegram_user_id": telegram_user_id,
        "nickname": user_data.get("nickname", "не указано"),
        "email": user_data.get("email", "не указано"),
        "password": user_data.get("password", "не указано"),
        "identity": user_data.get("identity", "не указано"),
        "main_school_code": user_data.get("main_school_code", "не указано"),
        "main_school_name": user_data.get("main_school_name", "не указано"),
        "class_number": user_data.get("class_number", "не указано"),
        "class_letter": user_data.get("class_letter", "не указано"),
        "additional_school_code": user_data.get("additional_school_code", "не указано"),
        "additional_school_name": user_data.get("additional_school_name", "не указано"),
        "specialization": user_data.get("specialization", "не указано"),
        "course": user_data.get("course", "не указано"),
        "platform_user_id": user_data.get("platform_user_id")
    }

    try:
        print("[DEBUG] Отправляем данные на обновление:", payload)
        async with aiohttp.ClientSession() as session:
            async with session.post(url, json=payload) as response:
                print("[DEBUG] Статус ответа обновления:", response.status)
                if response.status == 200:
                    response_data = await response.json()
                    platform_user_id_from_server = response_data.get("platform_user_id")

                    if platform_user_id_from_server and re.fullmatch(r"^\d{8,9}$", str(platform_user_id_from_server)):
                        print(f"[API SUCCESS ✅] Данные обновлены. Platform User ID: {platform_user_id_from_server}")
                        return True, str(platform_user_id_from_server)
                    else:
                        print(
                            f"[API ERROR ❌] Некорректный platform_user_id от сервера: {platform_user_id_from_server}. Используем сгенерированный: {user_data['platform_user_id']}")
                        return True, user_data['platform_user_id']
                else:
                    print("[API ERROR ❌]", await response.text())
                    return False, None
    except Exception as e:
        print("[API EXCEPTION ❌]", e)
        return False, None


async def get_profile_from_api(user_id: int):
    url = "https://vuntserver-csaq.onrender.com/get_user"
    try:
        print("[DEBUG] Получаем профиль по ID:", user_id)

        async with aiohttp.ClientSession() as session:
            async with session.post(url, json={"telegram_user_id": user_id}) as response:
                print("[DEBUG] Статус ответа профиля:", response.status)
                response_text = await response.text()
                print("[DEBUG] Ответ сервера:", response_text)

                if response.status == 200:
                    data = await response.json()
                    user_data = data.get("user")

                    if user_data:
                        retrieved_platform_id = user_data.get("platform_user_id")

                        if retrieved_platform_id and re.fullmatch(r"^\d{8,9}$", str(retrieved_platform_id)):
                            platform_user_id_to_store = str(retrieved_platform_id)
                        else:
                            print(
                                f"[DEBUG] Получен некорректный platform_user_id: {retrieved_platform_id}. Устанавливаем 'не указано'.")
                            platform_user_id_to_store = "не указано"

                        return {
                            "nickname": user_data.get("nickname", "не указано"),
                            "email": user_data.get("email", "не указано"),
                            "password": user_data.get("password", "не указано"),
                            "identity": user_data.get("identity", "не указано"),
                            "main_school_code": user_data.get("main_school_code", "не указано"),
                            "main_school_name": user_data.get("main_school_name", "не указано"),
                            "class_number": user_data.get("class_number", "не указано"),
                            "class_letter": user_data.get("class_letter", "не указано"),
                            "additional_school_code": user_data.get("additional_school_code", "не указано"),
                            "additional_school_name": user_data.get("additional_school_name", "не указано"),
                            "specialization": user_data.get("specialization", "не указано"),
                            "course": user_data.get("course", "не указано"),
                            "platform_user_id": platform_user_id_to_store
                        }
                    else:
                        print("[DEBUG] Данные пользователя отсутствуют в ответе.")
                        return None
                else:
                    print("[API ERROR ❌]", response_text)
                    return None
    except Exception as e:
        print("[API EXCEPTION ❌]", e)
        return None


def contains_bad_words(nickname: str) -> bool:
    char_replacements = {
        'a': 'а',
        'e': 'е',
        'o': 'о',
        'p': 'р',
        'c': 'с',
        'y': 'у',
        'x': 'х',
        'k': 'к',
        'h': 'н',
        'b': 'в',
        'm': 'м',
        't': 'т',
        'а': 'a',
        'е': 'e',
        'о': 'o',
        'р': 'p',
        'с': 'c',
        'у': 'y',
        'х': 'x',
        'к': 'k',
        'н': 'h',
        'в': 'b',
        'м': 'm',
        'т': 't',
    }

    cleaned_nickname = re.sub(r'[^a-zA-Zа-яА-ЯёЁ]', '', nickname).lower()

    variants = set()
    variants.add(cleaned_nickname)

    for i in range(len(cleaned_nickname)):
        char = cleaned_nickname[i]
        if char in char_replacements:
            new_variant = cleaned_nickname[:i] + char_replacements[char] + cleaned_nickname[i + 1:]
            variants.add(new_variant)

    for variant in variants:

        for word in BANNED_WORDS["рус"]:
            first_letters = word.lower()[:3]
            if first_letters in variant:
                return True

        for word in BANNED_WORDS["eng"]:
            first_letters = word.lower()[:3]
            if first_letters in variant:
                return True

    return False


def keep_alive():
    port = int(os.environ.get("PORT", 8080))
    handler = http.server.SimpleHTTPRequestHandler
    with socketserver.TCPServer(("", port), handler) as httpd:
        print(f"Фейковый сервер запущен на порту {port}")
        httpd.serve_forever()


threading.Thread(target=keep_alive, daemon=True).start()


class SchoolStates(StatesGroup):
    waiting_for_school_code = State()
    editing_main_school = State()
    waiting_for_nickname = State()
    waiting_for_password = State()
    waiting_for_identity = State()
    waiting_for_start_acknowledgement = State()
    waiting_for_email_choice = State()
    waiting_for_class = State()
    waiting_for_class_letter = State()
    waiting_for_other_identity = State()
    waiting_for_specialization = State()
    waiting_for_course = State()
    editing_profile_field = State()
    editing_nickname = State()
    editing_password = State()
    editing_identity = State()
    editing_class = State()
    editing_class_letter = State()
    editing_specialization = State()
    editing_course = State()
    editing_email_choice = State()
    waiting_for_additional_school_code = State()
    # Новые состояния для менторов ВШП
    waiting_for_mentor_specialization = State()
    waiting_for_mentor_password = State()
    waiting_for_mentor_email_choice = State()


router = Router()


async def delete_messages(bot: Bot, chat_id: int, message_ids: list):
    for msg_id in message_ids:
        if msg_id is not None:
            try:
                await bot.delete_message(chat_id=chat_id, message_id=msg_id)
            except Exception:
                pass


async def delete_last_interaction(bot: Bot, chat_id: int, state: FSMContext):
    data = await state.get_data()
    msgs_to_delete = [
        data.get("last_bot_message_id"),
        data.get("last_sticker_message_id")
    ]
    await delete_messages(bot, chat_id, msgs_to_delete)
    await state.update_data(last_bot_message_id=None, last_sticker_message_id=None)


async def show_profile_summary(callback_or_message, state: FSMContext):
    data = await state.get_data()
    telegram_id = callback_or_message.from_user.id

    success, updated_platform_id = await send_update_to_api(data, telegram_id)
    if success and updated_platform_id:
        await state.update_data(platform_user_id=updated_platform_id)
        data = await state.get_data()

    nickname = data.get("nickname", "не указан")
    password = data.get("password", "не указан")
    email = data.get("email", "не указана")
    identity = data.get("identity", "не указана")
    platform_user_id = data.get("platform_user_id", "не указан")

    main_school_code = data.get("main_school_code")
    main_school_data = SCHOOL_CODES.get(main_school_code, {})
    main_school_name = main_school_data.get("name", "не указано")
    main_school_type = main_school_data.get("type", "обычная")

    class_number = data.get("class_number", "")
    class_letter = data.get("class_letter", "")
    class_info = f"{class_number}{class_letter}" if class_number and class_letter else "не указан"

    additional_school_code = data.get("additional_school_code")
    additional_school_name = data.get("additional_school_name")
    specialization = data.get("specialization")
    course = data.get("course")

    profile_text = (
        f"🎉 Ваш профиль:\n\n"
        f"🆔 ID на платформе: `{platform_user_id}`\n"
        f"🏢 Основная школа: `{main_school_name}`\n"
        f"👤 Никнейм: `{nickname}`\n"
        f"🔑 Пароль: `{password}`\n"
        f"📧 Почта: `{email}`\n"
        f"🧑 Роль: `{identity}`\n"
    )

    if main_school_type == "обычная":
        profile_text += f"🏫 Класс: `{class_info}`\n"
    elif main_school_type == "особенная":
        if specialization:
            profile_text += f"➡️ Направление: `{specialization}`\n"
        if course:
            profile_text += f"📚 Курс: `{course}`\n"
    elif main_school_type == "ментор_вшп":  # Добавляем отображение для менторов ВШП
        if specialization:
            profile_text += f"➡️ Направление: `{specialization}`\n"

    if additional_school_code and additional_school_code != main_school_code:
        profile_text += f"\n📌 ДОПОЛНИТЕЛЬНАЯ ШКОЛА:\n"
        profile_text += f"🏢 Школа: `{additional_school_name or 'не указано'}`\n"
        if specialization:
            profile_text += f"➡️ Направление: `{specialization}`\n"
        if course:
            profile_text += f"🎓 Курс: `{course}`\n"

    edit_keyboard_buttons = [
        [InlineKeyboardButton(text="✏️ Изменить профиль", callback_data=f"edit_profile:{BOT_SESSION_ID}")],
        [InlineKeyboardButton(text="🔑 Вход", url="https://vuntgram.vercel.app")],
        [InlineKeyboardButton(text="Поддержка 💬", url="https://t.me/VuntgramSupport_bot")] 
    ]

    # Не добавляем кнопку "Добавить школу" для менторов ВШП
    if main_school_type != "ментор_вшп":
        edit_keyboard_buttons.insert(1, [
            InlineKeyboardButton(text="➕ Добавить школу", callback_data=f"add_school:{BOT_SESSION_ID}")])

    edit_keyboard = InlineKeyboardMarkup(inline_keyboard=edit_keyboard_buttons)

    try:
        if isinstance(callback_or_message, CallbackQuery):
            await callback_or_message.message.edit_text(
                profile_text,
                reply_markup=edit_keyboard,
                parse_mode=ParseMode.MARKDOWN
            )
        else:
            await callback_or_message.answer(
                profile_text,
                reply_markup=edit_keyboard,
                parse_mode=ParseMode.MARKDOWN
            )
    except Exception:
        if isinstance(callback_or_message, CallbackQuery):
            await callback_or_message.message.answer(
                profile_text,
                reply_markup=edit_keyboard,
                parse_mode=ParseMode.MARKDOWN
            )
        else:
            await callback_or_message.answer(
                profile_text,
                reply_markup=edit_keyboard,
                parse_mode=ParseMode.MARKDOWN
            )


async def send_admin_update(data: dict, user_id: int, is_additional_school: bool = False):
    main_school_code = data.get("main_school_code")
    main_school_data = SCHOOL_CODES.get(main_school_code, {})
    main_school_name = main_school_data.get("name", "не указано")
    main_school_type = main_school_data.get("type", "обычная")

    nickname = data.get("nickname", "не указан")
    password = data.get("password", "не указан")
    email = data.get("email", "не указана")
    identity = data.get("identity", "не указана")
    class_number = data.get("class_number", "")
    class_letter = data.get("class_letter", "")
    class_info = f"{class_number}{class_letter}" if class_number and class_letter else "не указан"
    platform_user_id = data.get("platform_user_id", "не указан")
    specialization = data.get("specialization")
    course = data.get("course")

    admin_message = (
        f"👤 Пользователь ID (Telegram): `{user_id}`\n"
        f"🆔 ID на платформе: `{platform_user_id}`\n"
        f"🏢 Основная школа: `{main_school_name}`\n"
        f"👤 Никнейм: `{nickname}`\n"
        f"🔑 Пароль: `{password}`\n"
        f"📧 Почта: `{email}`\n"
        f"🧑 Роль: `{identity}`\n"
    )

    if main_school_type == "обычная" and class_info != "не указан":
        admin_message += f"🏫 Класс: `{class_info}`\n"
    elif main_school_type == "особенная":
        if specialization:
            admin_message += f"➡️ Направление: `{specialization}`\n"
        if course:
            admin_message += f"📚 Курс: `{course}`\n"
    elif main_school_type == "ментор_вшп":  # Добавляем отображение для менторов ВШП
        if specialization:
            admin_message += f"➡️ Направление: `{specialization}`\n"

    additional_school_code = data.get("school_code")
    if additional_school_code and additional_school_code != main_school_code:
        additional_school_data = SCHOOL_CODES.get(additional_school_code, {})
        additional_school_name = additional_school_data.get("name", "не указано")
        additional_school_type = additional_school_data.get("type", "обычная")

        additional_parts = []

        if additional_school_name != main_school_name:
            additional_parts.append(f"🏢 Школа: `{additional_school_name}`")

        if additional_school_type == "особенная":
            if "course" in data and data["course"] not in [None, "None", "не указан"]:
                additional_parts.append(f"📚 Курс: `{data['course']}`")

            if "specialization" in data and data["specialization"] not in [None, "None", "не указано"]:
                additional_parts.append(f"➡️ Направление: `{data['specialization']}`")

        if additional_parts:
            admin_message += "\n\nДОПОЛНИТЕЛЬНО:\n" + "\n".join(additional_parts)

    safe_text = urllib.parse.quote_plus(admin_message)
    url = f"https://api.telegram.org/bot{ADMIN_BOT_TOKEN}/sendMessage?chat_id={ADMIN_CHAT_ID}&text={safe_text}&parse_mode=Markdown"

    try:
        response = requests.get(url)
        if response.status_code != 200:
            print("Ошибка при отправке сообщения админу:", response.text)
    except Exception as e:
        print(f"Ошибка при отправке запроса админу: {e}")


def process_user_profile(data: dict) -> dict:
    # Переопределяем поле пароля на "не указано", если оно не заполнено
    if not data.get("password") or data.get("password") == "не указано":
        data["password"] = "не указано"

    # Теперь можно вернуть или вывести профиль
    return data

def is_profile_complete(data: dict) -> bool:
    if not data:
        logger.warning("Данные профиля отсутствуют.")
        return False

    # ПРЕДВАРИТЕЛЬНАЯ ОБРАБОТКА ДАННЫХ
    # Автоматически устанавливаем пароль в "не указано", если он отсутствует
    if not data.get("password") or data.get("password") == "не указано":
        data["password"] = "не указано"
        logger.debug("Пароль автоматически установлен в 'не указано'")

    main_school_code = data.get('main_school_code')
    school = SCHOOL_CODES.get(main_school_code)
    if not school:
        logger.warning(f"Школа с кодом {main_school_code} не найдена.")
        return False

    # Проверка platform_user_id для всех типов пользователей
    platform_user_id = data.get("platform_user_id")
    if not platform_user_id or platform_user_id == "не указан" or not re.fullmatch(r"^\d{8,9}$", str(platform_user_id)):
        logger.warning("Неверный platform_user_id.")
        return False

    required_fields = ["nickname", "email", "identity"]
    for field in required_fields:
        if not data.get(field) or data.get(field) == "не указано":
            logger.warning(f"Поле {field} не заполнено.")
            return False

    # Проверяем ПАРОЛЬ (теперь всегда должен быть "не указано", если не заполнен)
    if not data.get("password"):
        logger.warning("Поле password отсутствует в данных.")
        return False

    # Проверка дополнительных полей в зависимости от типа школы
    if school.get("type") == "обычная":
        if not data.get("class_number") or data.get("class_number") == "не указано":
            logger.warning("Поле class_number не заполнено.")
            return False
        if not data.get("class_letter") or data.get("class_letter") == "не указано":
            logger.warning("Поле class_letter не заполнено.")
            return False
    elif school.get("type") == "особенная":
        if not data.get("specialization") or data.get("specialization") == "не указано":
            logger.warning("Поле specialization не заполнено.")
            return False
        if not data.get("course") or data.get("course") == "не указано":
            logger.warning("Поле course не заполнено.")
            return False
    elif school.get("type") == "ментор_вшп":
        if not data.get("specialization") or data.get("specialization") == "не указано":
            logger.warning("Поле specialization не заполнено.")
            return False

    # Проверка дополнительной школы (если есть)
    additional_school_code = data.get("additional_school_code")
    if additional_school_code:
        additional_school = SCHOOL_CODES.get(additional_school_code, {})
        if additional_school.get("type") == "особенная":
            if not data.get("specialization") or data.get("specialization") == "не указано":
                logger.warning("Поле specialization для дополнительной школы не заполнено.")
                return False
            if not data.get("course") or data.get("course") == "не указано":
                logger.warning("Поле course для дополнительной школы не заполнено.")
                return False

    logger.debug("Профиль прошел проверку на полноту")
    return True




@router.message(Command("start"))
async def start_handler(message: Message, state: FSMContext):
    user_id = message.from_user.id
    print(f"[DEBUG] start_handler вызван для user_id: {user_id}")

    await state.clear()

    user_profile = await get_profile_from_api(user_id)

    if user_profile:
        print("[DEBUG] Профиль найден из API для /start:", user_profile)
        await state.update_data(
            telegram_user_id=user_id,
            nickname=user_profile.get("nickname") or "не указано",
            email=user_profile.get("email") or "не указано",
            password=user_profile.get("password") or "не указано",
            identity=user_profile.get("identity") or "не указано",
            main_school_code=user_profile.get("main_school_code"),
            main_school_name=user_profile.get("main_school_name"),
            class_number=user_profile.get("class_number") or "не указано",
            class_letter=user_profile.get("class_letter") or "",
            additional_school_code=user_profile.get("additional_school_code"),
            additional_school_name=user_profile.get("additional_school_name"),
            specialization=user_profile.get("specialization"),
            course=user_profile.get("course"),
            platform_user_id=user_profile.get("platform_user_id")
        )

        current_data = await state.get_data()
        main_school_code = current_data.get("main_school_code")
        school_data = SCHOOL_CODES.get(main_school_code, {})
        school_type = school_data.get("type", "обычная")

        # Проверяем, есть ли дополнительная школа
        additional_school_code = current_data.get("additional_school_code")
        has_additional_school = additional_school_code and additional_school_code != main_school_code

        # Для профилей с дополнительной школой или менторов ВШП показываем профиль
        if has_additional_school or school_type == "ментор_вшп" or is_profile_complete(current_data):
            # Явно показываем профиль в нужном формате для менторов
            if school_type == "ментор_вшп":
                nickname = current_data.get("nickname", "не указан")
                password = current_data.get("password", "не указан")
                email = current_data.get("email", "не указана")
                identity = current_data.get("identity", "не указана")
                platform_user_id = current_data.get("platform_user_id", "не указан")
                specialization = current_data.get("specialization", "не указано")

                profile_text = (
                    f"🎉 Регистрация завершена!\n\n"
                    f"🆔 ID на платформе: `{platform_user_id}`\n"
                    f"🏢 Школа: ВШП(Высшая школа программирования)\n"
                    f"👤 Никнейм: `{nickname}`\n"
                    f"🔑 Пароль: `{password}`\n"
                    f"📧 Почта: `{email}`\n"
                    f"🧑 Роль: `{identity}`\n"
                    f"➡️ Направление: `{specialization}`\n"
                )

                edit_keyboard = InlineKeyboardMarkup(
                    inline_keyboard=[
                        [InlineKeyboardButton(text="✏️ Изменить профиль",
                                              callback_data=f"edit_profile:{BOT_SESSION_ID}")],
                        [InlineKeyboardButton(text="🔑 Вход", url="https://vuntgram.vercel.app")],
                        [InlineKeyboardButton(text="Поддержка 💬", url="https://t.me/VuntgramSupport_bot")]
                    ]
                )

                await message.answer(profile_text, parse_mode=ParseMode.MARKDOWN, reply_markup=edit_keyboard)
            else:
                await show_profile_summary(message, state)
            await state.set_state(None)
            return
        else:
            # Профиль неполный, продолжаем регистрацию
            await message.answer("Ваш профиль неполный. Давайте завершим регистрацию.")

    await state.set_state(SchoolStates.waiting_for_start_acknowledgement)

    sent_sticker = await message.answer_sticker(
        "CAACAgIAAxkBAAEBUxhoRFfkJ6Gpxrw8X8K_nQuZeqIOpQACNj8AAvw3SEl-1bzJ-K-rhjYE"
    )

    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="Ввести код приглашения 🔑", callback_data="enter_school_code")],
            [InlineKeyboardButton(text="Подробнее...", url="thevuntgram.vercel.app")],
            [InlineKeyboardButton(text="Поддержка 💬", url="https://t.me/VuntgramSupport_bot")]
        ]
    )

    welcome_text = (
        f"Привет, *{message.from_user.first_name}*, это *TheVuntgram* — добро пожаловать на регистрацию! 🚀\n\n"
        "Готов(а) присоединиться к своему школьному сообществу? 🫠❓"
    )

    sent_msg = await message.answer(
        welcome_text,
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=keyboard
    )

    await state.update_data(last_bot_message_id=sent_msg.message_id, last_sticker_message_id=sent_sticker.message_id)

@router.message(Command("myprofile"))
async def my_profile_handler(message: Message, state: FSMContext):
    user_id = message.from_user.id
    print(f"[DEBUG] my_profile_handler вызван для user_id: {user_id}")

    await state.clear()

    user_profile = await get_profile_from_api(user_id)

    if user_profile:
        print(f"[DEBUG] Профиль найден для user_id {user_id}: {user_profile}")
        await state.update_data(
            telegram_user_id=user_id,
            nickname=user_profile.get("nickname") or "не указано",
            email=user_profile.get("email") or "не указано",
            password=user_profile.get("password") or "не указано",
            identity=user_profile.get("identity") or "не указано",
            main_school_code=user_profile.get("main_school_code"),
            main_school_name=user_profile.get("main_school_name"),
            class_number=user_profile.get("class_number") or "не указано",
            class_letter=user_profile.get("class_letter") or "",
            additional_school_code=user_profile.get("additional_school_code"),
            additional_school_name=user_profile.get("additional_school_name"),
            specialization=user_profile.get("specialization"),
            course=user_profile.get("course"),
            platform_user_id=user_profile.get("platform_user_id")
        )
        await show_profile_summary(message, state)
        await state.set_state(None)
        return
    else:
        print(f"[DEBUG] Профиль НЕ найден для user_id {user_id}. Начинаем регистрацию.")
        await state.set_state(SchoolStates.waiting_for_start_acknowledgement)

        sent_sticker = await message.answer_sticker(
            "CAACAgIAAxkBAAEBUxhoRFfkJ6Gpxrw8X8K_nQuZeqIOpQACNj8AAvw3SEl-1bzJ-K-rhjYE"
        )

        keyboard = InlineKeyboardMarkup(
            inline_keyboard=[
                [InlineKeyboardButton(text="Ввести код приглашения 🔑", callback_data="enter_school_code")],
                [InlineKeyboardButton(text="Подробнее...", url="thevuntgram.vercel.app")],
                [InlineKeyboardButton(text="Поддержка 💬", url="https://t.me/VuntgramSupport_bot")]
            ]
        )

        welcome_text = (
            f"Привет, *{message.from_user.first_name}*, это *TheVuntgram* — добро пожаловать на регистрацию! 🚀\n\n"
            "Готов(а) присоединиться к своему школьному сообществу? 🫠❓"
        )

        sent_msg = await message.answer(welcome_text, parse_mode=ParseMode.MARKDOWN, reply_markup=keyboard)
        await state.update_data(
            last_bot_message_id=sent_msg.message_id,
            last_sticker_message_id=sent_sticker.message_id
        )


@router.callback_query(F.data.startswith("edit_field"))
async def handle_edit_field(callback: CallbackQuery, state: FSMContext):
    try:
        parts = callback.data.split(":")
        field = parts[1]
        session_id = parts[2] if len(parts) > 2 else None
    except ValueError:
        await callback.answer("❌ Неверный формат кнопки.")
        return

    if session_id and session_id != BOT_SESSION_ID:
        await callback.answer("⚠️ Это устаревшая кнопка. Пожалуйста, нажмите /start.", show_alert=True)
        return

    await edit_field_choice(callback, state)


@router.callback_query(F.data == "enter_school_code")
async def enter_code_callback(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    sent = await callback.message.answer(
        "🔐 Пожалуйста, введи *код приглашения своей школы*.",
        parse_mode=ParseMode.MARKDOWN
    )
    await state.set_state(SchoolStates.waiting_for_school_code)
    await state.update_data(last_bot_message_id=sent.message_id)


@router.message(SchoolStates.waiting_for_school_code)
async def code_handler(message: Message, state: FSMContext):
    data = await state.get_data()
    last_bot_message_id = data.get("last_bot_message_id")
    last_sticker_message_id = data.get("last_sticker_message_id")

    await delete_messages(message.bot, message.chat.id,
                          [message.message_id, last_bot_message_id, last_sticker_message_id])

    code = message.text.strip()

    if code in SCHOOL_CODES:
        school_data = SCHOOL_CODES[code]
        school_name = school_data["name"]
        school_type = school_data["type"]

        main_school_code = data.get("main_school_code")

        if code == main_school_code or code == data.get("school_code"):
            back_keyboard = InlineKeyboardMarkup(
                inline_keyboard=[
                    [InlineKeyboardButton(text="🔙 Назад", callback_data="back_to_profile")]
                ]
            )
            sent = await message.answer(
                f"❌ Вы уже зарегистрированы в школе {school_name}.",
                reply_markup=back_keyboard
            )
            await state.update_data(last_bot_message_id=sent.message_id)
            return

        if not main_school_code:
            if school_type == "особенная":
                sent = await message.answer(
                    "❌ Вы не можете зарегистрироваться по коду особенной школы.\n"
                    "Пожалуйста, введите код обычной школы для продолжения регистрации."
                )
                await state.update_data(last_bot_message_id=sent.message_id)
                return

            if school_type == "ментор_вшп": # Обработка кода ментора ВШП
                await state.update_data(
                    main_school_code=code,
                    school_code=code,
                    identity="ментор",  # Автоматически устанавливаем роль
                    main_school_name="ВШП(Высшая школа программирования)"
                )
                sent1 = await message.answer(f"✅ Код подтверждён!\nДобро пожаловать в {school_name} 🎉")
                sent2 = await message.answer("🧑‍🎓 Теперь придумай *никнейм* для своего аккаунта:")
                await state.set_state(SchoolStates.waiting_for_nickname)
                await state.update_data(last_bot_message_id=sent2.message_id, last_sticker_message_id=None)
                return

            await state.update_data(main_school_code=code, school_code=code)

        else:
            current_school_data = SCHOOL_CODES[main_school_code]
            if current_school_data["type"] == "обычная" and school_type == "обычная":
                back_keyboard = InlineKeyboardMarkup(
                    inline_keyboard=[
                        [InlineKeyboardButton(text="🔙 Назад", callback_data="back_to_profile")]
                    ]
                )
                sent = await message.answer(
                    f"❌ Вы уже зарегистрированы в обычной школе {current_school_data['name']}.",
                    reply_markup=back_keyboard
                )
                await state.update_data(last_bot_message_id=sent.message_id)
                return

            await state.update_data(school_code=code)

        sent1 = await message.answer(f"✅ Код подтверждён!\nДобро пожаловать в {school_name} 🎉")

        if not main_school_code:
            sent2 = await message.answer("🧑‍🎓 Теперь придумай *никнейм* для своего аккаунта:")
            await state.set_state(SchoolStates.waiting_for_nickname)
        else:
            if school_type == "особенная":
                specializations = school_data["specializations"]
                specialization_keyboard = InlineKeyboardMarkup(
                    inline_keyboard=[
                        [InlineKeyboardButton(text=name, callback_data=f"specialization:{code}")]
                        for code, name in specializations.items()
                    ]
                )
                sent2 = await message.answer("Выберите направление:", reply_markup=specialization_keyboard)
                await state.set_state(SchoolStates.waiting_for_specialization)
            else:
                keyboard = InlineKeyboardMarkup(
                    inline_keyboard=[
                        [InlineKeyboardButton(text=str(i), callback_data=f"class:{i}")]
                        for i in range(5, 12)
                    ]
                )
                sent2 = await message.answer("В каком вы классе?", reply_markup=keyboard)
                await state.set_state(SchoolStates.waiting_for_class)

        await state.update_data(last_bot_message_id=sent2.message_id, last_sticker_message_id=None)

    else:
        sent = await message.answer("❌ Неверный код. Попробуй ещё раз.")
        await state.update_data(last_bot_message_id=sent.message_id, last_sticker_message_id=None)


@router.message(SchoolStates.waiting_for_start_acknowledgement)
async def repeat_welcome_on_any_message(message: Message, state: FSMContext):
    sent_sticker = await message.answer_sticker(
        "CAACAgIAAxkBAAEBUxhoRFfkJ6Gpxrw8X8K_nQuZeqIOpQACNj8AAvw3SEl-1bzJ-K-rhjYE")
    await state.update_data(last_sticker_message_id=sent_sticker.message_id)

    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="Ввести код приглашения 🔑", callback_data="enter_school_code")],
            [InlineKeyboardButton(text="Подробнее...", url="thevuntgram.vercel.app")],
            [InlineKeyboardButton(text="Поддержка 💬", url="https://t.me/VuntgramSupport_bot")]
        ]
    )

    welcome_text = (
        f"Привет, *{message.from_user.first_name}*, это *TheVuntgram* — добро пожаловать на регистрацию! 🚀\n\n"
        "Готов(а) присоединиться к своему школьному сообществу? 🫠❓"
    )

    sent_msg = await message.answer(welcome_text, parse_mode=ParseMode.MARKDOWN, reply_markup=keyboard)
    await state.update_data(last_bot_message_id=sent_msg.message_id)


@router.message(SchoolStates.waiting_for_nickname)
async def nickname_handler(message: Message, state: FSMContext):
    data = await state.get_data()
    last_bot_message_id = data.get("last_bot_message_id")
    last_sticker_message_id = data.get("last_sticker_message_id")

    await delete_messages(message.bot, message.chat.id,
                          [message.message_id, last_bot_message_id, last_sticker_message_id])

    nickname_input = message.text.strip()

    if not re.fullmatch(r"[A-Za-zА-Яа-яёЁ\s\-_]+", nickname_input):
        sent_sticker = await message.answer_sticker(
            "CAACAgIAAxkBAAEBUx9oRJh9otcsYTyzz78pEjnwT7SNeQAC80EAAm-zaElfo-DQ18SjdjYE")
        sent2 = await message.answer(
            "⚠️ Никнейм должен содержать только буквы, подчёркивания, пробелы или дефис. Попробуй снова.")
        await state.update_data(last_bot_message_id=sent2.message_id, last_sticker_message_id=sent_sticker.message_id)
        return

    if re.search(r"[\s\-_]$", nickname_input):
        sent_sticker = await message.answer_sticker(
            "CAACAgIAAxkBAAEBUx9oRJh9otcsYTyzz78pEjnwT7SNeQAC80EAAm-zaElfo-DQ18SjdjYE")
        sent2 = await message.answer("⚠️ Никнейм не должен заканчиваться на пробел, подчёркивание или дефис.")
        await state.update_data(last_bot_message_id=sent2.message_id, last_sticker_message_id=sent_sticker.message_id)
        return

    num_letters = len(re.findall(r"[A-Za-zА-Яа-яёЁ]", nickname_input))
    if num_letters < 3:
        sent_sticker = await message.answer_sticker(
            "CAACAgIAAxkBAAEBUx9oRJh9otcsYTyzz78pEjnwT7SNeQAC80EAAm-zaElfo-DQ18SjdjYE")
        sent2 = await message.answer("⚠️ В никнейме должно быть минимум 3 буквы (не считая символы и подчёркивания).")
        await state.update_data(last_bot_message_id=sent2.message_id, last_sticker_message_id=sent_sticker.message_id)
        return

    if contains_bad_words(nickname_input):
        sent_sticker = await message.answer_sticker(
            "CAACAgIAAxkBAAEBU49oRXIQke73ZhxrtV6BPOp8A524aAACLDEAAlf4QEvL1oswk3KNSDYE")
        sent2 = await message.answer(
            "🚫 Ваш ник содержит или может содержать недопустимые или оскорбительные слова. Пожалуйста, выберите другой.")
        await state.update_data(last_bot_message_id=sent2.message_id, last_sticker_message_id=sent_sticker.message_id)
        return

    await state.update_data(nickname=nickname_input)

    data = await state.get_data()
    school_code = data.get("school_code")
    if not school_code:
        sent = await message.answer("Ошибка: код школы не найден. Пожалуйста, начните регистрацию заново.")
        await state.update_data(last_bot_message_id=sent.message_id, last_sticker_message_id=None)
        return

    school_data = SCHOOL_CODES[school_code]

    if school_data["type"] == "ментор_вшп":  # Для менторов ВШП пропускаем выбор роли
        specializations = school_data["specializations"]
        specialization_keyboard = InlineKeyboardMarkup(
            inline_keyboard=[
                [InlineKeyboardButton(text=name, callback_data=f"mentor_specialization:{code}")]
                for code, name in specializations.items()
            ]
        )
        sent_sticker = await message.answer_sticker(
            "CAACAgIAAxkBAAEBUyhoRJp6nGrtPyxZC8hOOsvqmSo7FAACTTYAAvfSsEmzU88Y7pT07TYE")
        sent_msg = await message.answer("✅ Имя принято!\n\nВыберите направление:", reply_markup=specialization_keyboard)
        await state.set_state(SchoolStates.waiting_for_mentor_specialization)
        await state.update_data(last_bot_message_id=sent_msg.message_id,
                                last_sticker_message_id=sent_sticker.message_id)
        return

    identity_keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="🧑‍🎓 Ученик", callback_data="identity:ученик"),
                InlineKeyboardButton(text="👩‍🎓 Ученица", callback_data="identity:ученица"),
            ]
        ]
    )

    sent_sticker = await message.answer_sticker(
        "CAACAgIAAxkBAAEBUyhoRJp6nGrtPyxZC8hOOsvqmSo7FAACTTYAAvfSsEmzU88Y7pT07TYE")
    sent_msg = await message.answer("✅ Имя принято!\n\n👤 Кем вы являетесь?", reply_markup=identity_keyboard)
    await state.set_state(SchoolStates.waiting_for_identity)
    await state.update_data(last_bot_message_id=sent_msg.message_id, last_sticker_message_id=sent_sticker.message_id)


@router.callback_query(SchoolStates.waiting_for_other_identity, F.data == "back_to_identity")
async def back_to_identity_callback(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    try:
        await callback.message.delete()
    except Exception:
        pass

    identity_keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="🧑‍🎓 Ученик", callback_data="identity:ученик"),
                InlineKeyboardButton(text="👩‍🎓 Ученица", callback_data="identity:ученица"),
            ]
        ]
    )
    sent = await callback.message.answer("👤 Кем вы являетесь?", reply_markup=identity_keyboard)
    await state.set_state(SchoolStates.waiting_for_identity)
    await state.update_data(last_bot_message_id=sent.message_id, last_sticker_message_id=None)


@router.callback_query(SchoolStates.waiting_for_mentor_specialization, F.data.startswith("mentor_specialization:"))
async def mentor_specialization_callback(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    specialization_code = callback.data.split(":", 1)[1]

    data = await state.get_data()
    school_code = data.get("school_code")

    if not school_code:
        await callback.message.answer("❌ Ошибка: код школы не найден.")
        return

    school_data = SCHOOL_CODES.get(school_code)
    if not school_data:
        await callback.message.answer("❌ Ошибка: данные школы не найдены.")
        return

    specializations = school_data.get("specializations", {})
    specialization_name = specializations.get(specialization_code, "не указано")

    await state.update_data(specialization=specialization_name)

    try:
        await callback.message.delete()
    except Exception:
        pass

    sent_sticker = await callback.message.answer_sticker(
        "CAACAgIAAxkBAAEBUxpoRGUW4cPUbd3fx0SgcG_GwRDuPAACwz0AAswTKUqFD82aGooDRjYE")
    await state.update_data(last_sticker_message_id=sent_sticker.message_id)

    await callback.message.answer("Отлично! 🔥")
    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(
                text="🔐 Сгенерировать пароль",
                callback_data="generate_mentor_password"
            )]
        ]
    )
    sent2 = await callback.message.answer("🔐 Теперь придумай пароль (не менее 6 символов, буквы и цифры).",
                                          reply_markup=keyboard)
    await state.set_state(SchoolStates.waiting_for_mentor_password)
    await state.update_data(last_bot_message_id=sent2.message_id)


@router.callback_query(SchoolStates.waiting_for_specialization, F.data.startswith("specialization:"))
async def specialization_callback(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    specialization_code = callback.data.split(":", 1)[1]

    data = await state.get_data()
    additional_school_code = data.get("school_code")

    if not additional_school_code:
        await callback.message.answer("❌ Ошибка: код дополнительной школы не найден.")
        return

    school_data = SCHOOL_CODES.get(additional_school_code)
    if not school_data:
        await callback.message.answer("❌ Ошибка: данные школы не найдены.")
        return

    specializations = school_data.get("specializations", {})
    specialization_name = specializations.get(specialization_code, "не указано")
    school_name = school_data.get("name", "не указано")

    await state.update_data(
        specialization=specialization_name,
        additional_school_code=additional_school_code,
        additional_school_name=school_name
    )

    course_keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text=str(i), callback_data=f"course:{i}")]
            for i in range(1, 6)
        ]
    )

    try:
        await callback.message.delete()
    except Exception:
        pass

    sent_sticker = await callback.message.answer_sticker(
        "CAACAgIAAxkBAAEBUxpoRGUW4cPUbd3fx0SgcG_GwRDuPAACwz0AAswTKUqFD82aGooDRjYE")
    await state.update_data(last_sticker_message_id=sent_sticker.message_id)

    await callback.message.answer("Отлично! 🔥")
    sent2 = await callback.message.answer("Теперь выберите курс:", reply_markup=course_keyboard)

    await state.set_state(SchoolStates.waiting_for_course)
    await state.update_data(last_bot_message_id=sent2.message_id)


@router.callback_query(SchoolStates.waiting_for_course, F.data.startswith("course:"))
async def course_callback(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    course = callback.data.split(":", 1)[1]

    await state.update_data(course=course)

    data = await state.get_data()
    user_id = callback.from_user.id

    additional_school_code = data.get("additional_school_code")
    additional_school_data = SCHOOL_CODES.get(additional_school_code, {})
    additional_school_name = additional_school_data.get("name", "не указано")
    specialization = data.get("specialization", "не указано")

    main_school_code = data.get("main_school_code")
    main_school_data = SCHOOL_CODES.get(main_school_code, {})
    main_school_name = main_school_data.get("name", "не указано")

    nickname = data.get("nickname", "не указан")
    password = data.get("password", "не указан")
    email = data.get("email", "не указана")
    identity = data.get("identity", "не указана")

    await state.update_data(
        additional_school_code=additional_school_code,
        additional_school_name=additional_school_name,
        course=course
    )

    updated_data = await state.get_data()

    success, platform_user_id = await send_update_to_api(updated_data, user_id)

    if success:
        await state.update_data(platform_user_id=platform_user_id)
        print("✅ Данные отправлены в БД")
    else:
        print("❌ Не удалось отправить данные в БД")

    updated_data = await state.get_data()
    platform_user_id = updated_data.get("platform_user_id", "не указан")

    profile_text = (
        f"🎉 Ваш профиль:\n\n"
        f"🆔 ID на платформе: `{platform_user_id}`\n"
        f"🏢 Основная школа: `{main_school_name}`\n"
        f"👤 Никнейм: `{nickname}`\n"
        f"🔑 Пароль: `{password}`\n"
        f"📧 Почта: `{email}`\n"
        f"🧑 Роль: `{identity}`\n"
        f"\nДОПОЛНИТЕЛЬНО:\n"
        f"🏢 Школа: `{additional_school_name}`\n"
        f"📚 Курс: `{course}`\n"
        f"➡️ Направление: `{specialization}`\n"
    )

    edit_keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="✏️ Изменить профиль", callback_data=f"edit_profile:{BOT_SESSION_ID}")],
            [InlineKeyboardButton(text="➕ Добавить школу", callback_data=f"add_school:{BOT_SESSION_ID}")],
            [InlineKeyboardButton(text="🔑 Вход", url="https://vuntgram.vercel.app")],
            [InlineKeyboardButton(text="Поддержка 💬", url="https://t.me/VuntgramSupport_bot")]
        ]
    )

    try:
        await callback.message.edit_text(profile_text, reply_markup=edit_keyboard, parse_mode=ParseMode.MARKDOWN)
    except Exception:
        await callback.message.answer(profile_text, reply_markup=edit_keyboard, parse_mode=ParseMode.MARKDOWN)

    await send_admin_update(updated_data, user_id, is_additional_school=True)

    await state.set_state(None)


@router.callback_query(SchoolStates.waiting_for_identity, F.data.startswith("identity:"))
async def identity_callback(callback: CallbackQuery, state: FSMContext):
    await callback.answer()

    role = callback.data.split(":", 1)[1]
    await state.update_data(identity=role)

    await callback.message.delete()

    sent_sticker = await callback.message.answer_sticker(
        "CAACAgIAAxkBAAEBVLNoSA5bX7s1Lg2VmofAqPSk5viOpwACEjUAAsenoUqpHiuzlnPN-jYE")
    await state.update_data(last_sticker_message_id=sent_sticker.message_id)
    sent_msg = await callback.message.answer("✅ Роль принята!")
    await state.update_data(last_bot_message_id=sent_msg.message_id)

    data = await state.get_data()
    school_code = data.get("school_code")
    if school_code is None:
        sent = await callback.message.answer("Ошибка: код школы не найден. Пожалуйста, начните регистрацию заново.")
        await state.update_data(last_bot_message_id=sent.message_id, last_sticker_message_id=None)
        return

    school_data = SCHOOL_CODES[school_code]
    school_type = school_data["type"]

    if school_type == "обычная":
        keyboard = InlineKeyboardMarkup(
            inline_keyboard=[
                [InlineKeyboardButton(text=str(i), callback_data=f"class:{i}")]
                for i in range(5, 12)
            ]
        )
        sent = await callback.message.answer("В каком вы классе на данный момент 🫥?", reply_markup=keyboard)
        await state.set_state(SchoolStates.waiting_for_class)
        await state.update_data(last_bot_message_id=sent.message_id)
    elif school_type == "особенная":
        specializations = school_data["specializations"]
        specialization_keyboard = InlineKeyboardMarkup(
            inline_keyboard=[
                [InlineKeyboardButton(text=name, callback_data=f"specialization:{code}")]
                for code, name in specializations.items()
            ]
        )
        sent = await callback.message.answer("Теперь выберите направление:", reply_markup=specialization_keyboard)
        await state.set_state(SchoolStates.waiting_for_specialization)
        await state.update_data(last_bot_message_id=sent.message_id)


@router.callback_query(SchoolStates.waiting_for_class, F.data.startswith("class:"))
async def class_selection_handler(callback: CallbackQuery, state: FSMContext):
    await callback.answer()

    class_number = callback.data.split(":")[1]
    await state.update_data(class_number=class_number)

    back_keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="Назад", callback_data="back_to_class_choice")]
        ]
    )

    await callback.message.delete()
    sent = await callback.message.answer(
        f"✅ Вы выбрали класс: {class_number}!\nТеперь напишите букву класса:",
        reply_markup=back_keyboard
    )
    await state.set_state(SchoolStates.waiting_for_class_letter)
    await state.update_data(last_bot_message_id=sent.message_id)


@router.callback_query(F.data == "back_to_class_choice")
async def back_to_class_choice_callback(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    data = await state.get_data()
    school_code = data.get("school_code")
    if school_code is None:
        await callback.message.answer("Ошибка: код школы не найден.")
        return
    school_data = SCHOOL_CODES.get(school_code)
    if not school_data:
        await callback.message.answer("Ошибка: данные школы не найдены.")
        return
    school_type = school_data["type"]

    try:
        await callback.message.delete()
    except Exception:
        pass

    if school_type == "обычная":
        keyboard = InlineKeyboardMarkup(
            inline_keyboard=[
                [InlineKeyboardButton(text=str(i), callback_data=f"class:{i}")]
                for i in range(5, 12)
            ]
        )
        sent = await callback.message.answer("В каком вы классе на данный момент 🫥?", reply_markup=keyboard)
        await state.set_state(SchoolStates.waiting_for_class)
        await state.update_data(last_bot_message_id=sent.message_id)

    else:
        await callback.message.answer("Возврат к выбору класса для данного типа школы не поддерживается.")


@router.message(SchoolStates.waiting_for_class_letter)
async def class_letter_handler(message: Message, state: FSMContext):
    data = await state.get_data()
    last_bot_message_id = data.get("last_bot_message_id")
    last_sticker_message_id = data.get("last_sticker_message_id")

    await delete_messages(message.bot, message.chat.id,
                          [message.message_id, last_bot_message_id, last_sticker_message_id])

    letter = message.text.strip().lower()

    if re.fullmatch(r"[А-Яа-я]", letter) and letter.lower() not in ('ю', 'ъ', 'ь', 'э', 'ы'):
        await state.update_data(class_letter=letter.upper())
        sent = await message.answer("✅ Буква класса принята!")
        keyboard = InlineKeyboardMarkup(
            inline_keyboard=[
                [InlineKeyboardButton(
                    text="🔐 Сгенерировать пароль",
                    callback_data="generate_password"
                )]
            ]
        )
        sent2 = await message.answer("🔐 Теперь придумай пароль (не менее 6 символов, буквы и цифры).",
                                     reply_markup=keyboard)
        await state.set_state(SchoolStates.waiting_for_password)
        await state.update_data(last_bot_message_id=sent2.message_id, last_sticker_message_id=None)
    else:
        sent = await message.answer("❌ Пожалуйста, введите одну букву (кроме ю, э. ы, ъ и ь).")
        await state.update_data(last_bot_message_id=sent.message_id, last_sticker_message_id=None)


@router.callback_query(F.data == "generate_password")
async def generate_password_handler(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    charset = string.ascii_letters + string.digits
    password = ''.join(secrets.choice(charset) for _ in range(10))

    await state.update_data(generated_password=password)

    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="✅ Выбрать",
                    callback_data="accept_password"
                ),
                InlineKeyboardButton(
                    text="🔁 Другой",
                    callback_data="generate_password"
                )
            ],
            [
                InlineKeyboardButton(
                    text="🔙 Назад",
                    callback_data="back_to_password_prompt"
                )
            ]
        ]
    )

    try:
        await callback.message.edit_text(
            f"🔐 Случайный пароль: <code>{password}</code>",
            parse_mode="HTML",
            reply_markup=keyboard
        )
    except Exception:
        pass


@router.callback_query(F.data == "generate_mentor_password")
async def generate_mentor_password_handler(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    charset = string.ascii_letters + string.digits
    password = ''.join(secrets.choice(charset) for _ in range(10))

    await state.update_data(generated_password=password)

    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="✅ Выбрать",
                    callback_data="accept_mentor_password"
                ),
                InlineKeyboardButton(
                    text="🔁 Другой",
                    callback_data="generate_mentor_password"
                )
            ],
            [
                InlineKeyboardButton(
                    text="🔙 Назад",
                    callback_data="back_to_mentor_password_prompt"
                )
            ]
        ]
    )

    try:
        await callback.message.edit_text(
            f"🔐 Случайный пароль: <code>{password}</code>",
            parse_mode="HTML",
            reply_markup=keyboard
        )
    except Exception:
        pass


@router.callback_query(F.data == "back_to_password_prompt")
async def back_to_password_prompt(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="🔐 Сгенерировать пароль", callback_data="generate_password")]
        ]
    )
    try:
        await callback.message.edit_text(
            "🔐 Теперь придумай пароль (не менее 6 символов, буквы и цифры).",
            reply_markup=keyboard
        )
    except Exception:
        pass

    await state.set_state(SchoolStates.waiting_for_password)


@router.callback_query(F.data == "back_to_mentor_password_prompt")
async def back_to_mentor_password_prompt(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="🔐 Сгенерировать пароль", callback_data="generate_mentor_password")]
        ]
    )
    try:
        await callback.message.edit_text(
            "🔐 Теперь придумай пароль (не менее 6 символов, буквы и цифры).",
            reply_markup=keyboard
        )
    except Exception:
        pass

    await state.set_state(SchoolStates.waiting_for_mentor_password)


@router.callback_query(F.data == "accept_password")
async def accept_generated_password(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    data = await state.get_data()
    password = data.get("generated_password")
    if not password:
        await callback.message.answer("Пароль не найден. Попробуйте сгенерировать его заново.")
        return

    await state.update_data(password=password)

    try:
        await callback.message.edit_reply_markup(reply_markup=None)
    except Exception:
        pass

    sent_sticker = await callback.message.answer_sticker(
        "CAACAgIAAxkBAAEBUxpoRGUW4cPUbd3fx0SgcG_GwRDuPAACwz0AAswTKUqFD82aGooDRjYE")
    await state.update_data(last_sticker_message_id=sent_sticker.message_id)
    sent = await callback.message.answer("✅ Принято!")
    await state.update_data(last_bot_message_id=sent.message_id)

    nickname = data.get("nickname", "user").replace(" ", "_").lower()
    suffix = "@vibe.ye"
    emails = [
        f"{nickname}{random.randint(10, 99)}{suffix}",
        f"{nickname}_{random.choice(string.ascii_lowercase)}{random.randint(1, 9)}{suffix}",
        f"{random.choice(string.ascii_lowercase)}{nickname}{suffix}",
    ]
    await state.update_data(emails=emails)

    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text=email, callback_data=f"choose_email:{email}")]
            for email in emails
        ]
    )

    sent2 = await callback.message.answer("📧 Выбери почту из предложенных вариантов:", reply_markup=keyboard)
    await state.update_data(last_bot_message_id=sent2.message_id)

    await state.set_state(SchoolStates.waiting_for_email_choice)


@router.callback_query(F.data == "accept_mentor_password")
async def accept_generated_mentor_password(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    data = await state.get_data()
    password = data.get("generated_password")
    if not password:
        await callback.message.answer("Пароль не найден. Попробуйте сгенерировать его заново.")
        return

    await state.update_data(password=password)

    try:
        await callback.message.edit_reply_markup(reply_markup=None)
    except Exception:
        pass

    sent_sticker = await callback.message.answer_sticker(
        "CAACAgIAAxkBAAEBUxpoRGUW4cPUbd3fx0SgcG_GwRDuPAACwz0AAswTKUqFD82aGooDRjYE")
    await state.update_data(last_sticker_message_id=sent_sticker.message_id)
    sent = await callback.message.answer("✅ Принято!")
    await state.update_data(last_bot_message_id=sent.message_id)

    nickname = data.get("nickname", "user").replace(" ", "_").lower()
    suffix = "@vibe.ye"
    emails = [
        f"{nickname}{random.randint(10, 99)}{suffix}",
        f"{nickname}_{random.choice(string.ascii_lowercase)}{random.randint(1, 9)}{suffix}",
        f"{random.choice(string.ascii_lowercase)}{nickname}{suffix}",
    ]
    await state.update_data(emails=emails)

    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text=email, callback_data=f"choose_mentor_email:{email}")]
            for email in emails
        ]
    )

    sent2 = await callback.message.answer("📧 Выбери почту из предложенных вариантов:", reply_markup=keyboard)
    await state.update_data(last_bot_message_id=sent2.message_id)

    await state.set_state(SchoolStates.waiting_for_mentor_email_choice)


@router.message(SchoolStates.waiting_for_password)
async def registration_password_handler(message: Message, state: FSMContext):
    data = await state.get_data()
    last_bot_message_id = data.get("last_bot_message_id")
    last_sticker_message_id = data.get("last_sticker_message_id")

    ids_to_delete = []
    if message.message_id: ids_to_delete.append(message.message_id)
    if last_bot_message_id: ids_to_delete.append(last_bot_message_id)
    if last_sticker_message_id: ids_to_delete.append(last_sticker_message_id)
    try:
        await delete_messages(message.bot, message.chat.id, ids_to_delete)
    except Exception:
        pass

    password = message.text.strip()
    nickname = data.get("nickname", "").lower()

    def is_sequential(password: str) -> bool:
        sequences = ['0123', '9876543210', '43210', '9101112']
        for seq in sequences:
            for i in range(len(seq) - 2):
                if seq[i:i + 3] in password:
                    return True
        return False

    def is_too_simple(password: str) -> bool:
        for size in range(1, len(password) // 2 + 1):
            pattern = password[:size]
            repeats = len(password) // size
            if pattern * repeats == password:
                return True
        return False

    def is_repeated_char(password: str) -> bool:
        return len(set(password)) == 1

    if len(password) < 6:
        sent = await message.answer("⚠️ Пароль слишком короткий. Попробуй не менее 6 символов:")
        sent_sticker = await message.answer_sticker(
            "CAACAgIAAxkBAAEBUx1oRJfE3q0TcxKwHLZphTvumzYLEgACcTsAArVDWUo6XMAuPW2eHTYE")
        await state.update_data(last_bot_message_id=sent.message_id, last_sticker_message_id=sent_sticker.message_id)
        return

    if is_repeated_char(password):
        sent_sticker = await message.answer_sticker(
            "CAACAgIAAxkBAAEBUx9oRJh9otcsYTyzz78pEjnwT7SNeQAC80EAAm-zaElfo-DQ18SjdjYE")
        sent2 = await message.answer(
            "⚠️ Пароль не может состоять из одного повторяющегося символа (например, 000000, aaaaaa):")
        await state.update_data(last_bot_message_id=sent2.message_id, last_sticker_message_id=sent_sticker.message_id)
        return

    for i in range(len(nickname) - 2):
        part = nickname[i:i + 3]
        if part in password.lower():
            sent_sticker = await message.answer_sticker(
                "CAACAgIAAxkBAAEBUx9oRJh9otcsYTyzz78pEjnwT7SNeQAC80EAAm-zaElfo-DQ18SjdjYE")
            sent2 = await message.answer("⚠️ Пароль не должен содержать часть вашего никнейма. Попробуй снова:")
            await state.update_data(last_bot_message_id=sent2.message_id,
                                    last_sticker_message_id=sent_sticker.message_id)
            return

    if any(str(y) in password for y in range(1980, 2025)):
        sent_sticker = await message.answer_sticker(
            "CAACAgIAAxkBAAEBUx9oRJh9otcsYTyzz78pEjnwT7SNeQAC80EAAm-zaElfo-DQ18SjdjYE")
        sent2 = await message.answer("⚠️ Пароль не должен быть похож на дату рождения. Попробуй снова:")
        await state.update_data(last_bot_message_id=sent2.message_id, last_sticker_message_id=sent_sticker.message_id)
        return

    if is_too_simple(password):
        sent_sticker = await message.answer_sticker(
            "CAACAgIAAxkBAAEBUx9oRJh9otcsYTyzz78pEjnwT7SNeQAC80EAAm-zaElfo-DQ18SjdjYE")
        sent2 = await message.answer(
            "⚠️ Пароль слишком простой и должен содержать хотя бы одну букву или цифру. Используй менее очевидную комбинацию:")
        await state.update_data(last_bot_message_id=sent2.message_id, last_sticker_message_id=sent_sticker.message_id)
        return

    if is_sequential(password):
        sent_sticker = await message.answer_sticker(
            "CAACAgIAAxkBAAEBUx9oRJh9otcsYTyzz78pEjnwT7SNeQAC80EAAm-zaElfo-DQ18SjdjYE")
        sent2 = await message.answer(
            "⚠️ Пароль не должен содержать простые последовательности цифр (например, 1234, 9876). Попробуй снова:")
        await state.update_data(last_bot_message_id=sent2.message_id, last_sticker_message_id=sent_sticker.message_id)
        return

    if not any(c.isalpha() for c in password) or not any(c.isdigit() for c in password):
        sent_sticker = await message.answer_sticker(
            "CAACAgIAAxkBAAEBUx9oRJh9otcsYTyzz78pEjnwT7SNeQAC80EAAm-zaElfo-DQ18SjdjYE")
        sent2 = await message.answer("⚠️ Пароль должен содержать как минимум одну букву И как минимум одну цифру:")
        await state.update_data(last_bot_message_id=sent2.message_id, last_sticker_message_id=sent_sticker.message_id)
        return

    await state.update_data(password=password)
    sent_sticker = await message.answer_sticker(
        "CAACAgIAAxkBAAEBUxpoRGUW4cPUbd3fx0SgcG_GwRDuPAACwz0AAswTKUqFD82aGooDRjYE")
    await state.update_data(last_sticker_message_id=sent_sticker.message_id)
    sent = await message.answer("✅ Принято!")
    await state.update_data(last_bot_message_id=sent.message_id)

    nickname = data.get("nickname", "user").replace(" ", "_").lower()
    suffix = "@vibe.ye"
    emails = [
        f"{nickname}{random.randint(10, 99)}{suffix}",
        f"{nickname}_{random.choice(string.ascii_lowercase)}{random.randint(1, 9)}{suffix}",
        f"{random.choice(string.ascii_lowercase)}{nickname}{suffix}",
    ]
    await state.update_data(emails=emails)

    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text=email, callback_data=f"choose_email:{email}")]
            for email in emails
        ]
    )

    sent2 = await message.answer("📧 Выбери почту из предложенных вариантов:", reply_markup=keyboard)
    await state.update_data(last_bot_message_id=sent2.message_id)


@router.message(SchoolStates.waiting_for_mentor_password)
async def mentor_password_handler(message: Message, state: FSMContext):
    data = await state.get_data()
    last_bot_message_id = data.get("last_bot_message_id")
    last_sticker_message_id = data.get("last_sticker_message_id")

    ids_to_delete = []
    if message.message_id: ids_to_delete.append(message.message_id)
    if last_bot_message_id: ids_to_delete.append(last_bot_message_id)
    if last_sticker_message_id: ids_to_delete.append(last_sticker_message_id)
    try:
        await delete_messages(message.bot, message.chat.id, ids_to_delete)
    except Exception:
        pass

    password = message.text.strip()
    nickname = data.get("nickname", "").lower()

    def is_sequential(password: str) -> bool:
        sequences = ['0123', '9876543210', '43210', '9101112']
        for seq in sequences:
            for i in range(len(seq) - 2):
                if seq[i:i + 3] in password:
                    return True
        return False

    def is_too_simple(password: str) -> bool:
        for size in range(1, len(password) // 2 + 1):
            pattern = password[:size]
            repeats = len(password) // size
            if pattern * repeats == password:
                return True
        return False

    def is_repeated_char(password: str) -> bool:
        return len(set(password)) == 1

    if len(password) < 6:
        sent = await message.answer("⚠️ Пароль слишком короткий. Попробуй не менее 6 символов:")
        sent_sticker = await message.answer_sticker(
            "CAACAgIAAxkBAAEBUx1oRJfE3q0TcxKwHLZphTvumzYLEgACcTsAArVDWUo6XMAuPW2eHTYE")
        await state.update_data(last_bot_message_id=sent.message_id, last_sticker_message_id=sent_sticker.message_id)
        return

    if is_repeated_char(password):
        sent_sticker = await message.answer_sticker(
            "CAACAgIAAxkBAAEBUx9oRJh9otcsYTyzz78pEjnwT7SNeQAC80EAAm-zaElfo-DQ18SjdjYE")
        sent2 = await message.answer(
            "⚠️ Пароль не может состоять из одного повторяющегося символа (например, 000000, aaaaaa):")
        await state.update_data(last_bot_message_id=sent2.message_id, last_sticker_message_id=sent_sticker.message_id)
        return

    for i in range(len(nickname) - 2):
        part = nickname[i:i + 3]
        if part in password.lower():
            sent_sticker = await message.answer_sticker(
                "CAACAgIAAxkBAAEBUx9oRJh9otcsYTyzz78pEjnwT7SNeQAC80EAAm-zaElfo-DQ18SjdjYE")
            sent2 = await message.answer("⚠️ Пароль не должен содержать часть вашего никнейма. Попробуй снова:")
            await state.update_data(last_bot_message_id=sent2.message_id,
                                    last_sticker_message_id=sent_sticker.message_id)
            return

    if any(str(y) in password for y in range(1980, 2025)):
        sent_sticker = await message.answer_sticker(
            "CAACAgIAAxkBAAEBUx9oRJh9otcsYTyzz78pEjnwT7SNeQAC80EAAm-zaElfo-DQ18SjdjYE")
        sent2 = await message.answer("⚠️ Пароль не должен быть похож на дату рождения. Попробуй снова:")
        await state.update_data(last_bot_message_id=sent2.message_id, last_sticker_message_id=sent_sticker.message_id)
        return

    if is_too_simple(password):
        sent_sticker = await message.answer_sticker(
            "CAACAgIAAxkBAAEBUx9oRJh9otcsYTyzz78pEjnwT7SNeQAC80EAAm-zaElfo-DQ18SjdjYE")
        sent2 = await message.answer(
            "⚠️ Пароль слишком простой и должен содержать хотя бы одну букву или цифру. Используй менее очевидную комбинацию:")
        await state.update_data(last_bot_message_id=sent2.message_id, last_sticker_message_id=sent_sticker.message_id)
        return

    if is_sequential(password):
        sent_sticker = await message.answer_sticker(
            "CAACAgIAAxkBAAEBUx9oRJh9otcsYTyzz78pEjnwT7SNeQAC80EAAm-zaElfo-DQ18SjdjYE")
        sent2 = await message.answer(
            "⚠️ Пароль не должен содержать простые последовательности цифр (например, 1234, 9876). Попробуй снова:")
        await state.update_data(last_bot_message_id=sent2.message_id, last_sticker_message_id=sent_sticker.message_id)
        return

    if not any(c.isalpha() for c in password) or not any(c.isdigit() for c in password):
        sent_sticker = await message.answer_sticker(
            "CAACAgIAAxkBAAEBUx9oRJh9otcsYTyzz78pEjnwT7SNeQAC80EAAm-zaElfo-DQ18SjdjYE")
        sent2 = await message.answer("⚠️ Пароль должен содержать как минимум одну букву И как минимум одну цифру:")
        await state.update_data(last_bot_message_id=sent2.message_id, last_sticker_message_id=sent_sticker.message_id)
        return

    await state.update_data(password=password)
    sent_sticker = await message.answer_sticker(
        "CAACAgIAAxkBAAEBUxpoRGUW4cPUbd3fx0SgcG_GwRDuPAACwz0AAswTKUqFD82aGooDRjYE")
    await state.update_data(last_sticker_message_id=sent_sticker.message_id)
    sent = await message.answer("✅ Принято!")
    await state.update_data(last_bot_message_id=sent.message_id)

    nickname = data.get("nickname", "user").replace(" ", "_").lower()
    suffix = "@vibe.ye"
    emails = [
        f"{nickname}{random.randint(10, 99)}{suffix}",
        f"{nickname}_{random.choice(string.ascii_lowercase)}{random.randint(1, 9)}{suffix}",
        f"{random.choice(string.ascii_lowercase)}{nickname}{suffix}",
    ]
    await state.update_data(emails=emails)

    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text=email, callback_data=f"choose_mentor_email:{email}")]
            for email in emails
        ]
    )

    sent2 = await message.answer("📧 Выбери почту из предложенных вариантов:", reply_markup=keyboard)
    await state.update_data(last_bot_message_id=sent2.message_id)
    await state.set_state(SchoolStates.waiting_for_mentor_email_choice)


@router.callback_query(F.data.startswith("choose_email:"))
async def email_choice_handler(callback: CallbackQuery, state: FSMContext):
    email = callback.data.removeprefix("choose_email:")
    await callback.answer()

    data = await state.get_data()
    user_id = callback.from_user.id

    main_school_code = data.get("main_school_code")
    main_school_data = SCHOOL_CODES.get(main_school_code, {})
    main_school_name = main_school_data.get("name", "не указано")
    main_school_type = main_school_data.get("type", "обычная")

    additional_school_code = data.get("additional_school_code")
    additional_school_name = data.get("additional_school_name", "не указано")

    nickname = data.get("nickname", "не указан")
    password = data.get("password", "не указан")
    identity = data.get("identity", "не указана")
    specialization = data.get("specialization", "не указано")
    course = data.get("course", "не указан")
    class_number = data.get("class_number", "")
    class_letter = data.get("class_letter", "")

    try:
        await callback.message.delete()
    except Exception:
        pass

    await state.update_data(
        telegram_user_id=user_id,
        nickname=nickname,
        password=password,
        email=email,
        identity=identity,
        class_number=class_number,
        class_letter=class_letter,
        specialization=specialization,
        course=course,
        main_school_code=main_school_code,
        main_school_name=main_school_name,
        additional_school_code=additional_school_code,
        additional_school_name=additional_school_name
    )

    updated_data = await state.get_data()
    telegram_id = callback.from_user.id

    success, platform_user_id = await send_registration_to_api(updated_data, telegram_id)

    if success:
        await state.update_data(platform_user_id=platform_user_id)
        print("✅ Данные отправлены в БД")
    else:
        await callback.message.answer("⚠️ Ошибка при сохранении. Попробуйте позже.")
        print("❌ Не удалось отправить данные в БД")

    updated_data = await state.get_data()
    platform_user_id = updated_data.get("platform_user_id", "не указан")

    user_message = (
        f"🎉 Регистрация завершена!\n\n"
        f"🆔 ID на платформе: `{platform_user_id}`\n"
        f"🏢 Школа: `{main_school_name}`\n"
        f"👤 Никнейм: `{nickname}`\n"
        f"🔑 Пароль: `{password}`\n"
        f"📧 Почта: `{email}`\n"
        f"🧑 Роль: `{identity}`\n"
    )

    if main_school_type == "обычная":
        class_info = f"{class_number}{class_letter}" if class_number and class_letter else "не указан"
        user_message += f"🏫 Класс: `{class_info}`\n"
    elif main_school_type == "особенная":
        user_message += (
            f"➡️ Направление: `{specialization}`\n"
            f"📚 Курс: `{course}`\n"
        )

    if additional_school_code and additional_school_code != main_school_code:
        user_message += (
            f"\n📌 ДОПОЛНИТЕЛЬНАЯ ШКОЛА:\n"
            f"🏢 Школа: `{additional_school_name}`\n"
            f"➡️ Направление: `{specialization}`\n"
            f"📚 Курс: `{course}`\n"
        )

    edit_keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="✏️ Изменить профиль", callback_data=f"edit_profile:{BOT_SESSION_ID}")],
            [InlineKeyboardButton(text="➕ Добавить школу", callback_data=f"add_school:{BOT_SESSION_ID}")],
            [InlineKeyboardButton(text="🔑 Вход", url="https://vuntgram.vercel.app")],
            [InlineKeyboardButton(text="Поддержка 💬", url="https://t.me/VuntgramSupport_bot")]
        ]
    )

    await callback.message.answer(user_message, parse_mode=ParseMode.MARKDOWN, reply_markup=edit_keyboard)

    admin_message = (
        f"🎉 Регистрация завершена!\n\n"
        f"👤 Пользователь ID (Telegram): `{user_id}`\n"
        f"🆔 ID на платформе: `{platform_user_id}`\n"
        f"🏢 Школа: `{main_school_name}`\n"
        f"👤 Никнейм: `{nickname}`\n"
        f"🔑 Пароль: `{password}`\n"
        f"📧 Почта: `{email}`\n"
        f"🧑 Роль: `{identity}`\n"
    )

    if main_school_type == "обычная":
        admin_message += f"🏫 Класс: `{class_number}{class_letter}`\n"
    elif main_school_type == "особенная":
        admin_message += (
            f"➡️ Направление: `{specialization}`\n"
            f"📚 Курс: `{course}`\n"
        )

    if additional_school_code and additional_school_code != main_school_code:
        admin_message += (
            f"\n📌 ДОП. Школа: `{additional_school_name}`\n"
            f"➡️ Направление: `{specialization}`\n"
            f"📚 Курс: `{course}`\n"
        )

    safe_text = urllib.parse.quote_plus(admin_message)
    url = f"https://api.telegram.org/bot{ADMIN_BOT_TOKEN}/sendMessage?chat_id={ADMIN_CHAT_ID}&text={safe_text}"

    try:
        response = requests.get(url)
        if response.status_code != 200:
            print("Ошибка при отправке сообщения админу:", response.text)
    except Exception as e:
        print(f"Ошибка при отправке запроса админу: {e}")


@router.callback_query(F.data.startswith("choose_mentor_email:"))
async def mentor_email_choice_handler(callback: CallbackQuery, state: FSMContext):
    email = callback.data.removeprefix("choose_mentor_email:")
    await callback.answer()

    data = await state.get_data()
    user_id = callback.from_user.id

    main_school_code = data.get("main_school_code")
    main_school_data = SCHOOL_CODES.get(main_school_code, {})
    main_school_name = main_school_data.get("name", "не указано")
    main_school_type = main_school_data.get("type", "обычная")

    nickname = data.get("nickname", "не указан")
    password = data.get("password", "не указан")
    identity = data.get("identity", "не указана")
    specialization = data.get("specialization", "не указано")

    try:
        await callback.message.delete()
    except Exception:
        pass

    await state.update_data(
        telegram_user_id=user_id,
        nickname=nickname,
        password=password,
        email=email,
        identity=identity,
        specialization=specialization,
        main_school_code=main_school_code,
        main_school_name=main_school_name,
    )

    updated_data = await state.get_data()
    telegram_id = callback.from_user.id

    success, platform_user_id = await send_registration_to_api(updated_data, telegram_id)

    if success:
        await state.update_data(platform_user_id=platform_user_id)
        print("✅ Данные отправлены в БД")
    else:
        await callback.message.answer("⚠️ Ошибка при сохранении. Попробуйте позже.")
        print("❌ Не удалось отправить данные в БД")

    updated_data = await state.get_data()
    platform_user_id = updated_data.get("platform_user_id", "не указан")

    user_message = (
        f"🎉 Регистрация завершена!\n\n"
        f"🆔 ID на платформе: `{platform_user_id}`\n"
        f"🏢 Школа: `{main_school_name}`\n"
        f"👤 Никнейм: `{nickname}`\n"
        f"🔑 Пароль: `{password}`\n"
        f"📧 Почта: `{email}`\n"
        f"🧑 Роль: `{identity}`\n"
        f"➡️ Направление: `{specialization}`\n"
    )

    edit_keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="✏️ Изменить профиль", callback_data=f"edit_profile:{BOT_SESSION_ID}")],
            [InlineKeyboardButton(text="🔑 Вход", url="https://vuntgram.vercel.app")],
            [InlineKeyboardButton(text="Поддержка 💬", url="https://t.me/VuntgramSupport_bot")]
        ]
    )

    await callback.message.answer(user_message, parse_mode=ParseMode.MARKDOWN, reply_markup=edit_keyboard)

    admin_message = (
        f"🎉 Регистрация завершена!\n\n"
        f"👤 Пользователь ID (Telegram): `{user_id}`\n"
        f"🆔 ID на платформе: `{platform_user_id}`\n"
        f"🏢 Школа: `{main_school_name}`\n"
        f"👤 Никнейм: `{nickname}`\n"
        f"🔑 Пароль: `{password}`\n"
        f"📧 Почта: `{email}`\n"
        f"🧑 Роль: `{identity}`\n"
        f"➡️ Направление: `{specialization}`\n"
    )

    safe_text = urllib.parse.quote_plus(admin_message)
    url = f"https://api.telegram.org/bot{ADMIN_BOT_TOKEN}/sendMessage?chat_id={ADMIN_CHAT_ID}&text={safe_text}"

    try:
        response = requests.get(url)
        if response.status_code != 200:
            print("Ошибка при отправке сообщения админу:", response.text)
    except Exception as e:
        print(f"Ошибка при отправке запроса админу: {e}")


@router.callback_query(F.data.startswith("add_school"))
async def add_school_callback(callback: CallbackQuery, state: FSMContext):
    try:
        _, session_id = callback.data.split(":")
    except ValueError:
        await callback.answer("❌ Неверный формат кнопки.")
        return

    if session_id != BOT_SESSION_ID:
        await callback.answer("⚠️ Это устаревшая кнопка. Пожалуйста, нажмите /start.", show_alert=True)
        return

    await callback.answer()
    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="🔙 Назад", callback_data="back_to_profile")]
        ]
    )
    await callback.message.answer("🔐 Пожалуйста, введите *код приглашения* для новой школы.", reply_markup=keyboard)
    await state.set_state(SchoolStates.waiting_for_school_code)


@router.message(SchoolStates.waiting_for_additional_school_code)
async def process_additional_school_code(message: Message, state: FSMContext):
    school_code = message.text.strip()

    if school_code not in SCHOOL_CODES:
        await message.answer("❌ Код школы не найден. Попробуйте ещё раз.")
        return

    school_name = SCHOOL_CODES[school_code]["name"]

    await state.update_data(
        additional_school_code=school_code,
        additional_school_name=school_name
    )

    data = await state.get_data()

    payload = {
        "telegram_user_id": data["telegram_user_id"],
        "nickname": data["nickname"],
        "email": data["email"],
        "password": data["password"],
        "identity": data["identity"],
        "main_school_code": data["main_school_code"],
        "main_school_name": data["main_school_name"],
        "class_number": data.get("class_number", "не указано"),
        "class_letter": data.get("class_letter", "не указано"),
        "specialization": data.get("specialization", "не указано"),
        "course": data.get("course", "не указано"),
        "additional_school_code": data.get("additional_school_code",  "не указано"),
        "additional_school_name": data.get("additional_school_name", "не указано")
    }

    async with aiohttp.ClientSession() as session:
        async with session.post("https://vuntserver-csaq.onrender.com/update_user", json=payload) as response:
            if response.status == 200:
                await message.answer("✅ Дополнительная школа успешно добавлена!")
            else:
                await message.answer("⚠️ Произошла ошибка при сохранении школы.")

    await state.clear()


@router.callback_query(F.data == "detach_school")
async def detach_school_callback(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="🔙 Назад", callback_data="back_to_profile")]
        ]
    )
    await state.update_data(school_code=None)
    await callback.message.answer(
        "Вы успешно отвязали свой аккаунт от текущей школы. Теперь вы можете зарегистрироваться в другой школе.")
    await callback.message.answer("🔐 Пожалуйста, введите *код приглашения* для новой школы.", reply_markup=keyboard)
    await state.set_state(SchoolStates.waiting_for_school_code)


@router.callback_query(F.data == "back_to_profile")
async def back_to_profile_callback(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    try:
        await callback.message.delete()
    except Exception as e:
        print(f"Ошибка при удалении сообщения: {e}")


@router.callback_query(F.data.startswith("edit_profile"))
async def edit_profile_callback(callback: CallbackQuery, state: FSMContext):
    try:
        _, session_id = callback.data.split(":")
    except ValueError:
        await callback.answer("❌ Неверный формат кнопки.")
        return

    if session_id != BOT_SESSION_ID:
        await callback.answer("⚠️ Это устаревшая кнопка. Пожалуйста, нажмите /start.", show_alert=True)
        return

    await callback.answer()
    data = await state.get_data()

    nickname = data.get("nickname", "не указан")
    password = data.get("password", "не указан")
    email = data.get("email", "не указана")
    identity = data.get("identity", "не указана")
    platform_user_id = data.get("platform_user_id", "не указан")

    main_school_code = data.get("main_school_code")
    main_school_data = SCHOOL_CODES.get(main_school_code, {})
    main_school_name = main_school_data.get("name", "не указано")
    main_school_type = main_school_data.get("type", "обычная")

    profile_parts = [
        f"🎉 Ваш профиль:\n",
        f"\n🆔 ID на платформе: `{platform_user_id}`",
        f"\n🏢 Основная школа: `{main_school_name}`",
        f"\n👤 Никнейм: `{nickname}`",
        f"\n🔑 Пароль: `{password}`",
        f"\n📧 Почта: `{email}`",
        f"\n🧑 Роль: `{identity}`"
    ]

    class_number = data.get("class_number")
    class_letter = data.get("class_letter", "")
    if main_school_type == "обычная" and class_number:
        profile_parts.append(f"\n🏫 Класс: `{class_number}{class_letter}`")

    additional_school_code = data.get("additional_school_code")
    additional_school_data = SCHOOL_CODES.get(additional_school_code) if additional_school_code else None

    specialization = data.get("specialization")
    course = data.get("course")

    if main_school_type == "ментор_вшп":  # Для менторов ВШП
        if specialization:
            profile_parts.append(f"\n➡️ Направление: `{specialization}`")
    elif main_school_type == "особенная":
        if specialization:
            profile_parts.append(f"\n➡️ Направление: `{specialization}`")
        if course:
            profile_parts.append(f"\n📚 Курс: `{course}`")

    if additional_school_code and additional_school_data and additional_school_code != main_school_code:
        additional_school_name = additional_school_data.get("name", "не указано")
        additional_school_type = additional_school_data.get("type", "обычная")

        profile_parts.append("\n\n📌 ДОПОЛНИТЕЛЬНО:")
        profile_parts.append(f"\n🏢 Школа: `{additional_school_name}`")

        if additional_school_type == "особенная":
            if course and course not in ["не указан", "None"]:
                profile_parts.append(f"\n📚 Курс: `{course}`")
            if specialization and specialization not in ["не указано", "None"]:
                profile_parts.append(f"\n➡️ Направление: `{specialization}`")

    profile_text = "".join(profile_parts)

    keyboard_buttons = [
        [InlineKeyboardButton(text="✏️ Никнейм", callback_data=f"edit_field:nickname:{BOT_SESSION_ID}")],
        [InlineKeyboardButton(text="🔑 Пароль", callback_data=f"edit_field:password:{BOT_SESSION_ID}")],
    ]

    if main_school_type != "ментор_вшп":  # Менторам ВШП нельзя менять роль
        keyboard_buttons.append(
            [InlineKeyboardButton(text="🧑 Роль", callback_data=f"edit_field:identity:{BOT_SESSION_ID}")])

    if main_school_type == "обычная":
        keyboard_buttons.append(
            [InlineKeyboardButton(text="🏢 Основная школа", callback_data=f"edit_field:main_school:{BOT_SESSION_ID}")])
        keyboard_buttons.append(
            [InlineKeyboardButton(text="🏫 Класс", callback_data=f"edit_field:class:{BOT_SESSION_ID}")])
    elif main_school_type == "особенная":
        keyboard_buttons.append(
            [InlineKeyboardButton(text="🏢 Основная школа", callback_data=f"edit_field:main_school:{BOT_SESSION_ID}")])
        keyboard_buttons.append(
            [InlineKeyboardButton(text="📚 Курс", callback_data=f"edit_field:course:{BOT_SESSION_ID}")])
        keyboard_buttons.append(
            [InlineKeyboardButton(text="➡️ Направление", callback_data=f"edit_field:specialization:{BOT_SESSION_ID}")])
    elif main_school_type == "ментор_вшп":  # Для менторов ВШП
        keyboard_buttons.append(
            [InlineKeyboardButton(text="➡️ Направление", callback_data=f"edit_field:specialization:{BOT_SESSION_ID}")])

    keyboard_buttons.append([InlineKeyboardButton(text="✅ Готово", callback_data=f"edit_field:done:{BOT_SESSION_ID}")])

    keyboard = InlineKeyboardMarkup(inline_keyboard=keyboard_buttons)

    try:
        await callback.message.edit_text(
            profile_text,
            reply_markup=keyboard,
            parse_mode=ParseMode.MARKDOWN
        )
    except TelegramBadRequest as e:
        if "message is not modified" in str(e):
            pass
        else:
            raise

    await state.set_state(SchoolStates.editing_profile_field)


@router.callback_query(SchoolStates.editing_profile_field, F.data.startswith("edit_field:"))
async def edit_field_choice(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    parts = callback.data.split(":")
    field = parts[1]
    session_id = parts[2] if len(parts) > 2 else None

    if session_id and session_id != BOT_SESSION_ID:
        await callback.answer("⚠️ Это устаревшая кнопка. Пожалуйста, нажмите /start.", show_alert=True)
        return

    data = await state.get_data()
    main_school_type = data.get("main_school_data", {}).get("type")

    if field == "done":
        await show_profile_summary(callback, state)
        await state.set_state(None)
        return

    if field == "nickname":
        await callback.message.edit_text("🧑‍🎓 Пожалуйста, введите новый никнейм:")
        await state.set_state(SchoolStates.editing_nickname)
    elif field == "password":
        keyboard = InlineKeyboardMarkup(
            inline_keyboard=[
                [InlineKeyboardButton(text="🔐 Сгенерировать пароль", callback_data="generate_password_edit")],
                [InlineKeyboardButton(text="🔙 Назад", callback_data=f"edit_field:back:{BOT_SESSION_ID}")]
            ]
        )
        await callback.message.edit_text("🔐 Пожалуйста, введите новый пароль (не менее 6 символов, буквы и цифры).",
                                         reply_markup=keyboard)
        await state.set_state(SchoolStates.editing_password)
    elif field == "identity":
        identity_keyboard = InlineKeyboardMarkup(
            inline_keyboard=[
                [
                    InlineKeyboardButton(text="🧑‍🎓 Ученик", callback_data="edit_identity:ученик"),
                    InlineKeyboardButton(text="👩‍🎓 Ученица", callback_data="edit_identity:ученица"),
                ],
                [InlineKeyboardButton(text="🔙 Назад", callback_data=f"edit_field:back:{BOT_SESSION_ID}")]
            ]
        )
        await callback.message.edit_text("👤 Пожалуйста, выберите новую роль:", reply_markup=identity_keyboard)
        await state.set_state(SchoolStates.editing_identity)
    elif field == "class":
        keyboard = InlineKeyboardMarkup(
            inline_keyboard=[
                                [InlineKeyboardButton(text=str(i), callback_data=f"edit_class:{i}")]
                                for i in range(5, 12)
                            ] + [[InlineKeyboardButton(text="🔙 Назад",
                                                       callback_data=f"edit_field:back:{BOT_SESSION_ID}")]]
        )
        await callback.message.edit_text("В каком вы классе на данный момент? 🫥", reply_markup=keyboard)
        await state.set_state(SchoolStates.editing_class)
    elif field == "specialization":
        school_code = (await state.get_data()).get(
            "main_school_code")  # Используем main_school_code для определения специализаций
        if school_code:
            specializations = SCHOOL_CODES[school_code].get("specializations", {})
            specialization_keyboard = InlineKeyboardMarkup(
                inline_keyboard=[
                                    [InlineKeyboardButton(text=name, callback_data=f"edit_specialization:{code}")]
                                    for code, name in specializations.items()
                                ] + [[InlineKeyboardButton(text="🔙 Назад",
                                                           callback_data=f"edit_field:back:{BOT_SESSION_ID}")]]
            )
            await callback.message.edit_text("Пожалуйста, выберите новое направление:",
                                             reply_markup=specialization_keyboard)
            await state.set_state(SchoolStates.editing_specialization)
        else:
            await callback.message.answer("Ошибка: код школы не найден.")
    elif field == "course":
        keyboard = InlineKeyboardMarkup(
            inline_keyboard=[
                                [InlineKeyboardButton(text=str(i), callback_data=f"edit_course:{i}")]
                                for i in range(1, 6)
                            ] + [[InlineKeyboardButton(text="🔙 Назад",
                                                       callback_data=f"edit_field:back:{BOT_SESSION_ID}")]]
        )
        await callback.message.edit_text("Пожалуйста, выберите новый курс:", reply_markup=keyboard)
        await state.set_state(SchoolStates.editing_course)
    elif field == "main_school":
        keyboard = InlineKeyboardMarkup(
            inline_keyboard=[
                [InlineKeyboardButton(text="🔙 Назад", callback_data=f"edit_field:back:{BOT_SESSION_ID}")]
            ]
        )
        await callback.message.edit_text(
            "🔐 Введите код новой основной школы (обычной):",
            reply_markup=keyboard
        )
        await state.set_state(SchoolStates.editing_main_school)
    elif field == "back":
        await show_profile_summary(callback, state)
        await state.set_state(SchoolStates.editing_profile_field)


@router.callback_query(SchoolStates.editing_main_school, F.data.startswith("edit_field:back"))
async def back_from_main_school_edit(callback: CallbackQuery, state: FSMContext):
    try:
        _, _, session_id = callback.data.split(":")
    except ValueError:
        await callback.answer("❌ Неверный формат кнопки.")
        return

    if session_id != BOT_SESSION_ID:
        await callback.answer("⚠️ Это устаревшая кнопка. Пожалуйста, нажмите /start.", show_alert=True)
        return

    await callback.answer()
    await show_profile_summary(callback, state)
    await state.set_state(SchoolStates.editing_profile_field)


@router.message(SchoolStates.editing_nickname)
async def editing_nickname_handler(message: Message, state: FSMContext):
    data = await state.get_data()
    last_bot_message_id = data.get("last_bot_message_id")
    last_sticker_message_id = data.get("last_sticker_message_id")

    await delete_messages(message.bot, message.chat.id,
                          [message.message_id, last_bot_message_id, last_sticker_message_id])

    nickname_input = message.text.strip()

    if not re.fullmatch(r"[A-Za-zА-Яа-яёЁ\s\-_]+", nickname_input):
        sent_sticker = await message.answer_sticker(
            "CAACAgIAAxkBAAEBUx9oRJh9otcsYTyzz78pEjnwT7SNeQAC80EAAm-zaElfo-DQ18SjdjYE")
        sent2 = await message.answer(
            "⚠️ Никнейм должен содержать только буквы, подчёркивания, пробелы или дефис. Попробуй снова.")
        await state.update_data(last_bot_message_id=sent2.message_id, last_sticker_message_id=sent_sticker.message_id)
        return

    if re.search(r"[\s\-_]$", nickname_input):
        sent_sticker = await message.answer_sticker(
            "CAACAgIAAxkBAAEBUx9oRJh9otcsYTyzz78pEjnwT7SNeQAC80EAAm-zaElfo-DQ18SjdjYE")
        sent2 = await message.answer("⚠️ Никнейм не должен заканчиваться на пробел, подчёркивание или дефис.")
        await state.update_data(last_bot_message_id=sent2.message_id, last_sticker_message_id=sent_sticker.message_id)
        return

    num_letters = len(re.findall(r"[A-Za-zА-Яа-яёЁ]", nickname_input))
    if num_letters < 3:
        sent_sticker = await message.answer_sticker(
            "CAACAgIAAxkBAAEBUx9oRJh9otcsYTyzz78pEjnwT7SNeQAC80EAAm-zaElfo-DQ18SjdjYE")
        sent2 = await message.answer("⚠️ В никнейме должно быть минимум 3 буквы (не считая символы и подчёркивания).")
        await state.update_data(last_bot_message_id=sent2.message_id, last_sticker_message_id=sent_sticker.message_id)
        return

    if contains_bad_words(nickname_input):
        sent_sticker = await message.answer_sticker(
            "CAACAgIAAxkBAAEBU49oRXIQke73ZhxrtV6BPOp8A524aAACLDEAAlf4QEvL1oswk3KNSDYE")
        sent2 = await message.answer(
            "🚫 Ваш ник содержит или может содержать недопустимые или оскорбительные слова. Пожалуйста, выберите другой.")
        await state.update_data(last_bot_message_id=sent2.message_id, last_sticker_message_id=sent_sticker.message_id)
        return

    await state.update_data(nickname=nickname_input)

    sent = await message.answer("✅ Никнейм успешно изменён!")
    await state.update_data(last_bot_message_id=sent.message_id)
    await show_profile_summary(message, state)
    await state.set_state(SchoolStates.editing_profile_field)


@router.callback_query(F.data == "generate_password_edit")
async def generate_password_edit_handler(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    charset = string.ascii_letters + string.digits
    password = ''.join(secrets.choice(charset) for _ in range(10))

    await state.update_data(generated_password=password)

    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="✅ Выбрать",
                    callback_data="accept_password_edit"
                ),
                InlineKeyboardButton(
                    text="🔁 Другой",
                    callback_data="generate_password_edit"
                )
            ],
            [
                InlineKeyboardButton(
                    text="🔙 Назад",
                    callback_data=f"edit_field:back:{BOT_SESSION_ID}"
                )
            ]
        ]
    )

    await callback.message.edit_text(
        f"🔐 Случайный пароль: <code>{password}</code>",
        parse_mode=ParseMode.HTML,
        reply_markup=keyboard
    )


@router.callback_query(F.data == "accept_password_edit")
async def accept_password_edit_handler(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    data = await state.get_data()
    password = data.get("generated_password")

    if not password:
        await callback.answer("⚠️ Пароль не найден. Попробуйте снова.")
        return

    await state.update_data(password=password)

    sent_sticker = await callback.message.answer_sticker(
        "CAACAgIAAxkBAAEBUxpoRGUW4cPUbd3fx0SgcG_GwRDuPAACwz0AAswTKUqFD82aGooDRjYE")
    await state.update_data(last_sticker_message_id=sent_sticker.message_id)
    sent = await callback.message.answer("✅ Пароль успешно изменён!")
    await state.update_data(last_bot_message_id=sent.message_id)
    await show_profile_summary(callback, state)
    await state.set_state(SchoolStates.editing_profile_field)


@router.message(SchoolStates.editing_password)
async def editing_password_handler(message: Message, state: FSMContext):
    data = await state.get_data()
    last_bot_message_id = data.get("last_bot_message_id")
    last_sticker_message_id = data.get("last_sticker_message_id")

    await delete_messages(message.bot, message.chat.id,
                          [message.message_id, last_bot_message_id, last_sticker_message_id])

    password = message.text.strip()
    nickname = data.get("nickname", "").lower()

    def is_sequential(password: str) -> bool:
        sequences = ['0123', '9876543210', '43210', '9101112']
        for seq in sequences:
            for i in range(len(seq) - 2):
                if seq[i:i + 3] in password:
                    return True
        return False

    def is_too_simple(password: str) -> bool:
        for size in range(1, len(password) // 2 + 1):
            pattern = password[:size]
            repeats = len(password) // size
            if pattern * repeats == password:
                return True
        return False

    def is_repeated_char(password: str) -> bool:
        return len(set(password)) == 1

    if len(password) < 6:
        sent = await message.answer("⚠️ Пароль слишком короткий. Попробуй не менее 6 символов:")
        sent_sticker = await message.answer_sticker(
            "CAACAgIAAxkBAAEBUx1oRJfE3q0TcxKwHLZphTvumzYLEgACcTsAArVDWUo6XMAuPW2eHTYE")
        await state.update_data(last_bot_message_id=sent.message_id, last_sticker_message_id=sent_sticker.message_id)
        return

    if is_repeated_char(password):
        sent_sticker = await message.answer_sticker(
            "CAACAgIAAxkBAAEBUx9oRJh9otcsYTyzz78pEjnwT7SNeQAC80EAAm-zaElfo-DQ18SjdjYE")
        sent2 = await message.answer(
            "⚠️ Пароль не может состоять из одного повторяющегося символа (например, 000000, aaaaaa):")
        await state.update_data(last_bot_message_id=sent2.message_id, last_sticker_message_id=sent_sticker.message_id)
        return

    for i in range(len(nickname) - 2):
        part = nickname[i:i + 3]
        if part in password.lower():
            sent_sticker = await message.answer_sticker(
                "CAACAgIAAxkBAAEBUx9oRJh9otcsYTyzz78pEjnwT7SNeQAC80EAAm-zaElfo-DQ18SjdjYE")
            sent2 = await message.answer("⚠️ Пароль не должен содержать часть вашего никнейма. Попробуй снова:")
            await state.update_data(last_bot_message_id=sent2.message_id,
                                    last_sticker_message_id=sent_sticker.message_id)
            return

    if any(str(y) in password for y in range(1980, 2025)):
        sent_sticker = await message.answer_sticker(
            "CAACAgIAAxkBAAEBUx9oRJh9otcsYTyzz78pEjnwT7SNeQAC80EAAm-zaElfo-DQ18SjdjYE")
        sent2 = await message.answer("⚠️ Пароль не должен быть похож на дату рождения. Попробуй снова:")
        await state.update_data(last_bot_message_id=sent2.message_id, last_sticker_message_id=sent_sticker.message_id)
        return

    if is_too_simple(password):
        sent_sticker = await message.answer_sticker(
            "CAACAgIAAxkBAAEBUx9oRJh9otcsYTyzz78pEjnwT7SNeQAC80EAAm-zaElfo-DQ18SjdjYE")
        sent2 = await message.answer(
            "⚠️ Пароль слишком простой и должен содержать хотя бы одну букву или цифру. Используй менее очевидную комбинацию:")
        await state.update_data(last_bot_message_id=sent2.message_id, last_sticker_message_id=sent_sticker.message_id)
        return

    if is_sequential(password):
        sent_sticker = await message.answer_sticker(
            "CAACAgIAAxkBAAEBUx9oRJh9otcsYTyzz78pEjnwT7SNeQAC80EAAm-zaElfo-DQ18SjdjYE")
        sent2 = await message.answer(
            "⚠️ Пароль не должен содержать простые последовательности цифр (например, 1234, 9876). Попробуй снова:")
        await state.update_data(last_bot_message_id=sent2.message_id, last_sticker_message_id=sent_sticker.message_id)
        return

    if not any(c.isalpha() for c in password) or not any(c.isdigit() for c in password):
        sent_sticker = await message.answer_sticker(
            "CAACAgIAAxkBAAEBUx9oRJh9otcsYTyzz78pEjnwT7SNeQAC80EAAm-zaElfo-DQ18SjdjYE")
        sent2 = await message.answer("⚠️ Пароль должен содержать как минимум одну букву И как минимум одну цифру:")
        await state.update_data(last_bot_message_id=sent2.message_id, last_sticker_message_id=sent_sticker.message_id)
        return

    sent_sticker = await message.answer_sticker(
        "CAACAgIAAxkBAAEBUxpoRGUW4cPUbd3fx0SgcG_GwRDuPAACwz0AAswTKUqFD82aGooDRjYE")
    await state.update_data(last_sticker_message_id=sent_sticker.message_id)
    await state.update_data(password=password)
    sent = await message.answer("✅ Пароль успешно изменён!")
    await state.update_data(last_bot_message_id=sent.message_id)
    await show_profile_summary(message, state)
    await state.set_state(SchoolStates.editing_profile_field)


@router.callback_query(SchoolStates.editing_identity, F.data.startswith("edit_identity:"))
async def editing_identity_callback(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    role = callback.data.split(":", 1)[1]
    await state.update_data(identity=role)

    sent_sticker = await callback.message.answer_sticker(
        "CAACAgIAAxkBAAEBVLNoSA5bX7s1Lg2VmofAqPSk5viOpwACEjUAAsenoUqpHiuzlnPN-jYE")
    await state.update_data(last_sticker_message_id=sent_sticker.message_id)
    sent_msg = await callback.message.answer("✅ Роль успешно изменена!")
    await state.update_data(last_bot_message_id=sent_msg.message_id)

    await show_profile_summary(callback, state)
    await state.set_state(SchoolStates.editing_profile_field)


@router.callback_query(SchoolStates.editing_email_choice, F.data.startswith("choose_email_edit:"))
async def editing_email_choice_handler(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    email = callback.data.split(":", 1)[1]
    await state.update_data(email=email)

    sent_msg = await callback.message.answer("✅ Email успешно изменён!")
    await state.update_data(last_bot_message_id=sent_msg.message_id)

    await show_profile_summary(callback, state)
    await state.set_state(SchoolStates.editing_profile_field)


@router.callback_query(SchoolStates.editing_class, F.data.startswith("edit_class:"))
async def editing_class_handler(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    class_number = callback.data.split(":", 1)[1]
    await state.update_data(class_number=class_number)

    back_keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="🔙 Назад", callback_data=f"edit_field:back:{BOT_SESSION_ID}")]
        ]
    )

    await callback.message.edit_text(
        f"✅ Выбран класс: {class_number}!\nТеперь введите букву класса:",
        reply_markup=back_keyboard
    )
    await state.set_state(SchoolStates.editing_class_letter)


@router.message(SchoolStates.editing_main_school)
async def edit_main_school_handler(message: Message, state: FSMContext):
    data = await state.get_data()
    last_bot_message_id = data.get("last_bot_message_id")

    await delete_messages(message.bot, message.chat.id, [message.message_id, last_bot_message_id])

    code = message.text.strip()

    if code in SCHOOL_CODES:
        school_data = SCHOOL_CODES[code]

        if school_data["type"] != "обычная":
            sent = await message.answer(
                "❌ Можно выбрать только обычную школу в качестве основной. Попробуйте снова:",
                reply_markup=InlineKeyboardMarkup(
                    inline_keyboard=[
                        [InlineKeyboardButton(text="🔙 Назад", callback_data=f"edit_field:back:{BOT_SESSION_ID}")]
                    ]
                )
            )
            await state.update_data(last_bot_message_id=sent.message_id)
            return

        await state.update_data(
            main_school_code=code,
            main_school_name=school_data["name"]
        )

        current_school_code = data.get("school_code")
        if current_school_code and current_school_code != code:
            await state.update_data(school_code=current_school_code)
        else:
            await state.update_data(school_code=code)

        sent = await message.answer("✅ Основная школа успешно изменена!")
        await state.update_data(last_bot_message_id=sent.message_id)

        await show_profile_summary(message, state)

        await state.set_state(SchoolStates.editing_profile_field)

    else:
        sent = await message.answer(
            "❌ Неверный код школы. Попробуйте снова:",
            reply_markup=InlineKeyboardMarkup(
                inline_keyboard=[
                    [InlineKeyboardButton(text="🔙 Назад", callback_data=f"edit_field:back:{BOT_SESSION_ID}")]
                ]
            )
        )
        await state.update_data(last_bot_message_id=sent.message_id)


@router.message(SchoolStates.editing_class_letter)
async def editing_class_letter_handler(message: Message, state: FSMContext):
    data = await state.get_data()
    last_bot_message_id = data.get("last_bot_message_id")
    last_sticker_message_id = data.get("last_sticker_message_id")

    await delete_messages(message.bot, message.chat.id,
                          [message.message_id, last_bot_message_id, last_sticker_message_id])

    letter = message.text.strip().lower()

    if re.fullmatch(r"[А-Яа-я]", letter) and letter.lower() not in ('ъ', 'ь'):
        await state.update_data(class_letter=letter.upper())

        sent = await message.answer("✅ Буква класса успешно изменена!")
        await state.update_data(last_bot_message_id=sent.message_id)

        await show_profile_summary(message, state)
        await state.set_state(SchoolStates.editing_profile_field)
    else:
        sent = await message.answer("❌ Пожалуйста, введите одну букву (кроме ъ и ь).")
        await state.update_data(last_bot_message_id=sent.message_id, last_sticker_message_id=None)


@router.callback_query(SchoolStates.editing_specialization, F.data.startswith("edit_specialization:"))
async def editing_specialization_handler(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    specialization_code = callback.data.split(":", 1)[1]

    data = await state.get_data()
    school_code = data.get("main_school_code")  # Используем main_school_code для определения специализаций
    if school_code is None:
        await callback.message.answer("Ошибка: код школы не найден.")
        return
    school_data = SCHOOL_CODES[school_code]
    specializations = school_data["specializations"]
    specialization = specializations.get(specialization_code, "не указано")

    await state.update_data(specialization=specialization)

    sent_msg = await callback.message.answer("✅ Направление успешно изменено!")
    await state.update_data(last_bot_message_id=sent_msg.message_id)

    await show_profile_summary(callback, state)
    await state.set_state(SchoolStates.editing_profile_field)


@router.callback_query(SchoolStates.editing_course, F.data.startswith("edit_course:"))
async def editing_course_handler(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    course = callback.data.split(":", 1)[1]
    await state.update_data(course=course)

    sent_msg = await callback.message.answer("✅ Курс успешно изменён!")
    await state.update_data(last_bot_message_id=sent_msg.message_id)

    await show_profile_summary(callback, state)
    await state.set_state(SchoolStates.editing_profile_field)


@router.callback_query()
async def handle_expired_or_unknown_callback(callback: CallbackQuery):
    if ":" in callback.data:
        try:
            _, _, session_id = callback.data.split(":")
            if session_id != BOT_SESSION_ID:
                await callback.answer(
                    "❗ Это устаревшая кнопка. Пожалуйста, отправьте команду /myprofile.",
                    show_alert=True
                )
                return
        except ValueError:
            pass

    try:
        await callback.answer(
            "❗ Это устаревшая кнопка. Пожалуйста, отправьте команду /myprofile.",
            show_alert=True
        )
    except TelegramBadRequest:
        try:
            await callback.message.answer("❗ Кнопка устарела. Отправьте команду /myprofile.")
        except Exception as e:
            print("[ERROR] Не удалось отправить сообщение:", e)


async def main():
    bot = Bot(
        token=BOT_TOKEN,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML)
    )
    dp = Dispatcher()
    dp.include_router(router)

    print("Бот запущен...")
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())

