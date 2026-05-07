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
            self.players[self.my_id] = (
                data["data"]["x"],
                data["data"]["y"],
                data["data"]["username"],
                data["data"]["class"]
            )
            print(f"Init OK. My id: {self.my_id}")
            return True
        else:
            print("Auth failed")
            return False

    async def send_move(self, x, y):
        await self.ws.send(json.dumps({"type": "move", "x": x, "y": y}))

    async def send_attack_mob(self, mob_id):
        await self.ws.send(json.dumps({"type": "attack_mob", "mob_id": mob_id}))

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
                elif t in ("attack_result", "attacked"):
                    pass  # можно выводить при желании
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

    async def attack_mob_async(self, mob_id):
        await self.send_attack_mob(mob_id)

    def attack_mob(self, mob_id):
        asyncio.run_coroutine_threadsafe(self.attack_mob_async(mob_id), self.loop)

    def stop(self):
        self.running = False
        if self.loop:
            self.loop.call_soon_threadsafe(self.loop.stop)

def draw(screen, client, camera_x, camera_y):
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
            # Полоска HP
            hp_percent = mob["hp"] / mob["max_hp"]
            pygame.draw.rect(screen, (255,0,0), (int(screen_x)-12, int(screen_y)-12, 24, 4))
            pygame.draw.rect(screen, (0,255,0), (int(screen_x)-12, int(screen_y)-12, int(24 * hp_percent), 4))
    # Координаты своего игрока
    pos = client.get_my_position()
    if pos:
        font = pygame.font.SysFont(None, 24)
        coord_text = font.render(f"X: {pos[0]} Y: {pos[1]}", True, (255, 255, 255))
        screen.blit(coord_text, (10, 10))
    pygame.display.flip()

def main():
    print("=== MMO Client with Mobs ===")
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
    running = True

    while running and client.running:
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                running = False
            elif event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
                mx, my = pygame.mouse.get_pos()
                world_x = mx + camera_x
                world_y = my + camera_y
                # Поиск моба под курсором
                for mob_id, mob in client.mobs.items():
                    dx = mob["x"] - world_x
                    dy = mob["y"] - world_y
                    if abs(dx) < 20 and abs(dy) < 20:
                        client.attack_mob(mob_id)
                        break

        # Управление стрелками
        keys = pygame.key.get_pressed()
        dx = dy = 0
        if keys[pygame.K_LEFT]:
            dx = -MOVE_STEP
        if keys[pygame.K_RIGHT]:
            dx = MOVE_STEP
        if keys[pygame.K_UP]:
            dy = -MOVE_STEP
        if keys[pygame.K_DOWN]:
            dy = MOVE_STEP
        if dx != 0 or dy != 0:
            pos = client.get_my_position()
            if pos:
                new_x = pos[0] + dx
                new_y = pos[1] + dy
                new_x = max(0, min(1000, new_x))
                new_y = max(0, min(1000, new_y))
                client.move(new_x, new_y)

        # Камера следует за игроком
        pos = client.get_my_position()
        if pos:
            camera_x = pos[0] - WIDTH // 2
            camera_y = pos[1] - HEIGHT // 2

        draw(screen, client, camera_x, camera_y)
        clock.tick(30)

    client.stop()
    pygame.quit()

if __name__ == "__main__":
    main()