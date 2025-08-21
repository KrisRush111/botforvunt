import re
import threading
import os
import http.server
import socketserver
import asyncio
from aiogram import Bot, Dispatcher, F, types
from aiogram.filters import Command
from aiogram.types import KeyboardButton, ReplyKeyboardMarkup
from aiogram.enums import ParseMode
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.context import FSMContext



from config import TOKEN, ADMIN_CHAT_ID

bot = Bot(TOKEN)
dp = Dispatcher()


def keep_alive():
    port = int(os.environ.get("PORT", 8080))
    handler = http.server.SimpleHTTPRequestHandler
    with socketserver.TCPServer(("", port), handler) as httpd:
        print(f"Фейковый сервер запущен на порту {port}")
        httpd.serve_forever()

last_admin_message_id = None



class DeleteAccount(StatesGroup):
    waiting_for_id = State()



@dp.message(Command('start'))
async def start_handler(message: types.Message, state: FSMContext):
    # Сбрасываем состояние на случай, если пользователь был в процессе
    await state.clear()

    sent_sticker = await message.answer_sticker(
        "CAACAgIAAxkBAAEBiFNop0zoiN_bQ48fWgZ3-HiwoAichQACMTQAAugboErSr6fEZiaivDYE"
    )

    kb = ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="Что такое TheVuntgram?")],
            [KeyboardButton(text="Двойной аккаунт"), KeyboardButton(text="Удалить аккаунт")]
        ],
        resize_keyboard=True
    )
    await message.answer(
        f"Привет, *{message.from_user.first_name}*! Ты открыл техподдержку платформы [TheVuntgram](https://t.me/VuntgramBot). "
        "Напиши сюда свой вопрос, и мы ответим на него в ближайшее время! 🙂\n\n"
        "Или воспользуй кнопками ниже, где ты найдете ответы на часто задаваемые вопросы.",
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=kb
    )



@dp.message(F.text == "Что такое TheVuntgram?")
async def handle_faq_info(message: types.Message, state: FSMContext):
    await state.clear()
    await message.answer(
        "О подробностях вы можете ознакомиться на официальном сайте TheVuntgram:\nhttps://thevuntgram.vercel.app")


@dp.message(F.text == "Двойной аккаунт")
async def handle_faq_double(message: types.Message, state: FSMContext):
    await state.clear()
    await message.answer(
        "Нельзя создавать два аккаунта, привязанных к одному пользователю, "
        "так как это нарушает правила и может привести к блокировке."
    )



@dp.message(F.text == "Удалить аккаунт")
async def handle_delete_account(message: types.Message, state: FSMContext):
    cancel_kb = ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text="Отмена")]],
        resize_keyboard=True
    )

    await message.answer(
        "Отправьте свой ID на платформе TheVuntgram",
        reply_markup=cancel_kb
    )
    await state.set_state(DeleteAccount.waiting_for_id)



@dp.message(F.text == "Отмена")
async def handle_cancel(message: types.Message, state: FSMContext):
    current_state = await state.get_state()
    if current_state is None:
        return

    await state.clear()

    # Возвращаем основную клавиатуру
    kb = ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="Что такое TheVuntgram?")],
            [KeyboardButton(text="Двойной аккаунт"), KeyboardButton(text="Удалить аккаунт")]
        ],
        resize_keyboard=True
    )

    await message.answer(
        "Запрос отменен. Вы можете отправить обычное сообщение или выбрать другую опцию.",
        reply_markup=kb
    )



