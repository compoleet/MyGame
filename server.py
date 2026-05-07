import asyncio
import websockets
import json
import random
from sqlalchemy import select
from game_engine import create_stats_by_class
from database import AsyncSessionLocal, Player, PlayerClass

players = {}

# ------------------------------------------------------------
# Функции работы с БД
# ------------------------------------------------------------
async def authenticate(username: str, password: str):
    async with AsyncSessionLocal() as session:
        result = await session.execute(select(Player).where(Player.username == username))
        player = result.scalar_one_or_none()
        if player and player.password == password:
            return player.id
    return None

async def create_player_in_db(username: str, password: str, class_name: str, stats_allocation: dict):
    async with AsyncSessionLocal() as session:
        result = await session.execute(select(Player).where(Player.username == username))
        if result.scalar_one_or_none():
            return None
        class_enum = getattr(PlayerClass, class_name.upper(), None)
        if not class_enum:
            return None
        new_player = Player(
            username=username,
            password=password,
            class_name=class_enum,
            base_str=stats_allocation.get('str', 5),
            base_spd=stats_allocation.get('spd', 5),
            base_vit=stats_allocation.get('vit', 5),
            base_int=stats_allocation.get('int', 5),
            base_cha=stats_allocation.get('cha', 5),
            base_lck=stats_allocation.get('lck', 5),
            x=500, y=500,
            level=1,
            exp=0
        )
        session.add(new_player)
        await session.commit()
        return new_player.id

async def load_player_from_db(player_id: int):
    async with AsyncSessionLocal() as session:
        player = await session.get(Player, player_id)
        if player:
            stats = create_stats_by_class(player.class_name.value)
            stats.base_stats["str"] = player.base_str
            stats.base_stats["spd"] = player.base_spd
            stats.base_stats["vit"] = player.base_vit
            stats.base_stats["int"] = player.base_int
            stats.base_stats["cha"] = player.base_cha
            stats.base_stats["lck"] = player.base_lck
            stats.current_hp = stats.calculate_health()
            return {
                "player_id": player.id,
                "username": player.username,
                "class": player.class_name.value,
                "level": player.level,
                "exp": player.exp,
                "stats": stats,
                "x": player.x,
                "y": player.y,
            }
    return None

async def save_player_to_db(player_id: int, player_data: dict):
    async with AsyncSessionLocal() as session:
        player = await session.get(Player, player_id)
        if player:
            player.level = player_data["level"]
            player.exp = player_data["exp"]
            player.x = player_data["x"]
            player.y = player_data["y"]
            stats = player_data["stats"]
            player.base_str = stats.base_stats["str"]
            player.base_spd = stats.base_stats["spd"]
            player.base_vit = stats.base_stats["vit"]
            player.base_int = stats.base_stats["int"]
            player.base_cha = stats.base_stats["cha"]
            player.base_lck = stats.base_stats["lck"]
            await session.commit()

# ------------------------------------------------------------
# Игровая логика
# ------------------------------------------------------------
def set_player_position(player_id, x, y):
    players[player_id]["x"] = x
    players[player_id]["y"] = y

def calculate_damage(attacker_stats, defender_stats, weapon_damage=30):
    base_damage = attacker_stats.calculate_physical_damage(weapon_damage)
    final_damage = attacker_stats.calculate_damage_after_armor(base_damage, defender_stats.get_total_stat("vit"))
    if random.random() < attacker_stats.calculate_critical_chance():
        final_damage = int(final_damage * 1.5)
        print("Крит!")
    return max(1, final_damage)

# ------------------------------------------------------------
# Спавн и деспавн
# ------------------------------------------------------------
async def send_existing_players(websocket, current_id):
    for pid, pdata in players.items():
        if pid == current_id:
            continue
        msg = {
            "type": "spawn",
            "player_id": pid,
            "username": pdata["username"],
            "x": pdata["x"],
            "y": pdata["y"],
            "class": pdata["class"]
        }
        await websocket.send(json.dumps(msg))

async def notify_spawn(new_id, new_data):
    msg = {
        "type": "spawn",
        "player_id": new_id,
        "username": new_data["username"],
        "x": new_data["x"],
        "y": new_data["y"],
        "class": new_data["class"]
    }
    for pid, pdata in players.items():
        if pid != new_id:
            await pdata["websocket"].send(json.dumps(msg))

async def notify_despawn(player_id):
    msg = {"type": "despawn", "player_id": player_id}
    for pid, pdata in players.items():
        if pid != player_id:
            await pdata["websocket"].send(json.dumps(msg))

