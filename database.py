import asyncio
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship
from sqlalchemy import ForeignKey, String, BigInteger, select
import os
from dotenv import load_dotenv

load_dotenv()

DB_URL = f"postgresql+asyncpg://{os.getenv('DB_USER')}:{os.getenv('DB_PASS')}@{os.getenv('DB_HOST')}:{os.getenv('DB_PORT')}/{os.getenv('DB_NAME')}"

engine = create_async_engine(DB_URL, echo=True)
async_session = async_sessionmaker(engine, expire_on_commit=False)

class Base(DeclarativeBase):
    pass

class User(Base):
    __tablename__ = 'users'
    
    id: Mapped[int] = mapped_column(primary_key=True)
    telegram_id: Mapped[int] = mapped_column(BigInteger, unique=True)

class Word(Base):
    __tablename__ = 'words'
    
    id: Mapped[int] = mapped_column(primary_key=True)
    target_word: Mapped[str] = mapped_column(String, unique=True)
    translate_word: Mapped[str] = mapped_column(String)

class UserWord(Base):
    __tablename__ = 'user_words'
    
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey('users.id'))
    word_id: Mapped[int] = mapped_column(ForeignKey('words.id'))

async def init_db():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

async def add_common_words():
    """Добавляет базовый набор слов при старте."""
    common = [
        ('Green', 'Зеленый'), ('Red', 'Красный'), ('Blue', 'Синий'),
        ('White', 'Белый'), ('Black', 'Черный'), ('Cat', 'Кошка'),
        ('Dog', 'Собака'), ('Hello', 'Привет'), ('House', 'Дом'),
        ('Car', 'Машина')
    ]
    async with async_session() as session:
        for eng, rus in common:
            result = await session.execute(select(Word).where(Word.target_word == eng))
            if not result.scalar_one_or_none():
                session.add(Word(target_word=eng, translate_word=rus))
        await session.commit()

async def get_or_create_user(tg_id: int):
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
