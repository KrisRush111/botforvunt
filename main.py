import asyncio
import logging
import os
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

from aiogram import Bot, Dispatcher, F, types
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import KeyboardButton, ReplyKeyboardMarkup

from config import TOKEN, ADMIN_CHAT_ID

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s",
)
log = logging.getLogger("vunt-support")

ADMIN_CHAT_ID = int(ADMIN_CHAT_ID)

bot = Bot(TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
dp = Dispatcher()

last_admin_message_id: int | None = None


# ---------------------------------------------------------------- keep-alive HTTP


class HealthHandler(BaseHTTPRequestHandler):
    """Отдаёт 200 OK на любой путь — нужно только чтобы Render видел открытый порт."""

    def do_GET(self):
        self.send_response(200)
        self.send_header("Content-Type", "text/plain; charset=utf-8")
        self.end_headers()
        self.wfile.write(b"TheVuntgram support bot is running")

    def do_HEAD(self):
        self.send_response(200)
        self.end_headers()

    def log_message(self, *args):
        pass  # не засоряем логи пингами Render


def run_http_server():
    port = int(os.environ.get("PORT", 5001))
    HTTPServer(("0.0.0.0", port), HealthHandler).serve_forever()


# ---------------------------------------------------------------- states / keyboards


class DeleteAccount(StatesGroup):
    waiting_for_id = State()


def main_kb() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="Что такое TheVuntgram?")],
            [KeyboardButton(text="Двойной аккаунт"), KeyboardButton(text="Удалить аккаунт")],
        ],
        resize_keyboard=True,
    )


def cancel_kb() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text="Отмена")]],
        resize_keyboard=True,
    )


# ---------------------------------------------------------------- commands
# ВАЖНО: все команды и кнопки объявлены ДО catch-all хендлера forward_to_admin,
# иначе catch-all перехватывает их первым (aiogram проверяет хендлеры по порядку).


@dp.message(Command("start"))
async def start_handler(message: types.Message, state: FSMContext):
    await state.clear()

    await message.answer_sticker(
        "CAACAgIAAxkBAAEBiFNop0zoiN_bQ48fWgZ3-HiwoAichQACMTQAAugboErSr6fEZiaivDYE"
    )
    await message.answer(
        f"Привет, <b>{message.from_user.first_name}</b>! Ты открыл техподдержку платформы "
        '<a href="https://t.me/VuntgramBot">TheVuntgram</a>. '
        "Напиши сюда свой вопрос, и мы ответим на него в ближайшее время! 🙂\n\n"
        "Или воспользуйся кнопками ниже, где ты найдёшь ответы на часто задаваемые вопросы.",
        reply_markup=main_kb(),
    )


@dp.message(Command("reply"))
async def reply_to_user(message: types.Message):
    if message.from_user.id != ADMIN_CHAT_ID:
        return

    args = message.text.split(maxsplit=2)
    if len(args) < 3:
        await message.answer("Формат: /reply &lt;user_id&gt; &lt;текст ответа&gt;")
        return

    try:
        user_id = int(args[1])
    except ValueError:
        await message.answer("❌ user_id должен быть числом.")
        return

    try:
        await bot.send_message(user_id, f"Ответ поддержки:\n\n{args[2]}")
        await message.answer("✅ Ответ отправлен пользователю")
    except Exception as e:
        await message.answer(f"❌ Не удалось отправить сообщение: {e}")


@dp.message(Command("reply_admin"))
async def reply_to_admin(message: types.Message):
    if message.from_user.id != ADMIN_CHAT_ID:
        return

    if last_admin_message_id is None:
        await message.answer("❌ Нет сообщения для ответа.")
        return

    args = message.text.split(maxsplit=1)
    if len(args) < 2:
        await message.answer("Формат: /reply_admin &lt;текст&gt;")
        return

    try:
        await bot.edit_message_text(
            text=f"📩 Ответ на ваше сообщение:\n\n{args[1]}",
            chat_id=ADMIN_CHAT_ID,
            message_id=last_admin_message_id,
        )
        await message.answer("✅ Ответ отправлен на ваше сообщение.")
    except Exception as e:
        await message.answer(f"❌ Не удалось отправить ответ: {e}")


# ---------------------------------------------------------------- FAQ buttons


