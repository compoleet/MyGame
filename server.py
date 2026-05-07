import asyncio
import websockets
import json
import random
from sqlalchemy import select
from game_engine import create_stats_by_class, CharacterStats
from database import AsyncSessionLocal, Player, PlayerClass

players = {}          # player_id -> {websocket, stats, x, y, level, exp, username, class}
mobs = {}             # mob_id -> {id, x, y, type, hp, attack, exp, max_hp}
next_mob_id = 1
RESPAWN_TIME = 10

MOB_TYPES = {
    "slime": {"hp": 50, "attack": 15, "exp": 20, "color": "green"},
    "goblin": {"hp": 80, "attack": 25, "exp": 40, "color": "brown"},
}

# ------------------------------------------------------------
# Функции работы с БД (без изменений)
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
def get_attack_range(class_name: str) -> int:
    ranged = ["mage", "archer", "buffer"]   # дальний бой
    if class_name.lower() in ranged:
        return 150
    else:
        return 30
# ------------------------------------------------------------
# Функции для спавна/деспавна игроков
# ------------------------------------------------------------
async def send_existing_players(websocket, current_id):
    for pid, pdata in players.items():
        if pid == current_id:
            continue
        msg = {"type": "spawn", "player_id": pid, "username": pdata["username"],
               "x": pdata["x"], "y": pdata["y"], "class": pdata["class"]}
        await websocket.send(json.dumps(msg))

async def notify_spawn(new_id, new_data):
    msg = {"type": "spawn", "player_id": new_id, "username": new_data["username"],
           "x": new_data["x"], "y": new_data["y"], "class": new_data["class"]}
    for pid, pdata in players.items():
        if pid != new_id:
            await pdata["websocket"].send(json.dumps(msg))

async def notify_despawn(player_id):
    msg = {"type": "despawn", "player_id": player_id}
    for pid, pdata in players.items():
        if pid != player_id:
            await pdata["websocket"].send(json.dumps(msg))

# ------------------------------------------------------------
# Функции для мобов
# ------------------------------------------------------------
def spawn_mob(x, y, mob_type="slime"):
    global next_mob_id
    mob_id = next_mob_id
    next_mob_id += 1
    mob_info = MOB_TYPES[mob_type]
    mobs[mob_id] = {
        "id": mob_id,
        "x": x,
        "y": y,
        "type": mob_type,
        "hp": mob_info["hp"],
        "max_hp": mob_info["hp"],
        "attack": mob_info["attack"],
        "exp": mob_info["exp"],
    }
    # Оповестить всех игроков
    msg = {"type": "spawn_mob", "mob_id": mob_id, "x": x, "y": y,
           "mob_type": mob_type, "hp": mob_info["hp"], "max_hp": mob_info["hp"]}
    for pid, pdata in players.items():
        asyncio.create_task(pdata["websocket"].send(json.dumps(msg)))
    return mob_id

async def move_mob(mob_id, new_x, new_y):
    if mob_id not in mobs:
        return
    mobs[mob_id]["x"] = new_x
    mobs[mob_id]["y"] = new_y
    msg = {"type": "move_mob", "mob_id": mob_id, "x": new_x, "y": new_y}
    for pid, pdata in players.items():
        await pdata["websocket"].send(json.dumps(msg))

async def despawn_mob(mob_id):
    if mob_id not in mobs:
        return
    del mobs[mob_id]
    msg = {"type": "despawn_mob", "mob_id": mob_id}
    for pid, pdata in players.items():
        await pdata["websocket"].send(json.dumps(msg))

async def mob_attack(mob_id, player_id):
    if mob_id not in mobs or player_id not in players:
        return
    mob = mobs[mob_id]
    damage = random.randint(5, mob["attack"])
    defender = players[player_id]["stats"]
    if not hasattr(defender, "current_hp"):
        defender.current_hp = defender.calculate_health()
    defender.current_hp -= damage
    msg = {"type": "attacked_by_mob", "mob_id": mob_id, "damage": damage, "your_hp": defender.current_hp}
    await players[player_id]["websocket"].send(json.dumps(msg))
    if defender.current_hp <= 0:
        # Игрок умер: респавн (пока просто восстановим HP до полного)
        defender.current_hp = defender.calculate_health()
        await players[player_id]["websocket"].send(json.dumps({"type": "respawn", "hp": defender.current_hp}))

