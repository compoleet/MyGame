# setup_db.py
import asyncio
from database import init_db, AsyncSessionLocal, Player, PlayerClass
from sqlalchemy import select

async def create_tables():
    await init_db()
    print("Таблицы созданы (или уже существуют).")

async def add_test_player():
    async with AsyncSessionLocal() as session:
        # Проверим, нет ли уже пользователя test
        result = await session.execute(select(Player).where(Player.username == "test"))
        existing = result.scalar_one_or_none()
        if existing:
            print("Тестовый игрок уже существует.")
            return
        
        # Создаём нового игрока (например, Воина)
        new_player = Player(
            username="test",
            password="123",  # в реальности надо хешировать, но для теста ок
            class_name=PlayerClass.WARRIOR,
            level=1,
            exp=0,
            x=500,
            y=500,
            base_str=5+25,   # 5 база + распределённые очки (согласно твоему примеру для Воина: STR 25)
            base_spd=5,
            base_vit=5+20,   # VIT 20
            base_int=5,
            base_cha=5,
            base_lck=5,
        )
        session.add(new_player)
        await session.commit()
        print(f"Создан тестовый игрок: {new_player.username} (id={new_player.id})")

async def main():
    await create_tables()
    await add_test_player()

if __name__ == "__main__":
    asyncio.run(main())