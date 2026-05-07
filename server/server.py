import asyncio
import websockets
import json
import random
import math
from sqlalchemy import select
from game_engine import create_stats_by_class
from database import AsyncSessionLocal, Player, PlayerClass

players = {}
mobs = {}
next_mob_id = 1

MOB_TYPES = {
    "slime": {"hp": 50, "attack": 15, "exp": 20, "level": 3},
    "goblin": {"hp": 80, "attack": 25, "exp": 40, "level": 8},
}
RESPAWN_TIME = 7

# Параметры мира
WORLD_SIZE = 100000
CITY_CENTER = WORLD_SIZE // 2   # 50000
CITY_RADIUS = 500               # город 1000x1000 (квадрат)
SAFE_ZONE_RADIUS = CITY_RADIUS

# Зоны спавна мобов по уровням (расстояние от центра города)
LEVEL_ZONES = {
    1: (CITY_RADIUS + 50, CITY_RADIUS + 250),   # уровни 1-5
    2: (CITY_RADIUS + 50, CITY_RADIUS + 250),
    3: (CITY_RADIUS + 50, CITY_RADIUS + 250),
    4: (CITY_RADIUS + 50, CITY_RADIUS + 250),
    5: (CITY_RADIUS + 50, CITY_RADIUS + 250),
    6: (CITY_RADIUS + 300, CITY_RADIUS + 600),  # уровни 6-10
    7: (CITY_RADIUS + 300, CITY_RADIUS + 600),
    8: (CITY_RADIUS + 300, CITY_RADIUS + 600),
    9: (CITY_RADIUS + 300, CITY_RADIUS + 600),
    10: (CITY_RADIUS + 300, CITY_RADIUS + 600),
}

def is_in_safe_zone(x, y):
    return abs(x - CITY_CENTER) <= CITY_RADIUS and abs(y - CITY_CENTER) <= CITY_RADIUS

def get_mob_spawn_zone(mob_level):
    for lvl in range(mob_level, 0, -1):
        if lvl in LEVEL_ZONES:
            return LEVEL_ZONES[lvl]
    return (CITY_RADIUS + 50, CITY_RADIUS + 250)

def get_random_point_in_zone(min_dist, max_dist):
    angle = random.uniform(0, 2*math.pi)
    dist = random.randint(min_dist, max_dist)
    x = CITY_CENTER + int(dist * math.cos(angle))
    y = CITY_CENTER + int(dist * math.sin(angle))
    x = max(0, min(WORLD_SIZE, x))
    y = max(0, min(WORLD_SIZE, y))
    return x, y

def spawn_initial_mobs():
    for mob_type, info in MOB_TYPES.items():
        mob_level = info["level"]
        min_dist, max_dist = get_mob_spawn_zone(mob_level)
        for _ in range(5):
            x, y = get_random_point_in_zone(min_dist, max_dist)
            spawn_mob(x, y, mob_type)

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
            x=CITY_CENTER, y=CITY_CENTER,
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

def get_attack_range(class_name: str) -> int:
    ranged = ["mage", "archer", "buffer"]
    return 150 if class_name.lower() in ranged else 30

def calculate_damage(attacker_stats, defender_stats, weapon_damage=30):
    base_damage = attacker_stats.calculate_physical_damage(weapon_damage)
    final_damage = attacker_stats.calculate_damage_after_armor(base_damage, defender_stats.get_total_stat("vit"))
    if random.random() < attacker_stats.calculate_critical_chance():
        final_damage = int(final_damage * 1.5)
        print("Крит!")
    return max(1, final_damage)

# ------------------------------------------------------------
# Игроки: спавн, движение, атака
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
        "stats": {s: player_data["stats"].get_total_stat(s) for s in ["str","spd","vit","int","cha","lck"]}
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
    for mob_id, mob in mobs.items():
        await websocket.send(json.dumps({
            "type": "spawn_mob", "mob_id": mob_id, "x": mob["x"], "y": mob["y"],
            "mob_type": mob["type"], "hp": mob["hp"], "max_hp": mob["max_hp"]
        }))

