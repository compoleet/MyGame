# My MMO Game Prototype

Простой прототип MMORPG на Python с websockets, SQLAlchemy и Pygame.

## Установка и запуск

1. Клонируй репозиторий
2. Создай виртуальное окружение: `python -m venv venv`
3. Активируй: `venv\Scripts\activate` (Windows) или `source venv/bin/activate` (Linux/Mac)
4. Установи зависимости: `pip install -r requirements.txt`
5. Создай базу данных: `python setup_db.py`
6. Запусти сервер: `python server.py`
7. Запусти клиент: `python pygame_client_fixed.py`

## Команды
- Стрелки — движение
- Логин/пароль: test / 123 (или создай нового через register_client.py)

## Текущий функционал
- Регистрация и аутентификация
- Движение игроков в реальном времени
- Отображение других игроков на карте (Pygame)
- Боевая система (формулы урона, защиты, крита)
- База данных SQLite (SQLAlchemy)