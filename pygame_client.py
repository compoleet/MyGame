import pygame
import asyncio
import websockets
import json
import threading
import sys

WIDTH, HEIGHT = 1000, 700
COLOR_SELF = (0, 255, 0)
COLOR_OTHER = (255, 0, 0)
COLOR_MOB = (139, 69, 19)   # коричневый
COLOR_BG = (30, 30, 30)
MOVE_STEP = 5

class MMOClient:
    def __init__(self, uri, username, password):
        self.uri = uri
        self.username = username
        self.password = password
        self.players = {}          # {player_id: (x, y, username, class)}
        self.mobs = {}             # {mob_id: {x, y, type, hp, max_hp}}
        self.my_id = None
        self.my_class = None
        self.running = True
        self.ws = None
        self.loop = None

    async def connect(self):
        self.ws = await websockets.connect(self.uri)
        await self.ws.send(json.dumps({
            "type": "auth",
            "username": self.username,
            "password": self.password
        }))
        msg = await self.ws.recv()
        data = json.loads(msg)
        if data["type"] == "init":
            self.my_id = data["data"]["player_id"]
            self.my_class = data["data"]["class"]
            self.players[self.my_id] = (
                data["data"]["x"],
                data["data"]["y"],
                data["data"]["username"],
                data["data"]["class"]
            )
            print(f"Init OK. My id: {self.my_id}, class: {self.my_class}")
            return True
        else:
            print("Auth failed")
            return False

    async def send_move(self, x, y):
        await self.ws.send(json.dumps({"type": "move", "x": x, "y": y}))

    async def send_attack(self, target_type, target_id):
        # target_type: "player" или "mob"
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
                        x, y, name, cls = self.players[pid]
                        self.players[pid] = (data["x"], data["y"], name, cls)
                elif t == "despawn":
                    pid = data["player_id"]
                    if pid in self.players:
                        del self.players[pid]
                elif t == "spawn_mob":
                    mob_id = data["mob_id"]
                    self.mobs[mob_id] = {
                        "x": data["x"], "y": data["y"],
                        "type": data["mob_type"], "hp": data["hp"], "max_hp": data["max_hp"]
                    }
                elif t == "move_mob":
                    mob_id = data["mob_id"]
                    if mob_id in self.mobs:
                        self.mobs[mob_id]["x"] = data["x"]
                        self.mobs[mob_id]["y"] = data["y"]
                elif t == "despawn_mob":
                    mob_id = data["mob_id"]
                    if mob_id in self.mobs:
                        del self.mobs[mob_id]
                elif t == "mob_attacked":
                    mob_id = data["mob_id"]
                    if mob_id in self.mobs:
                        self.mobs[mob_id]["hp"] = data["hp"]
                elif t == "attacked_by_mob":
                    print(f"Моб нанёс {data['damage']} урона, у вас {data['your_hp']} HP")
                elif t == "level_up":
                    print(f"Поздравляем! Вы достигли {data['level']} уровня!")
                elif t == "respawn":
                    if self.my_id in self.players:
                        x, y, name, cls = self.players[self.my_id]
                        self.players[self.my_id] = (data["x"], data["y"], name, cls)
                    print(f"Вы возродились в ({data['x']}, {data['y']}), HP={data['hp']}")
                elif t == "error":
                    print(f"Ошибка сервера: {data['message']}")
                elif t in ("attack_result", "attacked"):
                    pass  # можно игнорировать
                else:
                    print(f"Unknown message: {msg}")
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
        if self.my_class in ranged:
            return 150
        else:
            return 30

    def find_nearest_enemy(self):
        """Возвращает (target_type, target_id, distance) ближайшего врага (моба или игрока) в радиусе атаки."""
        my_x, my_y = self.get_my_position()
        if my_x is None:
            return None
        radius = self.get_attack_range()
        best = None
        best_dist = radius + 1
        # Среди других игроков
        for pid, (x, y, name, cls) in self.players.items():
            if pid == self.my_id:
                continue
            dist = abs(x - my_x) + abs(y - my_y)
            if dist <= radius and dist < best_dist:
                best_dist = dist
                best = ("player", pid)
        # Среди мобов
        for mob_id, mob in self.mobs.items():
            dist = abs(mob["x"] - my_x) + abs(mob["y"] - my_y)
            if dist <= radius and dist < best_dist:
                best_dist = dist
                best = ("mob", mob_id)
        if best:
            return best[0], best[1], best_dist
        return None

    async def attack_nearest_async(self):
        enemy = self.find_nearest_enemy()
        if enemy:
            target_type, target_id, dist = enemy
            await self.send_attack(target_type, target_id)
            print(f"Атака {target_type} {target_id} (дист. {dist})")
        else:
            print("Нет врагов в радиусе атаки")

    def attack_nearest(self):
        asyncio.run_coroutine_threadsafe(self.attack_nearest_async(), self.loop)

    def stop(self):
        self.running = False
        if self.loop:
            self.loop.call_soon_threadsafe(self.loop.stop)

