from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy.orm import declarative_base, Mapped, mapped_column
import enum

Base = declarative_base()

class PlayerClass(enum.Enum):
    SHIELD = "shield"
    SWORD = "sword"
    WARRIOR = "warrior"
    MAGE = "mage"
    BUFFER = "buffer"
    ARCHER = "archer"
    TAMER = "tamer"
    ASSASSIN = "assassin"
    CRAFTER = "crafter"

class Player(Base):
    __tablename__ = "players"

    id: Mapped[int] = mapped_column(primary_key=True)
    username: Mapped[str] = mapped_column(unique=True)
    password: Mapped[str]  # храни хеш!
    class_name: Mapped[PlayerClass]
    level: Mapped[int] = mapped_column(default=1)
    exp: Mapped[int] = mapped_column(default=0)
    
    # Позиция в мире
    x: Mapped[int] = mapped_column(default=500)
    y: Mapped[int] = mapped_column(default=500)
    
    # Статы (бонусные очки, которые игрок распределил)
    base_str: Mapped[int] = mapped_column(default=5)
    base_spd: Mapped[int] = mapped_column(default=5)
    base_vit: Mapped[int] = mapped_column(default=5)
    base_int: Mapped[int] = mapped_column(default=5)
    base_cha: Mapped[int] = mapped_column(default=5)
    base_lck: Mapped[int] = mapped_column(default=5)

# Создаём движок и фабрику сессий
engine = create_async_engine("sqlite+aiosqlite:///mmo.db", echo=True)
AsyncSessionLocal = async_sessionmaker(engine, expire_on_commit=False)

async def init_db():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)