async def handle_move(player_id, data):
    new_x = data.get("x")
    new_y = data.get("y")
    new_x = max(0, min(WORLD_SIZE, new_x))
    new_y = max(0, min(WORLD_SIZE, new_y))
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
    attacker = players[player_id]
    defender = players[target_id]
    if is_in_safe_zone(attacker["x"], attacker["y"]) or is_in_safe_zone(defender["x"], defender["y"]):
        await attacker["websocket"].send(json.dumps({"type": "error", "message": "Cannot attack in safe zone"}))
        return
    dist = abs(attacker["x"] - defender["x"]) + abs(attacker["y"] - defender["y"])
    if dist > get_attack_range(attacker["class"]):
        await attacker["websocket"].send(json.dumps({"type": "error", "message": "Too far"}))
        return
    damage = calculate_damage(attacker["stats"], defender["stats"])
    if not hasattr(defender["stats"], "current_hp"):
        defender["stats"].current_hp = defender["stats"].calculate_health()
    defender["stats"].current_hp -= damage
    await attacker["websocket"].send(json.dumps({"type": "attack_result", "target_id": target_id, "damage": damage, "target_hp": defender["stats"].current_hp}))
    await defender["websocket"].send(json.dumps({"type": "attacked", "attacker_id": player_id, "damage": damage, "your_hp": defender["stats"].current_hp}))
    if defender["stats"].current_hp <= 0:
        defender["stats"].current_hp = defender["stats"].calculate_health()
        set_player_position(target_id, CITY_CENTER, CITY_CENTER)
        await defender["websocket"].send(json.dumps({"type": "respawn", "x": CITY_CENTER, "y": CITY_CENTER, "hp": defender["stats"].current_hp}))
        for pid, pdata in players.items():
            if pid != target_id:
                await pdata["websocket"].send(json.dumps({"type": "move", "player_id": target_id, "x": CITY_CENTER, "y": CITY_CENTER}))

# ------------------------------------------------------------
# Мобы
# ------------------------------------------------------------
def spawn_mob(x, y, mob_type="slime"):
    if is_in_safe_zone(x, y):
        angle = math.atan2(y - CITY_CENTER, x - CITY_CENTER)
        x = CITY_CENTER + int((CITY_RADIUS + 10) * math.cos(angle))
        y = CITY_CENTER + int((CITY_RADIUS + 10) * math.sin(angle))
        x = max(0, min(WORLD_SIZE, x))
        y = max(0, min(WORLD_SIZE, y))
    global next_mob_id
    mob_id = next_mob_id
    next_mob_id += 1
    mob_info = MOB_TYPES[mob_type]
    mobs[mob_id] = {
        "id": mob_id, "x": x, "y": y, "type": mob_type,
        "hp": mob_info["hp"], "max_hp": mob_info["hp"],
        "attack": mob_info["attack"], "exp": mob_info["exp"],
        "level": mob_info["level"]
    }
    for pid, pdata in players.items():
        asyncio.create_task(pdata["websocket"].send(json.dumps({
            "type": "spawn_mob", "mob_id": mob_id, "x": x, "y": y,
            "mob_type": mob_type, "hp": mob_info["hp"], "max_hp": mob_info["hp"]
        })))
    return mob_id

async def move_mob(mob_id, new_x, new_y):
    if mob_id not in mobs:
        return
    if is_in_safe_zone(new_x, new_y):
        angle = math.atan2(new_y - CITY_CENTER, new_x - CITY_CENTER)
        new_x = CITY_CENTER + int((CITY_RADIUS + 5) * math.cos(angle))
        new_y = CITY_CENTER + int((CITY_RADIUS + 5) * math.sin(angle))
    new_x = max(0, min(WORLD_SIZE, new_x))
    new_y = max(0, min(WORLD_SIZE, new_y))
    mobs[mob_id]["x"] = new_x
    mobs[mob_id]["y"] = new_y
    for pid, pdata in players.items():
        await pdata["websocket"].send(json.dumps({"type": "move_mob", "mob_id": mob_id, "x": new_x, "y": new_y}))

async def despawn_mob(mob_id):
    if mob_id not in mobs:
        return
    del mobs[mob_id]
    for pid, pdata in players.items():
        await pdata["websocket"].send(json.dumps({"type": "despawn_mob", "mob_id": mob_id}))

