import pygame
import asyncio
import websockets
import json
import threading
import sys
import time
import os

WIDTH, HEIGHT = 1000, 700
BG_COLOR = (30, 30, 40)
BUTTON_COLOR = (70, 70, 90)
BUTTON_HOVER = (100, 100, 120)
TEXT_COLOR = (255, 255, 255)
LABEL_COLOR = (200, 200, 200)
VALUE_COLOR = (255, 255, 0)
INPUT_BOX_COLOR = (100, 100, 120)
INPUT_ACTIVE_COLOR = (200, 200, 250)

WORLD_SIZE = 100000
CITY_CENTER = WORLD_SIZE // 2
CITY_RADIUS = 500
SAFE_ZONE_RADIUS = CITY_RADIUS

BASE_MOVE_STEP = 4
MAX_MOVE_STEP = 20

CHAR_WINDOW_WIDTH = 640
CHAR_WINDOW_HEIGHT = 480

def resource_path(relative_path):
    try:
        base_path = sys._MEIPASS
    except Exception:
        base_path = os.path.abspath(".")
    return os.path.join(base_path, relative_path)

def calculate_move_step(speed_stat):
    step = BASE_MOVE_STEP + (speed_stat - 5) // 5
    return max(1, min(MAX_MOVE_STEP, step))

