import pygame
import asyncio
import websockets
import json
import threading
import sys

WIDTH, HEIGHT = 1000, 700
BG_COLOR = (30, 30, 40)
BUTTON_COLOR = (70, 70, 90)
BUTTON_HOVER = (100, 100, 120)
TEXT_COLOR = (255, 255, 255)
LABEL_COLOR = (200, 200, 200)
VALUE_COLOR = (255, 255, 0)
INPUT_BOX_COLOR = (100, 100, 120)
INPUT_ACTIVE_COLOR = (200, 200, 250)

# ------------------------------------------------------------
# Вспомогательные функции для рисования текста с переносом
# ------------------------------------------------------------
def draw_text(screen, text, font, color, x, y, max_width=None):
    if max_width is None:
        screen.blit(font.render(text, True, color), (x, y))
        return
    words = text.split(' ')
    lines = []
    current_line = []
    for w in words:
        test_line = ' '.join(current_line + [w])
        if font.size(test_line)[0] <= max_width:
            current_line.append(w)
        else:
            lines.append(' '.join(current_line))
            current_line = [w]
    lines.append(' '.join(current_line))
    for i, line in enumerate(lines):
        screen.blit(font.render(line, True, color), (x, y + i * font.get_height()))

# ------------------------------------------------------------
# Экран логина
# ------------------------------------------------------------
class LoginScreen:
    def __init__(self, screen):
        self.screen = screen
        self.username = ""
        self.password = ""
        self.active_field = None  # "username" or "password"
        self.username_rect = pygame.Rect(WIDTH//2 - 150, 200, 300, 40)
        self.password_rect = pygame.Rect(WIDTH//2 - 150, 270, 300, 40)
        self.login_btn = pygame.Rect(WIDTH//2 - 100, 350, 90, 40)
        self.register_btn = pygame.Rect(WIDTH//2 + 10, 350, 90, 40)
        self.font = pygame.font.SysFont("Arial", 24)
        self.small_font = pygame.font.SysFont("Arial", 18)
        self.error_msg = ""

    def handle_event(self, event):
        if event.type == pygame.MOUSEBUTTONDOWN:
            if self.username_rect.collidepoint(event.pos):
                self.active_field = "username"
            elif self.password_rect.collidepoint(event.pos):
                self.active_field = "password"
            else:
                self.active_field = None
            if self.login_btn.collidepoint(event.pos):
                if self.username and self.password:
                    return ("login", self.username, self.password)
                else:
                    self.error_msg = "Enter username and password"
            if self.register_btn.collidepoint(event.pos):
                return ("register", None, None)
        if event.type == pygame.KEYDOWN and self.active_field:
            if event.key == pygame.K_BACKSPACE:
                if self.active_field == "username":
                    self.username = self.username[:-1]
                else:
                    self.password = self.password[:-1]
            elif event.key == pygame.K_RETURN:
                self.active_field = None
            else:
                if len(getattr(self, self.active_field)) < 20:
                    setattr(self, self.active_field, getattr(self, self.active_field) + event.unicode)
        return None

    def draw(self):
        self.screen.fill(BG_COLOR)
        title = self.font.render("MMORPG LOGIN", True, TEXT_COLOR)
        self.screen.blit(title, (WIDTH//2 - title.get_width()//2, 80))
        # Поля ввода
        for field, rect in [("username", self.username_rect), ("password", self.password_rect)]:
            color = INPUT_ACTIVE_COLOR if self.active_field == field else INPUT_BOX_COLOR
            pygame.draw.rect(self.screen, color, rect, 2)
            value = getattr(self, field)
            text = self.font.render("*"*len(value) if field=="password" else value, True, TEXT_COLOR)
            self.screen.blit(text, (rect.x + 5, rect.y + 5))
            label = self.small_font.render(field.capitalize(), True, LABEL_COLOR)
            self.screen.blit(label, (rect.x, rect.y - 20))
        # Кнопки
        pygame.draw.rect(self.screen, BUTTON_COLOR, self.login_btn)
        pygame.draw.rect(self.screen, BUTTON_COLOR, self.register_btn)
        login_text = self.font.render("Login", True, TEXT_COLOR)
        reg_text = self.font.render("Register", True, TEXT_COLOR)
        self.screen.blit(login_text, (self.login_btn.x + 15, self.login_btn.y + 10))
        self.screen.blit(reg_text, (self.register_btn.x + 8, self.register_btn.y + 10))
        # Ошибка
        if self.error_msg:
            error_text = self.small_font.render(self.error_msg, True, (255, 100, 100))
            self.screen.blit(error_text, (WIDTH//2 - error_text.get_width()//2, 310))
        pygame.display.flip()

# ------------------------------------------------------------
# Конструктор персонажа (экран) – исправленные координаты
# ------------------------------------------------------------
class CharacterCreatorScreen:
    def __init__(self, screen):
        self.screen = screen
        self.running = True
        self.username = ""
        self.password = ""
        self.active_field = None
        self.class_names = ["warrior", "mage", "archer", "shield", "sword", "buffer", "tamer", "assassin", "crafter"]
        self.class_index = 0
        self.class_display = self.class_names[self.class_index].capitalize()
        self.base = {"str": 5, "spd": 5, "vit": 5, "int": 5, "cha": 5, "lck": 5}
        self.remaining_points = 45
        self.multipliers = self._get_multipliers()
        self.font = pygame.font.SysFont("Arial", 22)
        self.small_font = pygame.font.SysFont("Arial", 16)
        self.desc_font = pygame.font.SysFont("Arial", 14)
        # Поля ввода - сдвинем чуть выше, чтобы освободить место
        self.input_boxes = {
            "username": pygame.Rect(WIDTH//2 - 150, 45, 300, 35),
            "password": pygame.Rect(WIDTH//2 - 150, 100, 300, 35)
        }
        # Статы – начало ниже, чем было (было 140, станет 180)
        self.stat_buttons = {}
        y_start = 190
        for i, stat in enumerate(["str", "spd", "vit", "int", "cha", "lck"]):
            rect_minus = pygame.Rect(50, y_start + i*35, 30, 25)
            rect_plus = pygame.Rect(180, y_start + i*35, 30, 25)
            rect_value = pygame.Rect(90, y_start + i*35, 80, 25)
            self.stat_buttons[stat] = {"minus": rect_minus, "plus": rect_plus, "value": rect_value}
        self.create_button = pygame.Rect(WIDTH//2 - 100, HEIGHT - 70, 200, 45)
        self.back_button = pygame.Rect(20, HEIGHT - 45, 80, 30)
        self.error_msg = ""

    def _get_multipliers(self):
        class_mult = {
            "warrior": {"str": 1.25, "vit": 1.25},
            "mage": {"int": 1.5, "lck": 1.2},
            "archer": {"str": 1.4, "spd": 1.4},
            "shield": {"vit": 1.5, "str": 1.2},
            "sword": {"str": 1.5, "spd": 1.2},
            "buffer": {"cha": 1.5, "int": 1.2},
            "tamer": {"cha": 1.5, "vit": 1.2},
            "assassin": {"str": 1.4, "spd": 1.4, "lck": 1.2},
            "crafter": {"cha": 1.5, "str": 1.2}
        }
        mult = class_mult.get(self.class_names[self.class_index], {})
        res = {s: 1.0 for s in ["str","spd","vit","int","cha","lck"]}
        res.update(mult)
        return res

    def get_total_stat(self, stat):
        return int(self.base[stat] * self.multipliers[stat])

    def draw(self):
        self.screen.fill(BG_COLOR)
        title = self.font.render("CREATE CHARACTER", True, TEXT_COLOR)
        self.screen.blit(title, (WIDTH//2 - title.get_width()//2, 5))
        # Поля логин/пароль
        for field, rect in self.input_boxes.items():
            color = INPUT_ACTIVE_COLOR if self.active_field == field else INPUT_BOX_COLOR
            pygame.draw.rect(self.screen, color, rect, 2)
            val = getattr(self, field)
            display = "*"*len(val) if field == "password" else val
            text = self.small_font.render(display, True, TEXT_COLOR)
            self.screen.blit(text, (rect.x + 5, rect.y + 5))
            label = self.small_font.render(field.capitalize(), True, LABEL_COLOR)
            self.screen.blit(label, (rect.x, rect.y - 18))
        # Выбор класса – сдвинут ниже (было y=125, теперь y=150)
        class_rect = pygame.Rect(WIDTH//2 - 80, 145, 160, 30)
        pygame.draw.rect(self.screen, (80,80,100), class_rect)
        class_text = self.font.render(self.class_display, True, TEXT_COLOR)
        self.screen.blit(class_text, (class_rect.x + 10, class_rect.y + 3))
        left_arrow = pygame.Rect(class_rect.x - 25, class_rect.y, 20, 30)
        right_arrow = pygame.Rect(class_rect.x + class_rect.width + 5, class_rect.y, 20, 30)
        pygame.draw.polygon(self.screen, (200,200,200), [(left_arrow.x+12, left_arrow.y+5), (left_arrow.x+2, left_arrow.y+15), (left_arrow.x+12, left_arrow.y+25)])
        pygame.draw.polygon(self.screen, (200,200,200), [(right_arrow.x+8, right_arrow.y+5), (right_arrow.x+18, right_arrow.y+15), (right_arrow.x+8, right_arrow.y+25)])
        # Пояснения к статам – теперь начинаются ниже, чтобы не пересекаться с классом
        desc_x = 240
        desc_y = 190
        stat_desc = {
            "str": "Физический урон",
            "spd": "Скорость атаки/передвижения",
            "vit": "HP и защита (порог)",
            "int": "Мана, маг.урон, скорость каста",
            "cha": "Удачные сделки, приручение",
            "lck": "Шанс лута, крита, приручение"
        }
        for i, stat in enumerate(["str","spd","vit","int","cha","lck"]):
            label = self.small_font.render(stat.upper(), True, VALUE_COLOR)
            self.screen.blit(label, (desc_x, desc_y + i*35))
            desc_text = self.desc_font.render(stat_desc[stat], True, LABEL_COLOR)
            self.screen.blit(desc_text, (desc_x + 40, desc_y + i*35))
        # Кнопки +/-
        for stat, rects in self.stat_buttons.items():
            base_val = self.base[stat]
            total_val = self.get_total_stat(stat)
            value_text = self.small_font.render(f"{base_val} → {total_val}", True, VALUE_COLOR)
            self.screen.blit(value_text, (rects["value"].x, rects["value"].y))
            pygame.draw.rect(self.screen, BUTTON_COLOR, rects["minus"])
            pygame.draw.rect(self.screen, BUTTON_COLOR, rects["plus"])
            minus_text = self.font.render("-", True, TEXT_COLOR)
            plus_text = self.font.render("+", True, TEXT_COLOR)
            self.screen.blit(minus_text, (rects["minus"].x + 10, rects["minus"].y + 2))
            self.screen.blit(plus_text, (rects["plus"].x + 10, rects["plus"].y + 2))
        # Оставшиеся очки
        pts_text = self.small_font.render(f"Points left: {self.remaining_points}", True, TEXT_COLOR)
        self.screen.blit(pts_text, (WIDTH//2 - 60, HEIGHT - 120))
        # Кнопка Create
        pygame.draw.rect(self.screen, (0,150,0) if self.remaining_points==0 else BUTTON_COLOR, self.create_button)
        create_txt = self.font.render("CREATE", True, TEXT_COLOR)
        self.screen.blit(create_txt, (self.create_button.x + 60, self.create_button.y + 10))
        # Кнопка Back
        pygame.draw.rect(self.screen, BUTTON_COLOR, self.back_button)
        back_txt = self.small_font.render("Back", True, TEXT_COLOR)
        self.screen.blit(back_txt, (self.back_button.x + 20, self.back_button.y + 5))
        if self.error_msg:
            err = self.small_font.render(self.error_msg, True, (255,100,100))
            self.screen.blit(err, (WIDTH//2 - err.get_width()//2, HEIGHT - 50))
        pygame.display.flip()

    def handle_event(self, event):
        if event.type == pygame.QUIT:
            return "quit"
        if event.type == pygame.MOUSEBUTTONDOWN:
            # Поля ввода
            for field, rect in self.input_boxes.items():
                if rect.collidepoint(event.pos):
                    self.active_field = field
                    break
            else:
                self.active_field = None
            # Кнопки класса
            class_rect = pygame.Rect(WIDTH//2 - 80, 120, 160, 30)
            left_arrow = pygame.Rect(class_rect.x - 25, class_rect.y, 20, 30)
            right_arrow = pygame.Rect(class_rect.x + class_rect.width + 5, class_rect.y, 20, 30)
            if left_arrow.collidepoint(event.pos):
                self.class_index = (self.class_index - 1) % len(self.class_names)
                self.class_display = self.class_names[self.class_index].capitalize()
                self.multipliers = self._get_multipliers()
            if right_arrow.collidepoint(event.pos):
                self.class_index = (self.class_index + 1) % len(self.class_names)
                self.class_display = self.class_names[self.class_index].capitalize()
                self.multipliers = self._get_multipliers()
            # Кнопки статов
            for stat, rects in self.stat_buttons.items():
                if rects["minus"].collidepoint(event.pos) and self.base[stat] > 5:
                    self.base[stat] -= 1
                    self.remaining_points += 1
                if rects["plus"].collidepoint(event.pos) and self.remaining_points > 0:
                    self.base[stat] += 1
                    self.remaining_points -= 1
            # Кнопка Create
            if self.create_button.collidepoint(event.pos):
                if self.remaining_points != 0:
                    self.error_msg = f"Use all points! {self.remaining_points} left"
                elif not self.username or not self.password:
                    self.error_msg = "Enter username and password"
                else:
                    return ("create", {
                        "username": self.username,
                        "password": self.password,
                        "class": self.class_names[self.class_index],
                        "allocation": {stat: self.base[stat] for stat in self.base}
                    })
            # Кнопка Back
            if self.back_button.collidepoint(event.pos):
                return "back"
        if event.type == pygame.KEYDOWN and self.active_field:
            if event.key == pygame.K_BACKSPACE:
                setattr(self, self.active_field, getattr(self, self.active_field)[:-1])
            elif event.key == pygame.K_RETURN:
                self.active_field = None
            else:
                if len(getattr(self, self.active_field)) < 20:
                    setattr(self, self.active_field, getattr(self, self.active_field) + event.unicode)
        return None

# ------------------------------------------------------------
# Игровой клиент (MMOClient) – без изменений
# ------------------------------------------------------------
class MMOClient:
    def __init__(self, uri, username, password):
        self.uri = uri
        self.username = username
        self.password = password
        self.players = {}
        self.mobs = {}
        self.my_id = None
        self.my_class = None
        self.running = True
        self.ws = None
        self.loop = None

    async def connect(self):
        self.ws = await websockets.connect(self.uri)
        await self.ws.send(json.dumps({"type": "auth", "username": self.username, "password": self.password}))
        msg = await self.ws.recv()
        data = json.loads(msg)
        if data["type"] == "init":
            self.my_id = data["data"]["player_id"]
            self.my_class = data["data"]["class"]
            self.players[self.my_id] = (data["data"]["x"], data["data"]["y"], data["data"]["username"], data["data"]["class"])
            print(f"Init OK. My id: {self.my_id}, class: {self.my_class}")
            return True
        else:
            print("Auth failed")
            return False

    async def send_move(self, x, y):
        await self.ws.send(json.dumps({"type": "move", "x": x, "y": y}))

    async def send_attack(self, target_type, target_id):
        if target_type == "player":
            await self.ws.send(json.dumps({"type": "attack", "target_id": target_id}))
        elif target_type == "mob":
            await self.ws.send(json.dumps({"type": "attack_mob", "mob_id": target_id}))

    async def receive_loop(self):
        try:
            async for msg in self.ws:
                data = json.loads(msg)
                t = data["type"]
                if t == "spawn":
                    pid = data["player_id"]
                    if pid not in self.players:
                        self.players[pid] = (data["x"], data["y"], data["username"], data["class"])
                elif t == "move":
                    pid = data["player_id"]
                    if pid in self.players:
                        x,y,name,cls = self.players[pid]
                        self.players[pid] = (data["x"], data["y"], name, cls)
                elif t == "despawn":
                    pid = data["player_id"]
                    if pid in self.players:
                        del self.players[pid]
                elif t == "spawn_mob":
                    self.mobs[data["mob_id"]] = {"x": data["x"], "y": data["y"], "type": data["mob_type"], "hp": data["hp"], "max_hp": data["max_hp"]}
                elif t == "move_mob":
                    if data["mob_id"] in self.mobs:
                        self.mobs[data["mob_id"]]["x"] = data["x"]
                        self.mobs[data["mob_id"]]["y"] = data["y"]
                elif t == "despawn_mob":
                    if data["mob_id"] in self.mobs:
                        del self.mobs[data["mob_id"]]
                elif t == "mob_attacked":
                    if data["mob_id"] in self.mobs:
                        self.mobs[data["mob_id"]]["hp"] = data["hp"]
                elif t == "attacked_by_mob":
                    print(f"Моб нанёс {data['damage']} урона, у вас {data['your_hp']} HP")
                elif t == "level_up":
                    print(f"Поздравляем! Вы достигли {data['level']} уровня!")
                elif t == "respawn":
                    if self.my_id in self.players:
                        x,y,name,cls = self.players[self.my_id]
                        self.players[self.my_id] = (data["x"], data["y"], name, cls)
                    print(f"Вы возродились в ({data['x']}, {data['y']}), HP={data['hp']}")
                elif t == "error":
                    print(f"Ошибка сервера: {data['message']}")
        except websockets.exceptions.ConnectionClosed:
            print("Connection closed")
        self.running = False

    def start(self):
        self.loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self.loop)
        success = self.loop.run_until_complete(self.connect())
        if not success:
            return
        t = threading.Thread(target=lambda: self.loop.run_until_complete(self.receive_loop()))
        t.daemon = True
        t.start()

    def get_my_position(self):
        if self.my_id in self.players:
            return self.players[self.my_id][0], self.players[self.my_id][1]
        return None

    def set_my_position(self, x, y):
        if self.my_id in self.players:
            name, cls = self.players[self.my_id][2], self.players[self.my_id][3]
            self.players[self.my_id] = (x, y, name, cls)

    async def move_async(self, x, y):
        await self.send_move(x, y)
        self.set_my_position(x, y)

    def move(self, x, y):
        asyncio.run_coroutine_threadsafe(self.move_async(x, y), self.loop)

    def get_attack_range(self):
        ranged = ["mage", "archer", "buffer"]
        return 150 if self.my_class in ranged else 30

    def find_nearest_enemy(self):
        my_x, my_y = self.get_my_position()
        if my_x is None:
            return None
        radius = self.get_attack_range()
        best = None
        best_dist = radius + 1
        for pid, (x,y,name,cls) in self.players.items():
            if pid == self.my_id:
                continue
            dist = abs(x - my_x) + abs(y - my_y)
            if dist <= radius and dist < best_dist:
                best_dist = dist
                best = ("player", pid)
        for mob_id, mob in self.mobs.items():
            dist = abs(mob["x"] - my_x) + abs(mob["y"] - my_y)
            if dist <= radius and dist < best_dist:
                best_dist = dist
                best = ("mob", mob_id)
        return best[0], best[1], best_dist if best else None

    async def attack_nearest_async(self):
        nearest = self.find_nearest_enemy()
        if nearest:
            typ, tid, dist = nearest
            await self.send_attack(typ, tid)
            print(f"Атака {typ} {tid} (дист. {dist})")
        else:
            print("Нет врагов в радиусе атаки")

    def attack_nearest(self):
        asyncio.run_coroutine_threadsafe(self.attack_nearest_async(), self.loop)

    def stop(self):
        self.running = False
        if self.loop:
            self.loop.call_soon_threadsafe(self.loop.stop)

# ------------------------------------------------------------
# Функция отрисовки игрового мира
# ------------------------------------------------------------
def draw_game(screen, client, camera_x, camera_y, show_radius):
    screen.fill(BG_COLOR)
    for pid, (x,y,username,cls) in client.players.items():
        sx = x - camera_x
        sy = y - camera_y
        if -50 < sx < WIDTH+50 and -50 < sy < HEIGHT+50:
            color = (0,255,0) if pid == client.my_id else (255,0,0)
            pygame.draw.circle(screen, color, (int(sx), int(sy)), 8)
            font = pygame.font.SysFont(None, 18)
            text = font.render(username, True, (255,255,255))
            screen.blit(text, (sx - text.get_width()//2, sy - 15))
    for mob_id, mob in client.mobs.items():
        sx = mob["x"] - camera_x
        sy = mob["y"] - camera_y
        if -50 < sx < WIDTH+50 and -50 < sy < HEIGHT+50:
            pygame.draw.rect(screen, (139,69,19), (int(sx)-8, int(sy)-8, 16, 16))
            hp_percent = mob["hp"] / mob["max_hp"]
            pygame.draw.rect(screen, (255,0,0), (int(sx)-12, int(sy)-12, 24, 4))
            pygame.draw.rect(screen, (0,255,0), (int(sx)-12, int(sy)-12, int(24 * hp_percent), 4))
    if show_radius and client.my_id in client.players:
        my_x, my_y = client.get_my_position()
        if my_x is not None:
            sx = my_x - camera_x
            sy = my_y - camera_y
            radius = client.get_attack_range()
            surf = pygame.Surface((radius*2, radius*2), pygame.SRCALPHA)
            color = (100,100,255,50) if radius > 100 else (255,100,100,50)
            pygame.draw.circle(surf, color, (radius, radius), radius)
            screen.blit(surf, (sx - radius, sy - radius))
    pos = client.get_my_position()
    if pos:
        font = pygame.font.SysFont(None, 24)
        coord_text = font.render(f"X: {pos[0]} Y: {pos[1]}  (Ctrl - toggle radius)", True, (255,255,255))
        screen.blit(coord_text, (10, 10))
    pygame.display.flip()

# ------------------------------------------------------------
# Главный цикл с управлением экранами
# ------------------------------------------------------------
def main():
    pygame.init()
    screen = pygame.display.set_mode((WIDTH, HEIGHT))
    pygame.display.set_caption("MMORPG Client")

    current_screen = "login"
    login = LoginScreen(screen)
    creator = None
    client = None
    clock = pygame.time.Clock()
    running = True

    while running:
        if current_screen == "login":
            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    running = False
                res = login.handle_event(event)
                if res:
                    if res[0] == "login":
                        username, password = res[1], res[2]
                        client = MMOClient("ws://localhost:8765", username, password)
                        client.start()
                        import time
                        time.sleep(1)
                        if client.my_id is not None:
                            current_screen = "game"
                        else:
                            login.error_msg = "Auth failed. Check server."
                    elif res[0] == "register":
                        creator = CharacterCreatorScreen(screen)
                        current_screen = "creator"
            if current_screen == "login":
                login.draw()
        elif current_screen == "creator":
            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    running = False
                res = creator.handle_event(event)
                if res == "quit":
                    running = False
                elif res == "back":
                    current_screen = "login"
                    creator = None
                elif isinstance(res, tuple) and res[0] == "create":
                    data = res[1]
                    async def reg():
                        async with websockets.connect("ws://localhost:8765") as ws:
                            await ws.send(json.dumps({
                                "type": "register",
                                "username": data["username"],
                                "password": data["password"],
                                "class": data["class"],
                                "allocation": data["allocation"]
                            }))
                            resp = await ws.recv()
                            return json.loads(resp)
                    loop = asyncio.new_event_loop()
                    asyncio.set_event_loop(loop)
                    resp = loop.run_until_complete(reg())
                    loop.close()
                    if resp.get("success"):
                        client = MMOClient("ws://localhost:8765", data["username"], data["password"])
                        client.start()
                        time.sleep(1)
                        if client.my_id is not None:
                            current_screen = "game"
                        else:
                            login.error_msg = "Auto-login failed after registration"
                            current_screen = "login"
                    else:
                        creator.error_msg = resp.get("message", "Registration failed")
            if current_screen == "creator":
                creator.draw()
        elif current_screen == "game":
            camera_x, camera_y = 0, 0
            show_radius = True
            game_running = True
            while game_running and client.running:
                for event in pygame.event.get():
                    if event.type == pygame.QUIT:
                        game_running = False
                        running = False
                    elif event.type == pygame.KEYDOWN:
                        if event.key == pygame.K_SPACE:
                            client.attack_nearest()
                        elif event.key in (pygame.K_LCTRL, pygame.K_RCTRL):
                            show_radius = not show_radius
                            print(f"Radius {'shown' if show_radius else 'hidden'}")
                keys = pygame.key.get_pressed()
                dx = dy = 0
                if keys[pygame.K_a] or keys[pygame.K_LEFT]:
                    dx = -5
                if keys[pygame.K_d] or keys[pygame.K_RIGHT]:
                    dx = 5
                if keys[pygame.K_w] or keys[pygame.K_UP]:
                    dy = -5
                if keys[pygame.K_s] or keys[pygame.K_DOWN]:
                    dy = 5
                if dx != 0 or dy != 0:
                    pos = client.get_my_position()
                    if pos:
                        new_x = max(0, min(1000, pos[0] + dx))
                        new_y = max(0, min(1000, pos[1] + dy))
                        client.move(new_x, new_y)
                pos = client.get_my_position()
                if pos:
                    camera_x = pos[0] - WIDTH//2
                    camera_y = pos[1] - HEIGHT//2
                draw_game(screen, client, camera_x, camera_y, show_radius)
                clock.tick(30)
            client.stop()
            running = False
        clock.tick(30)

    pygame.quit()

if __name__ == "__main__":
    main()