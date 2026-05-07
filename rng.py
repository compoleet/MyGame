import secrets
import random

# Для криптостойкого непредсказуемого рандома (лут, приручение, криты)
secure_rng = secrets.SystemRandom()

# Для всего остального (например, выбор случайного направления моба) можно и обычный
fast_rng = random.Random()  # автоматический seed от времени

def get_chance(probability: float) -> bool:
    """Возвращает True с заданной вероятностью (0.0 - 1.0) используя безопасный RNG."""
    return secure_rng.random() < probability

def randint(a: int, b: int) -> int:
    """Безопасное целое случайное число."""
    return secure_rng.randint(a, b)

def choice(seq):
    """Безопасный случайный выбор элемента."""
    return secure_rng.choice(seq)