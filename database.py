import logging
import os

from dotenv import load_dotenv
from sqlalchemy import BigInteger, ForeignKey, String, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

load_dotenv()

DB_URL = (
    f"postgresql+asyncpg://{os.getenv('DB_USER')}:{os.getenv('DB_PASS')}"
    f"@{os.getenv('DB_HOST')}:{os.getenv('DB_PORT')}/{os.getenv('DB_NAME')}"
)


try:
    engine = create_async_engine(DB_URL, echo=False)
    async_session = async_sessionmaker(engine, expire_on_commit=False)
except Exception as e:
    logger.error(f"Ошибка инициализации подключения к БД: {e}")


class Base(DeclarativeBase):
    pass


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
    telegram_id: Mapped[int] = mapped_column(BigInteger, unique=True)


class Word(Base):
    __tablename__ = "words"

    id: Mapped[int] = mapped_column(primary_key=True)
    target_word: Mapped[str] = mapped_column(String, unique=True)
    translate_word: Mapped[str] = mapped_column(String)


class UserWord(Base):
    __tablename__ = "user_words"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    word_id: Mapped[int] = mapped_column(ForeignKey("words.id"))


async def init_db():
    try:
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
    except Exception as e:
        logger.error(f"Ошибка при создании таблиц: {e}")


async def add_common_words():
    common =[
        ("Green", "Зеленый"), ("Red", "Красный"), ("Blue", "Синий"),
        ("White", "Белый"), ("Black", "Черный"), ("Cat", "Кошка"),
        ("Dog", "Собака"), ("Hello", "Привет"), ("House", "Дом"),
        ("Car", "Машина"),
    ]
    try:
        async with async_session() as session:
            for eng, rus in common:
                result = await session.execute(select(Word).where(Word.target_word == eng))
                if not result.scalar_one_or_none():
                    session.add(Word(target_word=eng, translate_word=rus))
            await session.commit()
    except Exception as e:
        logger.error(f"Ошибка при добавлении базовых слов: {e}")


async def get_or_create_user(tg_id: int):
    try:
        async with async_session() as session:
            result = await session.execute(select(User).where(User.telegram_id == tg_id))
            user = result.scalar_one_or_none()

            if not user:
                user = User(telegram_id=tg_id)
                session.add(user)
                await session.commit()

                all_words = await session.execute(select(Word))
                for w in all_words.scalars():
                    session.add(UserWord(user_id=user.id, word_id=w.id))
                await session.commit()
            return user
    except Exception as e:
        logger.error(f"Ошибка в get_or_create_user: {e}")
        return None
