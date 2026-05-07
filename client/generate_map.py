import json
import numpy as np
from noise import snoise2

def generate_smart_map(width=200, height=200, scale=20.0, octaves=6):
    tile_size = 32
    # 0: трава, 1: вода, 2: лес, 3: камень
    collision_tiles = [1, 2, 3] 
    data = []

    # Центр карты для безопасной зоны
    center_x, center_y = width // 2, height // 2
    safe_radius = 15 

    for y in range(height):
        row = []
        for x in range(width):
            # Проверка на безопасную зону (всегда трава)
            dist_to_center = ((x - center_x)**2 + (y - center_y)**2)**0.5
            if dist_to_center < safe_radius:
                row.append(0)
                continue

            # Генерируем шум (-1.0 до 1.0)
            noise_val = snoise2(x / scale, 
                                y / scale, 
                                octaves=octaves, 
                                persistence=0.5, 
                                lacunarity=2.0)

            # Распределяем тайлы по значениям шума
            if noise_val < -0.15:
                tile = 1  # Глубокая вода
            elif noise_val < 0.0:
                tile = 0  # Трава / Берег
            elif noise_val < 0.25:
                tile = 2  # Лес
            else:
                tile = 3  # Горы / Камни
            row.append(tile)
        data.append(row)

    map_data = {
        "width": width,
        "height": height,
        "tile_size": tile_size,
        "tileset": "tileset.png",
        "collision_tiles": collision_tiles,
        "data": data
    }

    with open("map.json", "w") as f:
        json.dump(map_data, f)
    print(f"Карта {width}x{height} успешно сгенерирована с использованием шума Перлина!")

if __name__ == "__main__":
    generate_smart_map()