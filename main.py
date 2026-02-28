import asyncio
import logging
import os
import random

from aiogram import Bot, Dispatcher, F, types
from aiogram.filters import Command, CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.utils.keyboard import ReplyKeyboardBuilder
from dotenv import load_dotenv
from sqlalchemy import delete, select

from database import (
    UserWord, Word, add_common_words, async_session,
    get_or_create_user, init_db
)

load_dotenv()


logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

try:
    bot = Bot(token=os.getenv("BOT_TOKEN"))
    dp = Dispatcher()
except Exception as e:
    logger.critical(f"Ошибка инициализации бота: {e}")


class Form(StatesGroup):
    waiting_for_eng_word = State()
    waiting_for_rus_word = State()
    waiting_for_delete_word = State()
    quiz = State()


def get_main_keyboard(target_word: str = None, others: list = None):
    builder = ReplyKeyboardBuilder()

    if target_word and others:
        options =[target_word] + [w.target_word for w in others]
        random.shuffle(options)
        for word in options:
            builder.button(text=word)

    builder.button(text="Дальше ⏭")
    builder.button(text="Добавить слово ➕")
    builder.button(text="Удалить слово 🗑")
    builder.adjust(2)
    return builder.as_markup(resize_keyboard=True)


@dp.message(CommandStart())
async def command_start(message: types.Message):
    user = await get_or_create_user(message.from_user.id)
    if not user:
        await message.answer("Произошла ошибка при доступе к базе данных. Попробуйте позже.")
        return

    await message.answer(
        f"Привет, {message.from_user.first_name}! 👋\n"
        f"Давай учить английский. Нажми 'Дальше', чтобы начать.",
        reply_markup=get_main_keyboard(),
    )


@dp.message(F.text == "Дальше ⏭")
async def next_card(message: types.Message, state: FSMContext):
    user = await get_or_create_user(message.from_user.id)
    if not user:
        await message.answer("Сервис временно недоступен.")
        return

    try:
        async with async_session() as session:
            result = await session.execute(
                select(Word).join(UserWord).where(UserWord.user_id == user.id)
            )
            user_words = result.scalars().all()

            if not user_words:
                await message.answer("Слова закончились или не добавлены!")
                return

            target = random.choice(user_words)
            others = random.sample(
                [w for w in user_words if w.id != target.id],
                k=min(3, len(user_words) - 1),
            )

            await state.update_data(target_word=target.target_word, translate=target.translate_word)
            await state.set_state(Form.quiz)

            await message.answer(
                f"Как переводится: 🇷🇺 <b>{target.translate_word}</b>?",
                reply_markup=get_main_keyboard(target.target_word, others),
                parse_mode="HTML",
            )
    except Exception as e:
        logger.error(f"Ошибка в next_card: {e}")
        await message.answer("Произошла ошибка при загрузке словаря.")


@dp.message(F.text == "Добавить слово ➕")
async def add_word_start(message: types.Message, state: FSMContext):
    await message.answer("Введи слово на английском:", reply_markup=types.ReplyKeyboardRemove())
    await state.set_state(Form.waiting_for_eng_word)


@dp.message(Form.waiting_for_eng_word)
async def add_word_eng(message: types.Message, state: FSMContext):
    await state.update_data(new_eng=message.text)
    await message.answer("Теперь введи перевод на русском:")
    await state.set_state(Form.waiting_for_rus_word)


@dp.message(Form.waiting_for_rus_word)
async def add_word_rus(message: types.Message, state: FSMContext):
    data = await state.get_data()
    eng_word = data["new_eng"]
    rus_word = message.text
    user = await get_or_create_user(message.from_user.id)

    try:
        async with async_session() as session:
            res = await session.execute(select(Word).where(Word.target_word == eng_word))
            word = res.scalar_one_or_none()

            if not word:
                word = Word(target_word=eng_word, translate_word=rus_word)
                session.add(word)
                await session.commit()

            link_res = await session.execute(
                select(UserWord).where(UserWord.user_id == user.id, UserWord.word_id == word.id)
            )
            if not link_res.scalar_one_or_none():
                session.add(UserWord(user_id=user.id, word_id=word.id))
                await session.commit()
                await message.answer(f"Слово '{eng_word}' добавлено!", reply_markup=get_main_keyboard())
            else:
                await message.answer("Это слово уже есть у тебя.", reply_markup=get_main_keyboard())
    except Exception as e:
        logger.error(f"Ошибка при добавлении слова: {e}")
        await message.answer("Ошибка при сохранении слова. Попробуйте позже.", reply_markup=get_main_keyboard())

    await state.clear()



@dp.message(F.text == "Удалить слово 🗑")
async def delete_word_start(message: types.Message, state: FSMContext):
    await message.answer("Введите слово на английском, которое хотите удалить:", reply_markup=types.ReplyKeyboardRemove())
    await state.set_state(Form.waiting_for_delete_word)


@dp.message(Form.waiting_for_delete_word)
async def delete_word_process(message: types.Message, state: FSMContext):
    target_to_delete = message.text.strip()
    user = await get_or_create_user(message.from_user.id)

    try:
        async with async_session() as session:
            word_res = await session.execute(select(Word).where(Word.target_word == target_to_delete))
            word = word_res.scalar_one_or_none()

            if word:
                link_res = await session.execute(
                    select(UserWord).where(UserWord.user_id == user.id, UserWord.word_id == word.id)
                )
                if link_res.scalar_one_or_none():
                    await session.execute(
                        delete(UserWord).where(UserWord.user_id == user.id, UserWord.word_id == word.id)
                    )
                    await session.commit()
                    await message.answer(f"Слово '{target_to_delete}' успешно удалено из вашего списка.", reply_markup=get_main_keyboard())
                else:
                    await message.answer(f"Слова '{target_to_delete}' нет в вашем списке.", reply_markup=get_main_keyboard())
            else:
                await message.answer(f"Слово '{target_to_delete}' не найдено в базе.", reply_markup=get_main_keyboard())
    except Exception as e:
        logger.error(f"Ошибка при удалении слова: {e}")
        await message.answer("Произошла ошибка при удалении. Попробуйте позже.", reply_markup=get_main_keyboard())
    
    await state.clear()

    await next_card(message, state)


@dp.message(Form.quiz)
async def check_answer(message: types.Message, state: FSMContext):
    if message.text in["Дальше ⏭", "Добавить слово ➕", "Удалить слово 🗑"]:
        return

    data = await state.get_data()
    correct = data.get("target_word")

    if message.text == correct:
        await message.answer(f"Верно! ✅ {correct}", reply_markup=get_main_keyboard())
        await next_card(message, state)
    else:
        await message.answer("Неверно, попробуй еще раз ❌")


async def main():
    await init_db()
    await add_common_words()
    logger.info("Бот запущен!")
    await dp.start_polling(bot)


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Бот остановлен пользователем")