def draw(screen, client, camera_x, camera_y, show_radius):
    screen.fill(COLOR_BG)
    # Отрисовка игроков
    for pid, (x, y, username, cls) in client.players.items():
        screen_x = x - camera_x
        screen_y = y - camera_y
        if -50 < screen_x < WIDTH+50 and -50 < screen_y < HEIGHT+50:
            color = COLOR_SELF if pid == client.my_id else COLOR_OTHER
            pygame.draw.circle(screen, color, (int(screen_x), int(screen_y)), 8)
            font = pygame.font.SysFont(None, 18)
            text = font.render(username, True, (255, 255, 255))
            screen.blit(text, (screen_x - text.get_width()//2, screen_y - 15))
    # Отрисовка мобов
    for mob_id, mob in client.mobs.items():
        screen_x = mob["x"] - camera_x
        screen_y = mob["y"] - camera_y
        if -50 < screen_x < WIDTH+50 and -50 < screen_y < HEIGHT+50:
            pygame.draw.rect(screen, COLOR_MOB, (int(screen_x)-8, int(screen_y)-8, 16, 16))
            hp_percent = mob["hp"] / mob["max_hp"]
            pygame.draw.rect(screen, (255,0,0), (int(screen_x)-12, int(screen_y)-12, 24, 4))
            pygame.draw.rect(screen, (0,255,0), (int(screen_x)-12, int(screen_y)-12, int(24 * hp_percent), 4))
    # Радиус атаки (если включен)
    if show_radius and client.my_id in client.players and client.my_class:
        my_x, my_y = client.get_my_position()
        if my_x is not None:
            screen_x = my_x - camera_x
            screen_y = my_y - camera_y
            radius = client.get_attack_range()
            s = pygame.Surface((radius*2, radius*2), pygame.SRCALPHA)
            if radius > 100:
                color = (100, 100, 255, 50)  # синий
            else:
                color = (255, 100, 100, 50)  # красный
            pygame.draw.circle(s, color, (radius, radius), radius)
            screen.blit(s, (screen_x - radius, screen_y - radius))
    # Координаты и подсказка
    pos = client.get_my_position()
    if pos:
        font = pygame.font.SysFont(None, 24)
        coord_text = font.render(f"X: {pos[0]} Y: {pos[1]}  (Ctrl - показать/скрыть радиус)", True, (255, 255, 255))
        screen.blit(coord_text, (10, 10))
    pygame.display.flip()

def main():
    print("=== MMO Client with WASD and Space Attack ===")
    username = input("Username: ")
    password = input("Password: ")
    uri = "ws://localhost:8765"

    client = MMOClient(uri, username, password)
    client.start()
    import time
    time.sleep(1)
    if client.my_id is None:
        print("Не удалось подключиться. Проверьте сервер.")
        return

    pygame.init()
    screen = pygame.display.set_mode((WIDTH, HEIGHT))
    pygame.display.set_caption(f"MMO Client - {username}")
    clock = pygame.time.Clock()

    camera_x = 0
    camera_y = 0
    show_radius = True   # видимость радиуса атаки
    running = True

    while running and client.running:
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                running = False
            elif event.type == pygame.KEYDOWN:
                if event.key == pygame.K_SPACE:
                    client.attack_nearest()
                elif event.key == pygame.K_LCTRL or event.key == pygame.K_RCTRL:
                    show_radius = not show_radius
                    print(f"Радиус атаки {'показан' if show_radius else 'скрыт'}")
        # Движение: WASD + стрелки
        keys = pygame.key.get_pressed()
        dx = dy = 0
        if keys[pygame.K_a] or keys[pygame.K_LEFT]:
            dx = -MOVE_STEP
        if keys[pygame.K_d] or keys[pygame.K_RIGHT]:
            dx = MOVE_STEP
        if keys[pygame.K_w] or keys[pygame.K_UP]:
            dy = -MOVE_STEP
        if keys[pygame.K_s] or keys[pygame.K_DOWN]:
            dy = MOVE_STEP
        if dx != 0 or dy != 0:
            pos = client.get_my_position()
            if pos:
                new_x = max(0, min(1000, pos[0] + dx))
                new_y = max(0, min(1000, pos[1] + dy))
                client.move(new_x, new_y)

        # Камера следует за игроком
        pos = client.get_my_position()
        if pos:
            camera_x = pos[0] - WIDTH // 2
            camera_y = pos[1] - HEIGHT // 2

        draw(screen, client, camera_x, camera_y, show_radius)
        clock.tick(30)

    client.stop()
    pygame.quit()

if __name__ == "__main__":
    main()