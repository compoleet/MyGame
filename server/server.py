import asyncio
import websockets
import json
import random
import math
from sqlalchemy import select
from game_engine import create_stats_by_class
from database import AsyncSessionLocal, Player, PlayerClass, Item, Inventory, Equipment, init_db

players = {}
mobs = {}
next_mob_id = 1

MOB_TYPES = {
    "slime": {"hp": 50, "attack": 20, "exp": 20, "level": 3, "speed": 6},
    "goblin": {"hp": 80, "attack": 30, "exp": 40, "level": 8, "speed": 10},
}
RESPAWN_TIME = 7

WORLD_SIZE = 100000
CITY_CENTER = WORLD_SIZE // 2
CITY_RADIUS = 500
SAFE_ZONE_RADIUS = CITY_RADIUS

LEVEL_ZONES = {
    1: (CITY_RADIUS + 300, CITY_RADIUS + 500),   # 800-1000
    2: (CITY_RADIUS + 300, CITY_RADIUS + 500),
    3: (CITY_RADIUS + 300, CITY_RADIUS + 500),
    4: (CITY_RADIUS + 300, CITY_RADIUS + 500),
    5: (CITY_RADIUS + 300, CITY_RADIUS + 500),
    6: (CITY_RADIUS + 550, CITY_RADIUS + 900),   # 1050-1400
    7: (CITY_RADIUS + 550, CITY_RADIUS + 900),
    8: (CITY_RADIUS + 550, CITY_RADIUS + 900),
    9: (CITY_RADIUS + 550, CITY_RADIUS + 900),
    10: (CITY_RADIUS + 550, CITY_RADIUS + 900),
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
    return max(0, min(WORLD_SIZE, x)), max(0, min(WORLD_SIZE, y))

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
        await session.flush()   # Важно: теперь new_player.id будет заполнен
        # Создаём запись экипировки
        equip = Equipment(player_id=new_player.id)
        session.add(equip)
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
# Инвентарь и экипировка
# ------------------------------------------------------------
async def get_player_inventory(player_id: int):
    async with AsyncSessionLocal() as session:
        result = await session.execute(select(Inventory).where(Inventory.player_id == player_id))
        inv = result.scalars().all()
        items = []
        for entry in inv:
            item = await session.get(Item, entry.item_id)
            if item:
                items.append({
                    "id": entry.id,
                    "item_id": entry.item_id,
                    "name": item.name,
                    "type": item.item_type,
                    "quantity": entry.quantity,
                    "slot": item.slot,
                    "value": item.value
                })
        return items

async def get_player_equipment(player_id: int):
    async with AsyncSessionLocal() as session:
        equip = await session.execute(select(Equipment).where(Equipment.player_id == player_id))
        equip_row = equip.scalar_one_or_none()
        if not equip_row:
            return {}
        result = {}
        for slot in ["weapon", "head", "chest", "legs", "feet"]:
            item_id = getattr(equip_row, slot)
            if item_id:
                item = await session.get(Item, item_id)
                if item:
                    result[slot] = {"id": item_id, "name": item.name, "stat_bonuses": json.loads(item.stat_bonuses)}
                else:
                    result[slot] = None
            else:
                result[slot] = None
        return result

async def equip_item(player_id: int, inv_id: int, slot: str):
    async with AsyncSessionLocal() as session:
        # Найти предмет в инвентаре
        inv_entry = await session.get(Inventory, inv_id)
        if not inv_entry:
            return False
        item = await session.get(Item, inv_entry.item_id)
        if not item or item.slot != slot:
            return False
        # Получить экипировку игрока
        equip = await session.execute(select(Equipment).where(Equipment.player_id == player_id))
        equip_row = equip.scalar_one_or_none()
        if not equip_row:
            equip_row = Equipment(player_id=player_id)
            session.add(equip_row)
        # Снять текущий предмет (если есть) – положить обратно в инвентарь
        old_item_id = getattr(equip_row, slot)
        if old_item_id:
            # Проверить, есть ли уже такой предмет в инвентаре (стек)
            existing = await session.execute(select(Inventory).where(Inventory.player_id == player_id, Inventory.item_id == old_item_id))
            existing_row = existing.scalar_one_or_none()
            if existing_row:
                existing_row.quantity += 1
            else:
                new_inv = Inventory(player_id=player_id, item_id=old_item_id, quantity=1)
                session.add(new_inv)
        # Экипировать новый
        setattr(equip_row, slot, inv_entry.item_id)
        # Убрать из инвентаря
        if inv_entry.quantity > 1:
            inv_entry.quantity -= 1
        else:
            await session.delete(inv_entry)
        await session.commit()
        return True

# ------------------------------------------------------------
# Игровая логика (без изменений, кроме добавления дропа)
# ------------------------------------------------------------
def set_player_position(player_id, x, y):
    players[player_id]["x"] = x
    players[player_id]["y"] = y

def get_attack_range(class_name: str) -> int:
    return 150 if class_name in ("mage", "archer", "buffer") else 30

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
# Мобы с дропом
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
    # Настройки
    MOVE_INTERVAL = 0.033   # примерно 30 fps (0.033 сек)
    AGGRO_INTERVAL = 0.5    # проверка агрессии каждые 0.5 сек
    MOVE_STEP = 8           # шаг моба за один тик (пикселей)
    AGRO_RANGE = 400        # дистанция, с которой моб замечает игрока
    ATTACK_RANGE = 50       # дистанция для атаки

    last_aggro_check = 0
    while True:
        start_time = asyncio.get_event_loop().time()
        
        # Движение (каждый тик)
        for mob_id, mob in list(mobs.items()):
            # Движение к игроку или блуждание
            nearest = None
            min_dist = AGRO_RANGE
            # Поиск ближайшего игрока (только для выбора направления, не каждый тик, но можно)
            # Для оптимизации можно искать реже, но здесь оставим каждый тик для быстрой реакции
            for pid, pdata in players.items():
                if is_in_safe_zone(pdata["x"], pdata["y"]):
                    continue
                dist = abs(pdata["x"] - mob["x"]) + abs(pdata["y"] - mob["y"])
                if dist < min_dist:
                    min_dist = dist
                    nearest = pid
            if nearest:
                # Движение к игроку
                target = players[nearest]
                dx = target["x"] - mob["x"]
                dy = target["y"] - mob["y"]
                length = max(1, abs(dx) + abs(dy))
                step_x = int(MOVE_STEP * dx / length)
                step_y = int(MOVE_STEP * dy / length)
                new_x = mob["x"] + step_x
                new_y = mob["y"] + step_y
            else:
                # Случайное блуждание
                dx = random.randint(-MOVE_STEP, MOVE_STEP)
                dy = random.randint(-MOVE_STEP, MOVE_STEP)
                new_x = mob["x"] + dx
                new_y = mob["y"] + dy
            # Проверка границ и safe zone
            new_x = max(0, min(WORLD_SIZE, new_x))
            new_y = max(0, min(WORLD_SIZE, new_y))
            if not is_in_safe_zone(new_x, new_y):
                await move_mob(mob_id, new_x, new_y)

        # Атака и агрессия – реже
        if asyncio.get_event_loop().time() - last_aggro_check >= AGGRO_INTERVAL:
            last_aggro_check = asyncio.get_event_loop().time()
            for mob_id, mob in list(mobs.items()):
                nearest = None
                min_dist = AGRO_RANGE
                for pid, pdata in players.items():
                    if is_in_safe_zone(pdata["x"], pdata["y"]):
                        continue
                    dist = abs(pdata["x"] - mob["x"]) + abs(pdata["y"] - mob["y"])
                    if dist < min_dist:
                        min_dist = dist
                        nearest = pid
                if nearest and min_dist < ATTACK_RANGE:
                    await mob_attack(mob_id, nearest)

        # Задержка до следующего тика с учётом времени выполнения
        elapsed = asyncio.get_event_loop().time() - start_time
        sleep_time = max(0, MOVE_INTERVAL - elapsed)
        await asyncio.sleep(sleep_time)

async def respawn_mob_after_delay(mob_type, x, y):
    await asyncio.sleep(RESPAWN_TIME)
    mob_level = MOB_TYPES[mob_type]["level"]
    min_dist, max_dist = get_mob_spawn_zone(mob_level)
    new_x, new_y = get_random_point_in_zone(min_dist, max_dist)
    spawn_mob(new_x, new_y, mob_type)

async def drop_loot(player_id, mob_type):
    # Простой дроп: с вероятностью 30% даём зелье здоровья
    if random.random() < 0.3:
        async with AsyncSessionLocal() as session:
            # Найти предмет "Зелье здоровья" (id=1 предположительно)
            item = await session.execute(select(Item).where(Item.name == "Зелье здоровья"))
            item_row = item.scalar_one_or_none()
            if item_row:
                inv_entry = await session.execute(select(Inventory).where(Inventory.player_id == player_id, Inventory.item_id == item_row.id))
                inv = inv_entry.scalar_one_or_none()
                if inv:
                    inv.quantity += 1
                else:
                    new_inv = Inventory(player_id=player_id, item_id=item_row.id, quantity=1)
                    session.add(new_inv)
                await session.commit()
                # Уведомить клиента (позже)

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
    if mob["hp"] <= 0:
        attacker["exp"] += mob["exp"]
        exp_needed = 100 * attacker["level"]
        while attacker["exp"] >= exp_needed:
            attacker["level"] += 1
            attacker["exp"] -= exp_needed
            exp_needed = 100 * attacker["level"]
        await websocket.send(json.dumps({"type": "exp_update", "exp": attacker["exp"], "level": attacker["level"]}))
        # Дроп
        await drop_loot(player_id, mob["type"])
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
                    allocation = {"str": 30, "spd": 5, "vit": 25, "int": 5, "cha": 5, "lck": 5}
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
                elif data["type"] == "get_inventory":
                    inv = await get_player_inventory(player_id)
                    equip = await get_player_equipment(player_id)
                    await websocket.send(json.dumps({"type": "inventory_data", "inventory": inv, "equipment": equip}))
                elif data["type"] == "equip_item":
                    inv_id = data.get("inv_id")
                    slot = data.get("slot")
                    success = await equip_item(player_id, inv_id, slot)
                    if success:
                        # После экипировки пересылаем обновлённые данные
                        inv = await get_player_inventory(player_id)
                        equip = await get_player_equipment(player_id)
                        await websocket.send(json.dumps({"type": "inventory_data", "inventory": inv, "equipment": equip}))
                    else:
                        await websocket.send(json.dumps({"type": "error", "message": "Equip failed"}))
                elif data["type"] == "use_item":
                    inv_id = data.get("inv_id")
                    success = await use_item(player_id, inv_id)
                    await websocket.send(json.dumps({"type": "item_action_result", "success": success, "action": "use"}))
                elif data["type"] == "drop_item":
                    inv_id = data.get("inv_id")
                    success = await drop_item(player_id, inv_id)
                    await websocket.send(json.dumps({"type": "item_action_result", "success": success, "action": "drop"}))
                elif data["type"] == "destroy_item":
                    inv_id = data.get("inv_id")
                    success = await destroy_item(player_id, inv_id)
                    await websocket.send(json.dumps({"type": "item_action_result", "success": success, "action": "destroy"}))
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
#инвентарь
# ------------------------------------------------------------           
async def use_item(player_id: int, inv_id: int):
    async with AsyncSessionLocal() as session:
        inv_entry = await session.get(Inventory, inv_id)
        if not inv_entry:
            return False
        item = await session.get(Item, inv_entry.item_id)
        if not item:
            return False
        # Только расходники (consumable) пока
        if item.item_type != "consumable":
            return False
        # Пример: зелье здоровья восстанавливает 50 HP
        if item.name == "Зелье здоровья":
            # Получаем игрока
            player = await session.get(Player, player_id)
            if player:
                # Здесь нужно обновить текущее HP игрока в памяти сервера (players[player_id]["stats"].current_hp)
                # Но проще отправить событие клиенту, а клиент сам увеличит HP (с проверкой на сервере при следующей атаке)
                # Для упрощения: добавим временное поле в stats
                stats = players[player_id]["stats"]
                stats.current_hp = min(stats.calculate_health(), stats.current_hp + 50)
                # Уменьшаем количество предмета
                if inv_entry.quantity > 1:
                    inv_entry.quantity -= 1
                else:
                    await session.delete(inv_entry)
                await session.commit()
                # Уведомить клиента об изменении HP
                await players[player_id]["websocket"].send(json.dumps({
                    "type": "hp_update",
                    "hp": stats.current_hp
                }))
                return True
        return False

async def drop_item(player_id: int, inv_id: int):
    async with AsyncSessionLocal() as session:
        inv_entry = await session.get(Inventory, inv_id)
        if not inv_entry:
            return False
        # Удаляем предмет из инвентаря
        if inv_entry.quantity > 1:
            inv_entry.quantity -= 1
        else:
            await session.delete(inv_entry)
        await session.commit()
        # TODO: создать сущность "дроп" на земле (пока пропустим)
        return True

async def destroy_item(player_id: int, inv_id: int):
    async with AsyncSessionLocal() as session:
        inv_entry = await session.get(Inventory, inv_id)
        if not inv_entry:
            return False
        if inv_entry.quantity > 1:
            inv_entry.quantity -= 1
        else:
            await session.delete(inv_entry)
        await session.commit()
        return True
# ------------------------------------------------------------
# Запуск
# ------------------------------------------------------------
async def main():
    await init_db()
    async with websockets.serve(handle_player_input, "localhost", 8765):
        print("Сервер запущен на ws://localhost:8765")
        spawn_initial_mobs()
        asyncio.create_task(mob_ai())
        await asyncio.Future()

if __name__ == "__main__":
    asyncio.run(main())