@dp.message(F.text == "Что такое TheVuntgram?")
async def handle_faq_info(message: types.Message, state: FSMContext):
    await state.clear()
    await message.answer(
        "О подробностях вы можете ознакомиться на официальном сайте TheVuntgram:\n"
        "https://thevuntgram.vercel.app",
        reply_markup=main_kb(),
    )


@dp.message(F.text == "Двойной аккаунт")
async def handle_faq_double(message: types.Message, state: FSMContext):
    await state.clear()
    await message.answer(
        "Нельзя создавать два аккаунта, привязанных к одному пользователю, "
        "так как это нарушает правила и может привести к блокировке.",
        reply_markup=main_kb(),
    )


# ---------------------------------------------------------------- удаление аккаунта


@dp.message(F.text == "Удалить аккаунт")
async def handle_delete_account(message: types.Message, state: FSMContext):
    await message.answer(
        "Отправьте свой ID на платформе TheVuntgram",
        reply_markup=cancel_kb(),
    )
    await state.set_state(DeleteAccount.waiting_for_id)


@dp.message(F.text == "Отмена")
async def handle_cancel(message: types.Message, state: FSMContext):
    if await state.get_state() is None:
        return

    await state.clear()
    await message.answer(
        "Запрос отменён. Вы можете отправить обычное сообщение или выбрать другую опцию.",
        reply_markup=main_kb(),
    )


@dp.message(DeleteAccount.waiting_for_id)
async def process_account_id(message: types.Message, state: FSMContext):
    bad_sticker = "CAACAgIAAxkBAAEBiFdop1VzvX34UgQya0DHpsLunn07FQACcTsAArVDWUo6XMAuPW2eHTYE"

    if not message.text:
        await message.answer("Пожалуйста, отправьте ID текстом или нажмите «Отмена».")
        return

    user_input = message.text.strip()

    if not user_input.isdigit():
        await message.answer_sticker(bad_sticker)
        await message.answer("❌ Неверный ввод ID. ID должен содержать только цифры.")
        return

    if len(user_input) < 8:
        await message.answer_sticker(bad_sticker)
        await message.answer("❌ ID не может быть меньше 8 цифр.")
        return

    await state.clear()
    await message.answer(
        "✅ Ваш запрос принят, аккаунт будет удалён в течение 3 дней.",
        reply_markup=main_kb(),
    )

    await bot.send_message(
        ADMIN_CHAT_ID,
        "🚨 ЗАПРОС НА УДАЛЕНИЕ АККАУНТА\n\n"
        f"Пользователь: {message.from_user.full_name}\n"
        f"ID Telegram: {message.from_user.id}\n"
        f"ID платформы: {user_input}\n"
        f"Время: {message.date}",
    )


# ---------------------------------------------------------------- catch-all (последний!)


@dp.message()
async def forward_to_admin(message: types.Message):
    global last_admin_message_id

    if message.from_user.id == ADMIN_CHAT_ID:
        await message.answer(
            "Чтобы ответить пользователю: /reply &lt;user_id&gt; &lt;текст&gt;"
        )
        return

    body = message.text or message.caption or "[нетекстовое сообщение]"
    sent = await bot.send_message(
        ADMIN_CHAT_ID,
        f"📩 Сообщение от пользователя {message.from_user.full_name} "
        f"(ID: {message.from_user.id}):\n\n{body}",
    )
    last_admin_message_id = sent.message_id

    await message.answer_sticker(
        "CAACAgIAAxkBAAEBiFVop08nN5c00tl1wFqw0L_nSZgG-QACAzYAAgjOMErEAAH7H5AfVxw2BA"
    )
    await message.answer("✅ Ваш запрос отправлен администратору, ожидайте ответа!")


# ---------------------------------------------------------------- entrypoint


async def main():
    # Снимаем webhook — иначе Telegram отдаёт
    # "Conflict: can't use getUpdates method while webhook is active"
    await bot.delete_webhook(drop_pending_updates=True)
    log.info("Webhook удалён, стартуем polling...")

    try:
        await dp.start_polling(bot)
    finally:
        await bot.session.close()


if __name__ == "__main__":
    threading.Thread(target=run_http_server, daemon=True).start()
    asyncio.run(main())