# ------------------------------------------------------------
# Обработчики
# ------------------------------------------------------------
async def handle_auth(websocket, data, player_id):
    player_data = await load_player_from_db(player_id)
    if not player_data:
        await websocket.send(json.dumps({"type": "error", "message": "Failed to load player data"}))
        return

    players[player_id] = {
        "websocket": websocket,
        "stats": player_data["stats"],
        "x": player_data["x"],
        "y": player_data["y"],
        "level": player_data["level"],
        "exp": player_data["exp"],
        "username": player_data["username"],
        "class": player_data["class"]
    }

    init_data = {
        "player_id": player_data["player_id"],
        "username": player_data["username"],
        "class": player_data["class"],
        "level": player_data["level"],
        "exp": player_data["exp"],
        "x": player_data["x"],
        "y": player_data["y"],
        "hp": player_data["stats"].current_hp,
        "max_hp": player_data["stats"].calculate_health(),
        "stats": {
            "str": player_data["stats"].get_total_stat("str"),
            "spd": player_data["stats"].get_total_stat("spd"),
            "vit": player_data["stats"].get_total_stat("vit"),
            "int": player_data["stats"].get_total_stat("int"),
            "cha": player_data["stats"].get_total_stat("cha"),
            "lck": player_data["stats"].get_total_stat("lck"),
        }
    }
    await websocket.send(json.dumps({"type": "init", "data": init_data}))

    await send_existing_players(websocket, player_id)
    await notify_spawn(player_id, {
        "player_id": player_id,
        "username": player_data["username"],
        "x": player_data["x"],
        "y": player_data["y"],
        "class": player_data["class"]
    })

async def handle_move(player_id, data):
    new_x = data.get("x")
    new_y = data.get("y")
    set_player_position(player_id, new_x, new_y)
    for pid, pdata in players.items():
        if pid != player_id:
            await pdata["websocket"].send(json.dumps({
                "type": "move",
                "player_id": player_id,
                "x": new_x,
                "y": new_y
            }))

async def handle_attack(attacker_id, data):
    target_id = data.get("target_id")
    if target_id not in players:
        return
    attacker_stats = players[attacker_id]["stats"]
    defender_stats = players[target_id]["stats"]
    if not hasattr(defender_stats, "current_hp"):
        defender_stats.current_hp = defender_stats.calculate_health()
    damage = calculate_damage(attacker_stats, defender_stats)
    defender_stats.current_hp -= damage

    await players[attacker_id]["websocket"].send(json.dumps({
        "type": "attack_result",
        "target_id": target_id,
        "damage": damage,
        "target_hp": defender_stats.current_hp
    }))
    await players[target_id]["websocket"].send(json.dumps({
        "type": "attacked",
        "attacker_id": attacker_id,
        "damage": damage,
        "your_hp": defender_stats.current_hp
    }))

    if defender_stats.current_hp <= 0:
        # TODO: смерть
        pass

# ------------------------------------------------------------
# Диспетчер сообщений
# ------------------------------------------------------------
async def handle_player_input(websocket):
    player_id = None
    try:
        async for message in websocket:
            data = json.loads(message)
            if data["type"] == "auth":
                pid = await authenticate(data["username"], data["password"])
                if pid:
                    player_id = pid
                    await handle_auth(websocket, data, player_id)
                else:
                    await websocket.send(json.dumps({"type": "error", "message": "Auth failed"}))
            elif data["type"] == "register":
                username = data.get("username")
                password = data.get("password")
                class_name = data.get("class", "warrior")
                if class_name.lower() == "warrior":
                    allocation = {"str": 5+25, "spd": 5, "vit": 5+20, "int": 5, "cha": 5, "lck": 5}
                elif class_name.lower() == "mage":
                    allocation = {"str": 5, "spd": 5, "vit": 5, "int": 5+35, "cha": 5, "lck": 5+10}
                else:
                    allocation = {"str": 5+25, "spd": 5, "vit": 5+20, "int": 5, "cha": 5, "lck": 5}
                new_id = await create_player_in_db(username, password, class_name, allocation)
                if new_id:
                    await websocket.send(json.dumps({"type": "registered", "success": True, "player_id": new_id}))
                else:
                    await websocket.send(json.dumps({"type": "registered", "success": False, "message": "Username exists or invalid class"}))
            elif player_id is None:
                await websocket.send(json.dumps({"type": "error", "message": "Not authenticated"}))
            else:
                if data["type"] == "move":
                    await handle_move(player_id, data)
                elif data["type"] == "attack":
                    await handle_attack(player_id, data)
                else:
                    await websocket.send(json.dumps({"type": "error", "message": "Unknown command"}))
    except websockets.exceptions.ConnectionClosed:
        print(f"Player {player_id} disconnected")
        if player_id in players:
            data_to_save = {
                "level": players[player_id]["level"],
                "exp": players[player_id]["exp"],
                "x": players[player_id]["x"],
                "y": players[player_id]["y"],
                "stats": players[player_id]["stats"],
            }
            await save_player_to_db(player_id, data_to_save)
            await notify_despawn(player_id)
            del players[player_id]

# ------------------------------------------------------------
# Запуск
# ------------------------------------------------------------
async def main():
    async with websockets.serve(handle_player_input, "localhost", 8765):
        print("Сервер запущен на ws://localhost:8765")
        await asyncio.Future()

if __name__ == "__main__":
    asyncio.run(main())