async def mob_ai():
    """Простой ИИ: случайное движение и атака ближайшего игрока."""
    while True:
        await asyncio.sleep(2)
        for mob_id, mob in list(mobs.items()):
            # Движение с вероятностью 0.5
            if random.random() < 0.5:
                dx = random.randint(-2, 2)
                dy = random.randint(-2, 2)
                new_x = max(0, min(1000, mob["x"] + dx))
                new_y = max(0, min(1000, mob["y"] + dy))
                await move_mob(mob_id, new_x, new_y)
            # Поиск ближайшего игрока
            nearest = None
            min_dist = 200
            for pid, pdata in players.items():
                dist = abs(pdata["x"] - mob["x"]) + abs(pdata["y"] - mob["y"])
                if dist < min_dist:
                    min_dist = dist
                    nearest = pid
            if nearest and min_dist < 40:
                await mob_attack(mob_id, nearest)

# ------------------------------------------------------------
# Обработчики команд
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
    # Отправить новому игроку всех существующих мобов
    for mob_id, mob in mobs.items():
        await websocket.send(json.dumps({
            "type": "spawn_mob", "mob_id": mob_id, "x": mob["x"], "y": mob["y"],
            "mob_type": mob["type"], "hp": mob["hp"], "max_hp": mob["max_hp"]
        }))

async def handle_move(player_id, data):
    new_x = data.get("x")
    new_y = data.get("y")
    set_player_position(player_id, new_x, new_y)
    for pid, pdata in players.items():
        if pid != player_id:
            await pdata["websocket"].send(json.dumps({
                "type": "move", "player_id": player_id, "x": new_x, "y": new_y
            }))

async def handle_attack(player_id, data):
    target_id = data.get("target_id")
    if target_id not in players:
        return
    attacker_stats = players[player_id]["stats"]
    defender_stats = players[target_id]["stats"]
    if not hasattr(defender_stats, "current_hp"):
        defender_stats.current_hp = defender_stats.calculate_health()
    damage = calculate_damage(attacker_stats, defender_stats)
    defender_stats.current_hp -= damage
    await players[player_id]["websocket"].send(json.dumps({
        "type": "attack_result", "target_id": target_id, "damage": damage, "target_hp": defender_stats.current_hp
    }))
    await players[target_id]["websocket"].send(json.dumps({
        "type": "attacked", "attacker_id": player_id, "damage": damage, "your_hp": defender_stats.current_hp
    }))
    if defender_stats.current_hp <= 0:
        # Смерть игрока: респавн (сброс позиции и HP)
        defender_stats.current_hp = defender_stats.calculate_health()
        new_x, new_y = 500, 500
        set_player_position(target_id, new_x, new_y)
        await players[target_id]["websocket"].send(json.dumps({"type": "respawn", "x": new_x, "y": new_y, "hp": defender_stats.current_hp}))
        # Оповестить остальных о перемещении
        for pid, pdata in players.items():
            if pid != target_id:
                await pdata["websocket"].send(json.dumps({"type": "move", "player_id": target_id, "x": new_x, "y": new_y}))

async def handle_attack_mob(player_id, data, websocket):
    mob_id = data.get("mob_id")
    if mob_id not in mobs:
        return
    attacker_stats = players[player_id]["stats"]
    mob = mobs[mob_id]
    # Урон мобу (простая формула: сила*2 + рандом)
    damage = int(attacker_stats.get_total_stat("str") * 2 + random.randint(5, 15))
    mob["hp"] -= damage
    await websocket.send(json.dumps({"type": "mob_attacked", "mob_id": mob_id, "damage": damage, "hp": mob["hp"]}))
    if mob["hp"] <= 0:
        # Убийство моба: дать опыт игроку и убрать моба
        players[player_id]["exp"] += mob["exp"]
        # Проверка уровня (упрощённо)
        exp_needed = 100 * players[player_id]["level"]
        if players[player_id]["exp"] >= exp_needed:
            players[player_id]["level"] += 1
            players[player_id]["exp"] -= exp_needed
            await websocket.send(json.dumps({"type": "level_up", "level": players[player_id]["level"]}))
        await despawn_mob(mob_id)
        asyncio.create_task(respawn_mob_after_delay(mob["type"]))
async def respawn_mob_after_delay(mob_type):
    await asyncio.sleep(RESPAWN_TIME)
    # Можно заспавнить в случайной точке, если хотите, чтобы моб появлялся не точно на месте смерти
    new_x = random.randint(100, 900)
    new_y = random.randint(100, 900)
    spawn_mob(new_x, new_y, mob_type)

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
                elif data["type"] == "attack_mob":
                    await handle_attack_mob(player_id, data, websocket)
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
        # Спавним несколько мобов
        spawn_mob(300, 300, "slime")
        spawn_mob(700, 200, "goblin")
        spawn_mob(500, 600, "slime")
        asyncio.create_task(mob_ai())
        await asyncio.Future()

if __name__ == "__main__":
    asyncio.run(main())