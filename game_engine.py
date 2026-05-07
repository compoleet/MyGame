import random
from typing import Tuple

class CharacterStats:
    """Базовый класс для управления характеристиками персонажа."""
    def __init__(self):
        self.base_stats = {"str": 5, "spd": 5, "vit": 5, "int": 5, "cha": 5, "lck":5}
        self.bonus_stats = {"str": 0, "spd": 0, "vit": 0, "int": 0, "cha": 0, "lck":0}
        self.multipliers = {"str": 1.0, "spd": 1.0, "vit": 1.0, "int": 1.0, "cha": 1.0, "lck":1.0}

    def get_total_stat(self, stat_name: str) -> float:
        """Рассчитывает итоговое значение стата с учетом множителя."""
        return (self.base_stats[stat_name] + self.bonus_stats[stat_name]) * self.multipliers[stat_name]

    def calculate_health(self) -> int:
        """Расчет HP по формуле 100 + VIT*10 + max(0, VIT-50)*5."""
        vit_total = self.get_total_stat("vit")
        return int(100 + vit_total * 10 + max(0, vit_total - 50) * 5)

    def calculate_physical_damage(self, weapon_damage: int) -> int:
        """Расчет физического урона: сила*2 + урон оружия."""
        return int(self.get_total_stat("str") * 2 + weapon_damage)
    
    def calculate_damage_after_armor(self, damage: int, target_vit: int) -> int:
        """Получение урона после брони: если урон <= брони, урон = 1, иначе урон - броня."""
        if damage <= target_vit:
            return 1
        return damage - target_vit

    def calculate_critical_chance(self) -> float:
        """Расчет шанса крита от удачи."""
        luck_total = self.get_total_stat("lck")
        return 0.3+luck_total/100

class ShieldStats(CharacterStats):
    """Щитовик: VIT x1.5, STR x1.2"""
    def __init__(self):
        super().__init__()
        self.multipliers["vit"] = 1.5
        self.multipliers["str"] = 1.2

class MeleeStats(CharacterStats):  # Мечник
    def __init__(self):
        super().__init__()
        self.multipliers["str"] = 1.5
        self.multipliers["spd"] = 1.2

class WarriorStats(CharacterStats):  # Воин
    def __init__(self):
        super().__init__()
        self.multipliers["vit"] = 1.25
        self.multipliers["str"] = 1.25

class MageStats(CharacterStats):
    def __init__(self):
        super().__init__()
        self.multipliers["int"] = 1.5
        self.multipliers["lck"] = 1.2

class BufferStats(CharacterStats):
    def __init__(self):
        super().__init__()
        self.multipliers["cha"] = 1.5
        self.multipliers["int"] = 1.2

class ArcherStats(CharacterStats):
    def __init__(self):
        super().__init__()
        self.multipliers["spd"] = 1.4
        self.multipliers["str"] = 1.4

class TamerStats(CharacterStats):
    def __init__(self):
        super().__init__()
        self.multipliers["cha"] = 1.5
        self.multipliers["vit"] = 1.2

class AssassinStats(CharacterStats):
    def __init__(self):
        super().__init__()
        self.multipliers["spd"] = 1.4
        self.multipliers["str"] = 1.4
        self.multipliers["lck"] = 1.2   # добавим lck как второстепенный

class CrafterStats(CharacterStats):
    def __init__(self):
        super().__init__()
        self.multipliers["cha"] = 1.5
        self.multipliers["str"] = 1.2

# Фабрика
def create_stats_by_class(class_name: str) -> CharacterStats:
    mapping = {
        "shield": ShieldStats,
        "sword": MeleeStats,
        "warrior": WarriorStats,
        "mage": MageStats,
        "buffer": BufferStats,
        "archer": ArcherStats,
        "tamer": TamerStats,
        "assassin": AssassinStats,
        "crafter": CrafterStats,
    }
    return mapping[class_name]()