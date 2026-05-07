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
    password: Mapped[str]
    class_name: Mapped[PlayerClass]
    level: Mapped[int] = mapped_column(default=1)
    exp: Mapped[int] = mapped_column(default=0)

    x: Mapped[int] = mapped_column(default=50000)
    y: Mapped[int] = mapped_column(default=50000)

    base_str: Mapped[int] = mapped_column(default=5)
    base_spd: Mapped[int] = mapped_column(default=5)
    base_vit: Mapped[int] = mapped_column(default=5)
    base_int: Mapped[int] = mapped_column(default=5)
    base_cha: Mapped[int] = mapped_column(default=5)
    base_lck: Mapped[int] = mapped_column(default=5)

class Item(Base):
    __tablename__ = "items"
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str]
    item_type: Mapped[str]   # weapon, armor, consumable, material
    slot: Mapped[str]        # weapon, head, chest, legs, feet, none
    value: Mapped[int]
    stat_bonuses: Mapped[str] = mapped_column(default="{}")

class Inventory(Base):
    __tablename__ = "inventory"
    id: Mapped[int] = mapped_column(primary_key=True)
    player_id: Mapped[int] = mapped_column(index=True)
    item_id: Mapped[int]
    quantity: Mapped[int] = mapped_column(default=1)

class Equipment(Base):
    __tablename__ = "equipment"
    id: Mapped[int] = mapped_column(primary_key=True)
    player_id: Mapped[int] = mapped_column(unique=True)
    weapon: Mapped[int] = mapped_column(nullable=True)
    head: Mapped[int] = mapped_column(nullable=True)
    chest: Mapped[int] = mapped_column(nullable=True)
    legs: Mapped[int] = mapped_column(nullable=True)
    feet: Mapped[int] = mapped_column(nullable=True)

# Движок и сессия
engine = create_async_engine("sqlite+aiosqlite:///mmo.db", echo=True)
AsyncSessionLocal = async_sessionmaker(engine, expire_on_commit=False)

async def init_db():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)