# ------------------------------------------------------------
# Экран логина
# ------------------------------------------------------------
class LoginScreen:
    def __init__(self, screen):
        self.screen = screen
        self.username = ""
        self.password = ""
        self.active_field = None
        self.username_rect = pygame.Rect(WIDTH//2 - 150, 200, 300, 40)
        self.password_rect = pygame.Rect(WIDTH//2 - 150, 270, 300, 40)
        self.login_btn = pygame.Rect(WIDTH//2 - 100, 350, 90, 40)
        self.register_btn = pygame.Rect(WIDTH//2 + 10, 350, 90, 40)
        self.font = pygame.font.SysFont("Arial", 24)
        self.small_font = pygame.font.SysFont("Arial", 18)
        self.error_msg = ""

    def handle_event(self, event):
        if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
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
        for field, rect in [("username", self.username_rect), ("password", self.password_rect)]:
            color = INPUT_ACTIVE_COLOR if self.active_field == field else INPUT_BOX_COLOR
            pygame.draw.rect(self.screen, color, rect, 2)
            value = getattr(self, field)
            text = self.font.render("*"*len(value) if field=="password" else value, True, TEXT_COLOR)
            self.screen.blit(text, (rect.x + 5, rect.y + 5))
            label = self.small_font.render(field.capitalize(), True, LABEL_COLOR)
            self.screen.blit(label, (rect.x, rect.y - 20))
        pygame.draw.rect(self.screen, BUTTON_COLOR, self.login_btn)
        pygame.draw.rect(self.screen, BUTTON_COLOR, self.register_btn)
        login_text = self.font.render("Login", True, TEXT_COLOR)
        reg_text = self.font.render("Register", True, TEXT_COLOR)
        self.screen.blit(login_text, (self.login_btn.x + 15, self.login_btn.y + 10))
        self.screen.blit(reg_text, (self.register_btn.x + 8, self.register_btn.y + 10))
        if self.error_msg:
            error_text = self.small_font.render(self.error_msg, True, (255, 100, 100))
            self.screen.blit(error_text, (WIDTH//2 - error_text.get_width()//2, 310))
        pygame.display.flip()

# ------------------------------------------------------------
# Конструктор персонажа
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
        self.input_boxes = {
            "username": pygame.Rect(WIDTH//2 - 150, 45, 300, 35),
            "password": pygame.Rect(WIDTH//2 - 150, 100, 300, 35)
        }
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
        for field, rect in self.input_boxes.items():
            color = INPUT_ACTIVE_COLOR if self.active_field == field else INPUT_BOX_COLOR
            pygame.draw.rect(self.screen, color, rect, 2)
            val = getattr(self, field)
            display = "*"*len(val) if field == "password" else val
            text = self.small_font.render(display, True, TEXT_COLOR)
            self.screen.blit(text, (rect.x + 5, rect.y + 5))
            label = self.small_font.render(field.capitalize(), True, LABEL_COLOR)
            self.screen.blit(label, (rect.x, rect.y - 18))
        class_rect = pygame.Rect(WIDTH//2 - 80, 145, 160, 30)
        pygame.draw.rect(self.screen, (80,80,100), class_rect)
        class_text = self.font.render(self.class_display, True, TEXT_COLOR)
        self.screen.blit(class_text, (class_rect.x + 10, class_rect.y + 3))
        left_arrow = pygame.Rect(class_rect.x - 25, class_rect.y, 20, 30)
        right_arrow = pygame.Rect(class_rect.x + class_rect.width + 5, class_rect.y, 20, 30)
        pygame.draw.polygon(self.screen, (200,200,200), [(left_arrow.x+12, left_arrow.y+5), (left_arrow.x+2, left_arrow.y+15), (left_arrow.x+12, left_arrow.y+25)])
        pygame.draw.polygon(self.screen, (200,200,200), [(right_arrow.x+8, right_arrow.y+5), (right_arrow.x+18, right_arrow.y+15), (right_arrow.x+8, right_arrow.y+25)])
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
        pts_text = self.small_font.render(f"Points left: {self.remaining_points}", True, TEXT_COLOR)
        self.screen.blit(pts_text, (WIDTH//2 - 60, HEIGHT - 120))
        pygame.draw.rect(self.screen, (0,150,0) if self.remaining_points==0 else BUTTON_COLOR, self.create_button)
        create_txt = self.font.render("CREATE", True, TEXT_COLOR)
        self.screen.blit(create_txt, (self.create_button.x + 60, self.create_button.y + 10))
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
            for field, rect in self.input_boxes.items():
                if rect.collidepoint(event.pos):
                    self.active_field = field
                    break
            else:
                self.active_field = None
            class_rect = pygame.Rect(WIDTH//2 - 80, 145, 160, 30)
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
            for stat, rects in self.stat_buttons.items():
                if rects["minus"].collidepoint(event.pos) and self.base[stat] > 5:
                    self.base[stat] -= 1
                    self.remaining_points += 1
                if rects["plus"].collidepoint(event.pos) and self.remaining_points > 0:
                    self.base[stat] += 1
                    self.remaining_points -= 1
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
# Окно персонажа
# ------------------------------------------------------------
class CharacterWindow:
    def __init__(self, screen, client):
        self.screen = screen
        self.client = client
        self.visible = False
        self.active_tab = 0
        self.tab_names = ["Inventory", "Stats", "Quests", "Equipment", "Skills", "Spells"]
        self.font = pygame.font.SysFont("Arial", 20)
        self.small_font = pygame.font.SysFont("Arial", 16)
        self.rect = pygame.Rect((WIDTH - CHAR_WINDOW_WIDTH)//2,
                                (HEIGHT - CHAR_WINDOW_HEIGHT)//2,
                                CHAR_WINDOW_WIDTH, CHAR_WINDOW_HEIGHT)
        self.context_menu = None
        self.context_font = pygame.font.SysFont("Arial", 18)

    def toggle(self):
        self.visible = not self.visible
        if self.visible:
            asyncio.run_coroutine_threadsafe(self.client.request_inventory(), self.client.loop)

    def handle_event(self, event):
        if not self.visible:
            return
        if event.type == pygame.KEYDOWN and event.key == pygame.K_ESCAPE:
            self.visible = False
            self.context_menu = None
        if event.type == pygame.MOUSEBUTTONDOWN:
            if event.button == 1:  # ЛКМ
                if self.context_menu:
                    self.handle_context_click(event.pos)
                    return
                tab_width = self.rect.width // len(self.tab_names)
                for i, name in enumerate(self.tab_names):
                    tab_rect = pygame.Rect(self.rect.x + i*tab_width, self.rect.y, tab_width, 30)
                    if tab_rect.collidepoint(event.pos):
                        self.active_tab = i
                        self.context_menu = None
                        break
                if self.active_tab == 0:
                    self.handle_inventory_click(event.pos)
            elif event.button == 3:  # ПКМ
                if self.active_tab == 0:
                    self.open_context_menu(event.pos)

    def handle_inventory_click(self, pos):
        inv = getattr(self.client, 'inventory', [])
        y_start = self.rect.y + 50
        index = (pos[1] - y_start) // 25
        if 0 <= index < len(inv):
            item = inv[index]
            if item['slot'] != 'none':
                asyncio.run_coroutine_threadsafe(self.client.equip_item(item['id'], item['slot']), self.client.loop)

    def open_context_menu(self, pos):
        inv = getattr(self.client, 'inventory', [])
        y_start = self.rect.y + 50
        index = (pos[1] - y_start) // 25
        if 0 <= index < len(inv):
            item = inv[index]
            self.context_menu = {
                'item': item,
                'pos': pos,
                'options': ['Use', 'Drop', 'Destroy']
            }
        else:
            self.context_menu = None

    def handle_context_click(self, pos):
        if not self.context_menu:
            return
        menu_x, menu_y = self.context_menu['pos']
        menu_width = 120
        menu_height = len(self.context_menu['options']) * 25
        if menu_x <= pos[0] <= menu_x + menu_width and menu_y <= pos[1] <= menu_y + menu_height:
            option_index = (pos[1] - menu_y) // 25
            if 0 <= option_index < len(self.context_menu['options']):
                option = self.context_menu['options'][option_index]
                item = self.context_menu['item']
                self.handle_item_action(item, option)
        self.context_menu = None

    def handle_item_action(self, item, action):
        print(f"Item action: {action} on {item['name']}")
        if action == "Use":
            asyncio.run_coroutine_threadsafe(self.client.use_item(item['id']), self.client.loop)
        elif action == "Drop":
            asyncio.run_coroutine_threadsafe(self.client.drop_item(item['id']), self.client.loop)
        elif action == "Destroy":
            asyncio.run_coroutine_threadsafe(self.client.destroy_item(item['id']), self.client.loop)

    def draw(self):
        if not self.visible:
            return
        overlay = pygame.Surface((WIDTH, HEIGHT), pygame.SRCALPHA)
        overlay.fill((0, 0, 0, 180))
        self.screen.blit(overlay, (0, 0))
        pygame.draw.rect(self.screen, (50,50,70), self.rect)
        pygame.draw.rect(self.screen, (100,100,120), self.rect, 3)
        tab_width = self.rect.width // len(self.tab_names)
        for i, name in enumerate(self.tab_names):
            tab_rect = pygame.Rect(self.rect.x + i*tab_width, self.rect.y, tab_width, 30)
            color = (80,80,100) if i == self.active_tab else (60,60,80)
            pygame.draw.rect(self.screen, color, tab_rect)
            pygame.draw.rect(self.screen, (120,120,140), tab_rect, 1)
            text = self.font.render(name, True, (255,255,255))
            text_rect = text.get_rect(center=tab_rect.center)
            self.screen.blit(text, text_rect)
        content_rect = pygame.Rect(self.rect.x + 10, self.rect.y + 40,
                                   self.rect.width - 20, self.rect.height - 50)
        if self.active_tab == 0:
            self._draw_inventory(content_rect)
        elif self.active_tab == 1:
            self._draw_stats(content_rect)
        elif self.active_tab == 2:
            self._draw_quests(content_rect)
        elif self.active_tab == 3:
            self._draw_equipment(content_rect)
        elif self.active_tab == 4:
            self._draw_skills(content_rect)
        elif self.active_tab == 5:
            self._draw_spells(content_rect)

    def _draw_inventory(self, rect):
        inv = getattr(self.client, 'inventory', [])
        y = rect.y + 10
        for item in inv:
            text = self.small_font.render(f"{item['name']} x{item['quantity']}", True, (255,255,255))
            self.screen.blit(text, (rect.x + 10, y))
            if item['slot'] != 'none':
                eq_text = self.small_font.render("[Equip]", True, (200,200,0))
                self.screen.blit(eq_text, (rect.x + 200, y))
            y += 25
        if not inv:
            text = self.small_font.render("Inventory empty", True, (200,200,200))
            self.screen.blit(text, (rect.x + 10, rect.y + 10))
        if self.context_menu:
            menu = self.context_menu
            x, y = menu['pos']
            options = menu['options']
            mw = 120
            mh = len(options) * 25
            pygame.draw.rect(self.screen, (50,50,70), (x, y, mw, mh))
            pygame.draw.rect(self.screen, (100,100,120), (x, y, mw, mh), 2)
            for i, opt in enumerate(options):
                opt_text = self.context_font.render(opt, True, (255,255,255))
                self.screen.blit(opt_text, (x + 5, y + i*25 + 4))

    def _draw_stats(self, rect):
        stats = getattr(self.client, 'my_stats', {})
        y = rect.y + 10
        for stat, value in stats.items():
            text = self.small_font.render(f"{stat.upper()}: {value}", True, (255,255,0))
            self.screen.blit(text, (rect.x + 10, y))
            y += 25
        if not stats:
            text = self.small_font.render("No stats available", True, (200,200,200))
            self.screen.blit(text, (rect.x + 10, rect.y + 10))

    def _draw_quests(self, rect):
        text = self.small_font.render("Quests will be here", True, (200,200,200))
        self.screen.blit(text, (rect.x + 10, rect.y + 10))

    def _draw_equipment(self, rect):
        equip = getattr(self.client, 'equipment', {})
        y = rect.y + 10
        slots = ["weapon", "head", "chest", "legs", "feet"]
        for slot in slots:
            item = equip.get(slot)
            if item:
                text = self.small_font.render(f"{slot.capitalize()}: {item['name']}", True, (200,255,200))
            else:
                text = self.small_font.render(f"{slot.capitalize()}: empty", True, (150,150,150))
            self.screen.blit(text, (rect.x + 10, y))
            y += 25

    def _draw_skills(self, rect):
        text = self.small_font.render("Skills will be here", True, (200,200,200))
        self.screen.blit(text, (rect.x + 10, rect.y + 10))

    def _draw_spells(self, rect):
        text = self.small_font.render("Spells will be here", True, (200,200,200))
        self.screen.blit(text, (rect.x + 10, rect.y + 10))

# ------------------------------------------------------------
# Игровой клиент
# ------------------------------------------------------------
class MMOClient:
    def __init__(self, uri, username, password):
        self.uri = uri
        self.username = username
        self.password = password
        self.players = {}
        self.mobs = {}
        self.lock = threading.Lock()
        self.my_id = None
        self.my_class = None
        self.my_level = 1
        self.my_exp = 0
        self.my_hp = 0
        self.my_max_hp = 0
        self.exp_needed = 100
        self.speed_stat = 5
        self.move_step = BASE_MOVE_STEP
        self.my_stats = {}
        self.inventory = []
        self.equipment = {}
        self.running = True
        self.ws = None
        self.loop = None
        self.font = pygame.font.SysFont("Arial", 20)
        self.small_font = pygame.font.SysFont("Arial", 14)
        self.sprite_size = 32
        self.sprites = {}
        self.animations = {}
        self.animation_frame = 0
        self.animation_timer = 0
        self.anim_speed = 0.15
        self.last_direction = "down"
        self.is_moving = False
        self.load_sprites()
        self.load_animations()

    def load_sprites(self):
        surf = pygame.Surface((self.sprite_size, self.sprite_size), pygame.SRCALPHA)
        pygame.draw.circle(surf, (255,0,0), (self.sprite_size//2, self.sprite_size//2), self.sprite_size//2)
        self.sprites['other'] = surf
        for mob_type in ["slime", "goblin"]:
            surf = pygame.Surface((self.sprite_size, self.sprite_size), pygame.SRCALPHA)
            color = (0,150,0) if mob_type == "slime" else (139,69,19)
            pygame.draw.rect(surf, color, (0,0,self.sprite_size,self.sprite_size))
            self.sprites[mob_type] = surf

    def load_animations(self):
        dirs = ["down", "up", "left", "right"]
        size = self.sprite_size
        for direction in dirs:
            frames = []
            for frame in range(2):
                surf = pygame.Surface((size, size), pygame.SRCALPHA)
                pygame.draw.circle(surf, (0,255,0), (size//2, size//2), size//2 - 2)
                if direction == "down":
                    pygame.draw.line(surf, (255,255,0), (size//2, size//2+5), (size//2, size//2-10), 3)
                elif direction == "up":
                    pygame.draw.line(surf, (255,255,0), (size//2, size//2-5), (size//2, size//2+10), 3)
                elif direction == "left":
                    pygame.draw.line(surf, (255,255,0), (size//2-5, size//2), (size//2+10, size//2), 3)
                elif direction == "right":
                    pygame.draw.line(surf, (255,255,0), (size//2+5, size//2), (size//2-10, size//2), 3)
                frames.append(surf)
            self.animations[direction] = frames
        for direction in dirs:
            surf = pygame.Surface((size, size), pygame.SRCALPHA)
            pygame.draw.circle(surf, (0,255,0), (size//2, size//2), size//2 - 2)
            self.animations[f"idle_{direction}"] = [surf]

    def get_current_sprite(self):
        if self.is_moving:
            frames = self.animations.get(self.last_direction, [])
            if frames:
                return frames[int(self.animation_frame) % len(frames)]
        frames = self.animations.get(f"idle_{self.last_direction}", [])
        return frames[0] if frames else None

    def update_animation(self, dt):
        if self.is_moving:
            self.animation_timer += dt
            if self.animation_timer >= self.anim_speed:
                self.animation_timer = 0
                self.animation_frame += 1

    async def connect(self):
        self.ws = await websockets.connect(self.uri)
        await self.ws.send(json.dumps({"type": "auth", "username": self.username, "password": self.password}))
        msg = await self.ws.recv()
        data = json.loads(msg)
        if data["type"] == "init":
            self.my_id = data["data"]["player_id"]
            self.my_class = data["data"]["class"]
            self.my_level = data["data"]["level"]
            self.my_exp = data["data"]["exp"]
            self.my_hp = data["data"]["hp"]
            self.my_max_hp = data["data"]["max_hp"]
            self.exp_needed = 100 * self.my_level
            self.speed_stat = data["data"]["stats"]["spd"]
            self.move_step = calculate_move_step(self.speed_stat)
            self.my_stats = data["data"]["stats"]
            with self.lock:
                self.players[self.my_id] = (data["data"]["x"], data["data"]["y"], data["data"]["username"], data["data"]["class"])
            print(f"Init OK. My id: {self.my_id}, class: {self.my_class}, level: {self.my_level}, SPD: {self.speed_stat}, speed: {self.move_step}")
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

    async def request_inventory(self):
        await self.ws.send(json.dumps({"type": "get_inventory"}))

    async def equip_item(self, inv_id, slot):
        await self.ws.send(json.dumps({"type": "equip_item", "inv_id": inv_id, "slot": slot}))

    async def use_item(self, inv_id):
        await self.ws.send(json.dumps({"type": "use_item", "inv_id": inv_id}))

    async def drop_item(self, inv_id):
        await self.ws.send(json.dumps({"type": "drop_item", "inv_id": inv_id}))

    async def destroy_item(self, inv_id):
        await self.ws.send(json.dumps({"type": "destroy_item", "inv_id": inv_id}))

    async def receive_loop(self):
        try:
            async for msg in self.ws:
                data = json.loads(msg)
                t = data["type"]
                with self.lock:
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
                        self.my_hp = data["your_hp"]
                        print(f"Моб нанёс {data['damage']} урона, у вас {self.my_hp} HP")
                    elif t == "level_up":
                        if "exp" in data:
                            self.my_exp = data["exp"]
                        self.my_level = data["level"]
                        self.exp_needed = 100 * self.my_level
                        print(f"Поздравляем! Вы достигли {self.my_level} уровня! Опыт: {self.my_exp}")
                    elif t == "respawn":
                        self.my_hp = data["hp"]
                        if self.my_id in self.players:
                            x,y,name,cls = self.players[self.my_id]
                            self.players[self.my_id] = (data["x"], data["y"], name, cls)
                        print(f"Вы возродились в ({data['x']}, {data['y']}), HP={self.my_hp}")
                    elif t == "error":
                        print(f"Ошибка сервера: {data['message']}")
                    elif t == "exp_update":
                        self.my_exp = data["exp"]
                        self.my_level = data["level"]
                        self.exp_needed = 100 * self.my_level
                        print(f"Опыт: {self.my_exp}/{self.exp_needed}, уровень {self.my_level}")
                    elif t == "inventory_data":
                        self.inventory = data["inventory"]
                        self.equipment = data["equipment"]
                        print(f"Получен инвентарь: {len(self.inventory)} предметов")
                    elif t == "hp_update":
                        self.my_hp = data["hp"]
                    elif t == "item_action_result":
                        if data["success"]:
                            print(f"Item {data['action']} successful")
                            await self.request_inventory()
                        else:
                            print(f"Item {data['action']} failed")
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
        with self.lock:
            if self.my_id in self.players:
                return self.players[self.my_id][0], self.players[self.my_id][1]
        return None

    def set_my_position(self, x, y):
        with self.lock:
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
        with self.lock:
            for pid, (x, y, name, cls) in self.players.items():
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
# Отрисовка мира (без тайловой карты)
# ------------------------------------------------------------
def draw_game(screen, client, camera_x, camera_y, show_radius):
    # Простой фон
    screen.fill((60, 120, 60))

    # Безопасная зона (город)
    center_sx = CITY_CENTER - camera_x
    center_sy = CITY_CENTER - camera_y
    surf = pygame.Surface((CITY_RADIUS*2, CITY_RADIUS*2), pygame.SRCALPHA)
    pygame.draw.rect(surf, (100, 200, 255, 60), (0, 0, CITY_RADIUS*2, CITY_RADIUS*2))
    screen.blit(surf, (center_sx - CITY_RADIUS, center_sy - CITY_RADIUS))

    with client.lock:
        players_copy = client.players.copy()
        mobs_copy = client.mobs.copy()
        my_id = client.my_id
        my_level = client.my_level

    # Игроки
    for pid, (x, y, username, cls) in players_copy.items():
        sx = x - camera_x
        sy = y - camera_y
        if -50 < sx < WIDTH+50 and -50 < sy < HEIGHT+50:
            if pid == my_id:
                sprite = client.get_current_sprite()
            else:
                sprite = client.sprites.get('other')
            if sprite:
                screen.blit(sprite, (sx - client.sprite_size//2, sy - client.sprite_size//2))
            font = pygame.font.SysFont(None, 18)
            text = font.render(username, True, (255,255,255))
            screen.blit(text, (sx - text.get_width()//2, sy - client.sprite_size//2 - 5))
            if pid == my_id:
                lvl_text = font.render(f"Lv.{my_level}", True, (255,255,0))
                screen.blit(lvl_text, (sx - lvl_text.get_width()//2, sy - client.sprite_size//2 - 20))

    # Мобы
    for mob_id, mob in mobs_copy.items():
        sx = mob["x"] - camera_x
        sy = mob["y"] - camera_y
        if -50 < sx < WIDTH+50 and -50 < sy < HEIGHT+50:
            sprite = client.sprites.get(mob["type"], client.sprites.get('slime'))
            if sprite:
                screen.blit(sprite, (sx - client.sprite_size//2, sy - client.sprite_size//2))
            hp_percent = mob["hp"] / mob["max_hp"]
            bar_width = 40
            bar_height = 6
            bar_x = sx - bar_width//2
            bar_y = sy - client.sprite_size//2 - 8
            pygame.draw.rect(screen, (255,0,0), (bar_x, bar_y, bar_width, bar_height))
            pygame.draw.rect(screen, (0,255,0), (bar_x, bar_y, int(bar_width * hp_percent), bar_height))

    # Радиус атаки
    if show_radius and my_id in players_copy:
        my_pos = client.get_my_position()
        if my_pos:
            my_x, my_y = my_pos
            sx = my_x - camera_x
            sy = my_y - camera_y
            radius = client.get_attack_range()
            surf = pygame.Surface((radius*2, radius*2), pygame.SRCALPHA)
            color = (100,100,255,50) if radius > 100 else (255,100,100,50)
            pygame.draw.circle(surf, color, (radius, radius), radius)
            screen.blit(surf, (sx - radius, sy - radius))

    # HUD
    bar_width = 200
    bar_height = 20
    bar_x = 20
    bar_y = HEIGHT - 60
    hp_ratio = client.my_hp / client.my_max_hp
    pygame.draw.rect(screen, (100,0,0), (bar_x, bar_y, bar_width, bar_height))
    pygame.draw.rect(screen, (0,255,0), (bar_x, bar_y, int(bar_width * hp_ratio), bar_height))
    hp_text = client.font.render(f"HP: {client.my_hp}/{client.my_max_hp}", True, (255,255,255))
    screen.blit(hp_text, (bar_x, bar_y - 20))
    exp_ratio = min(1.0, client.my_exp / client.exp_needed) if client.exp_needed > 0 else 0
    exp_bar_y = bar_y - 40
    pygame.draw.rect(screen, (50,50,100), (bar_x, exp_bar_y, bar_width, 15))
    pygame.draw.rect(screen, (0,100,200), (bar_x, exp_bar_y, int(bar_width * exp_ratio), 15))
    exp_text = client.small_font.render(f"EXP: {client.my_exp}/{client.exp_needed}", True, (255,255,255))
    screen.blit(exp_text, (bar_x, exp_bar_y - 15))
    lvl_text = client.font.render(f"Level {client.my_level}", True, (255,255,0))
    screen.blit(lvl_text, (bar_x, bar_y - 80))
    pos = client.get_my_position()
    if pos:
        coord_font = pygame.font.SysFont(None, 24)
        coord_text = coord_font.render(f"Speed: {client.move_step}  (Ctrl - radius)", True, (255,255,255))
        screen.blit(coord_text, (10, 10))

# ------------------------------------------------------------
# Главный цикл
# ------------------------------------------------------------
def main():
    pygame.init()
    screen = pygame.display.set_mode((WIDTH, HEIGHT))
    pygame.display.set_caption("MMORPG Client")

    current_screen = "login"
    login = LoginScreen(screen)
    creator = None
    client = None
    char_window = None
    clock = pygame.time.Clock()
    running = True
    last_time = time.time()

    while running:
        dt = min(0.033, time.time() - last_time)
        last_time = time.time()

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
                        time.sleep(1)
                        if client.my_id is not None:
                            char_window = CharacterWindow(screen, client)
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
                            char_window = CharacterWindow(screen, client)
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
                        elif event.key == pygame.K_i:
                            char_window.toggle()
                        elif event.key in (pygame.K_LCTRL, pygame.K_RCTRL):
                            show_radius = not show_radius
                            print(f"Radius {'shown' if show_radius else 'hidden'}")
                        elif event.key == pygame.K_F11:
                            pygame.display.toggle_fullscreen()
                    char_window.handle_event(event)
                keys = pygame.key.get_pressed()
                dx = dy = 0
                if keys[pygame.K_a] or keys[pygame.K_LEFT]:
                    dx = -client.move_step
                if keys[pygame.K_d] or keys[pygame.K_RIGHT]:
                    dx = client.move_step
                if keys[pygame.K_w] or keys[pygame.K_UP]:
                    dy = -client.move_step
                if keys[pygame.K_s] or keys[pygame.K_DOWN]:
                    dy = client.move_step
                client.is_moving = (dx != 0 or dy != 0)
                if dx > 0:
                    client.last_direction = "right"
                elif dx < 0:
                    client.last_direction = "left"
                elif dy > 0:
                    client.last_direction = "down"
                elif dy < 0:
                    client.last_direction = "up"
                client.update_animation(dt)
                if dx != 0 or dy != 0:
                    pos = client.get_my_position()
                    if pos:
                        new_x = max(0, min(WORLD_SIZE, pos[0] + dx))
                        new_y = max(0, min(WORLD_SIZE, pos[1] + dy))
                        client.move(new_x, new_y)
                pos = client.get_my_position()
                if pos:
                    camera_x = pos[0] - WIDTH//2
                    camera_y = pos[1] - HEIGHT//2
                    camera_x = max(0, min(WORLD_SIZE - WIDTH, camera_x))
                    camera_y = max(0, min(WORLD_SIZE - HEIGHT, camera_y))
                draw_game(screen, client, camera_x, camera_y, show_radius)
                char_window.draw()
                pygame.display.flip()
                clock.tick(30)
            client.stop()
            running = False
        clock.tick(30)

    pygame.quit()

if __name__ == "__main__":
    main()