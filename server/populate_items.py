import asyncio
from database import AsyncSessionLocal, Item

async def add_items():
    async with AsyncSessionLocal() as session:
        items = [
            Item(name="Деревянный меч", item_type="weapon", slot="weapon", value=10, stat_bonuses='{"str": 2}'),
            Item(name="Кожаный шлем", item_type="armor", slot="head", value=5, stat_bonuses='{"vit": 1}'),
            Item(name="Кожаный доспех", item_type="armor", slot="chest", value=8, stat_bonuses='{"vit": 2}'),
            Item(name="Зелье здоровья", item_type="consumable", slot="none", value=5, stat_bonuses='{}'),
        ]
        for item in items:
            session.add(item)
        await session.commit()
        print("Предметы добавлены")

if __name__ == "__main__":
    asyncio.run(add_items())