async def mob_attack(mob_id, player_id):
    if mob_id not in mobs or player_id not in players:
        return
    mob = mobs[mob_id]
    damage = random.randint(5, mob["attack"])
    defender = players[player_id]["stats"]
    if not hasattr(defender, "current_hp"):
        defender.current_hp = defender.calculate_health()
    defender.current_hp -= damage
    await players[player_id]["websocket"].send(json.dumps({"type": "attacked_by_mob", "mob_id": mob_id, "damage": damage, "your_hp": defender.current_hp}))
    if defender.current_hp <= 0:
        defender.current_hp = defender.calculate_health()
        set_player_position(player_id, CITY_CENTER, CITY_CENTER)
        await players[player_id]["websocket"].send(json.dumps({"type": "respawn", "x": CITY_CENTER, "y": CITY_CENTER, "hp": defender.current_hp}))
        for pid, pdata in players.items():
            if pid != player_id:
                await pdata["websocket"].send(json.dumps({"type": "move", "player_id": player_id, "x": CITY_CENTER, "y": CITY_CENTER}))

async def mob_ai():
    while True:
        await asyncio.sleep(2)
        for mob_id, mob in list(mobs.items()):
            if random.random() < 0.5:
                dx = random.randint(-15, 15)
                dy = random.randint(-15, 15)
                new_x = mob["x"] + dx
                new_y = mob["y"] + dy
                await move_mob(mob_id, new_x, new_y)
            nearest = None
            min_dist = 200
            for pid, pdata in players.items():
                if is_in_safe_zone(pdata["x"], pdata["y"]):
                    continue
                dist = abs(pdata["x"] - mob["x"]) + abs(pdata["y"] - mob["y"])
                if dist < min_dist:
                    min_dist = dist
                    nearest = pid
            if nearest and min_dist < 40:
                await mob_attack(mob_id, nearest)

async def respawn_mob_after_delay(mob_type, x, y):
    await asyncio.sleep(RESPAWN_TIME)
    mob_level = MOB_TYPES[mob_type]["level"]
    min_dist, max_dist = get_mob_spawn_zone(mob_level)
    new_x, new_y = get_random_point_in_zone(min_dist, max_dist)
    spawn_mob(new_x, new_y, mob_type)

async def handle_attack_mob(player_id, data, websocket):
    mob_id = data.get("mob_id")
    if mob_id not in mobs:
        return
    attacker = players[player_id]
    mob = mobs[mob_id]
    if is_in_safe_zone(attacker["x"], attacker["y"]):
        await websocket.send(json.dumps({"type": "error", "message": "Cannot attack in safe zone"}))
        return
    dist = abs(attacker["x"] - mob["x"]) + abs(attacker["y"] - mob["y"])
    if dist > get_attack_range(attacker["class"]):
        await websocket.send(json.dumps({"type": "error", "message": "Too far from mob"}))
        return
    damage = int(attacker["stats"].get_total_stat("str") * 2 + random.randint(5, 15))
    mob["hp"] -= damage
    await websocket.send(json.dumps({"type": "mob_attacked", "mob_id": mob_id, "damage": damage, "hp": mob["hp"]}))
    print(f"Player {player_id} attacked mob {mob_id}, damage {damage}, mob hp {mob['hp']}")
    if mob["hp"] <= 0:
        attacker["exp"] += mob["exp"]
        exp_needed = 100 * attacker["level"]
        while attacker["exp"] >= exp_needed:
            attacker["level"] += 1
            attacker["exp"] -= exp_needed
            exp_needed = 100 * attacker["level"]
        await websocket.send(json.dumps({
            "type": "exp_update",
            "exp": attacker["exp"],
            "level": attacker["level"]
        }))
        print(f"Player {player_id} killed mob, exp now {attacker['exp']}, level {attacker['level']}")
        mob_type = mob["type"]
        await despawn_mob(mob_id)
        asyncio.create_task(respawn_mob_after_delay(mob_type, mob["x"], mob["y"]))

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
                allocation = data.get("allocation")
                if not allocation:
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
        spawn_initial_mobs()
        asyncio.create_task(mob_ai())
        await asyncio.Future()

if __name__ == "__main__":
    asyncio.run(main())