@dp.message(DeleteAccount.waiting_for_id)
async def process_account_id(message: types.Message, state: FSMContext):
    user_input = message.text.strip()


    if not user_input.isdigit():
        sent_sticker = await message.answer_sticker(
            "CAACAgIAAxkBAAEBiFdop1VzvX34UgQya0DHpsLunn07FQACcTsAArVDWUo6XMAuPW2eHTYE"
        )
        await message.answer("❌ Неверный ввод ID. ID должен содержать только цифры.")
        return


    if len(user_input) < 8:
        sent_sticker = await message.answer_sticker(
            "CAACAgIAAxkBAAEBiFdop1VzvX34UgQya0DHpsLunn07FQACcTsAArVDWUo6XMAuPW2eHTYE"
        )
        await message.answer("❌ ID не может быть меньше 8 цифр.")
        return


    await state.clear()


    kb = ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="Что такое TheVuntgram?")],
            [KeyboardButton(text="Двойной аккаунт"), KeyboardButton(text="Удалить аккаунт")]
        ],
        resize_keyboard=True
    )

    await message.answer(
        "✅ Ваш запрос принят, аккаунт будет удален в течение 3 дней.",
        reply_markup=kb
    )


    admin_text = (f"🚨 ЗАПРОС НА УДАЛЕНИЕ АККАУНТА\n\n"
                  f"Пользователь: {message.from_user.full_name}\n"
                  f"ID Telegram: {message.from_user.id}\n"
                  f"ID платформы: {user_input}\n"
                  f"Время: {message.date}")

    await bot.send_message(ADMIN_CHAT_ID, admin_text)



@dp.message(Command("reply"))
async def reply_to_user(message: types.Message, state: FSMContext):
    if message.from_user.id != ADMIN_CHAT_ID:
        return

    args = message.text.split(maxsplit=2)
    if len(args) < 3:
        await message.answer("Формат: /reply <user_id> <текст ответа>")
        return

    user_id = int(args[1])
    reply_text = args[2]

    try:
        await bot.send_message(user_id, f"Ответ поддержки:\n\n{reply_text}")
        await message.answer("✅ Ответ отправлен пользователю")
    except Exception as e:
        await message.answer(f"❌ Не удалось отправить сообщение: {e}")



@dp.message()
async def forward_to_admin(message: types.Message, state: FSMContext):
    global last_admin_message_id


    current_state = await state.get_state()
    if current_state == DeleteAccount.waiting_for_id:

        if message.text != "Отмена":
            await message.answer("Пожалуйста, введите ваш ID или нажмите 'Отмена' для отмены запроса.")
        return

    if message.from_user.id != ADMIN_CHAT_ID:

        text = f"📩 Сообщение от пользователя {message.from_user.full_name} (ID: {message.from_user.id}):\n\n{message.text}"
        sent_message = await bot.send_message(ADMIN_CHAT_ID, text)


        last_admin_message_id = sent_message.message_id


        await message.answer_sticker("CAACAgIAAxkBAAEBiFVop08nN5c00tl1wFqw0L_nSZgG-QACAzYAAgjOMErEAAH7H5AfVxw2BA")
        await message.answer("✅ Ваш запрос отправлен администратору, ожидайте ответа!")
    else:

        text = f"📩 Сообщение от администратора {message.from_user.full_name} (ID: {message.from_user.id}):\n\n{message.text}"
        await bot.send_message(ADMIN_CHAT_ID, text)



@dp.message(Command("reply_admin"))
async def reply_to_admin(message: types.Message):
    if message.from_user.id != ADMIN_CHAT_ID:
        return

    if last_admin_message_id is None:
        await message.answer("❌ Нет сообщения для ответа.")
        return

    reply_text = message.text[len("/reply_admin "):]  # Убираем команду из текста

    try:
        await bot.send_message(ADMIN_CHAT_ID, f"Ответ на ваше сообщение:\n\n{reply_text}")
        await bot.edit_message_text(
            text=f"📩 Ответ на ваше сообщение:\n\n{reply_text}",
            chat_id=ADMIN_CHAT_ID,
            message_id=last_admin_message_id
        )
        await message.answer("✅ Ответ отправлен на ваше сообщение.")
    except Exception as e:
        await message.answer(f"❌ Не удалось отправить ответ: {e}")


async def main():
    print("Бот техподдержки запущен...")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())

