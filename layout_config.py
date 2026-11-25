import os
import sys
import json

# Запущено ли приложение внутри exe, собранного PyInstaller
FROZEN = getattr(sys, "frozen", False)

if FROZEN:
    # В exe ресурсы (папка icons) лежат внутри папки приложения
    BASE_DIR = getattr(sys, "_MEIPASS", os.path.dirname(sys.executable))
    # Настройки храним в папке пользователя, туда можно писать без прав администратора
    DATA_DIR = os.path.join(
        os.environ.get("APPDATA", os.path.expanduser("~")), "Tap"
    )
else:
    BASE_DIR = os.path.dirname(os.path.abspath(__file__))
    DATA_DIR = BASE_DIR

os.makedirs(DATA_DIR, exist_ok=True)

ICONS_DIR = os.path.join(BASE_DIR, "icons")
LAYOUT_FILE = os.path.join(DATA_DIR, "layout.json")

# Рамки окон: x, y, ширина, высота
# Иконки приложений: x, y, размер
DEFAULTS = {
    "phone": [1588, 388, 288, 639],
    "tablet": [338, 77, 1252, 924],
    "phone_icon": [1601, 710, 50],
    "tablet_icon": [606, 273, 76],
}


def load_layout():
    data = {k: list(v) for k, v in DEFAULTS.items()}
    if os.path.exists(LAYOUT_FILE):
        try:
            with open(LAYOUT_FILE, "r", encoding="utf-8") as f:
                saved = json.load(f)
            for key, default in DEFAULTS.items():
                value = saved.get(key)
                if not isinstance(value, list):
                    continue
                numbers = [int(n) for n in value]
                # Если в файле меньше чисел, чем нужно, добираем из значений по умолчанию
                if len(numbers) < len(default):
                    numbers += default[len(numbers):]
                data[key] = numbers[:len(default)]
        except Exception as error:
            print("Не смог прочитать layout.json, беру значения по умолчанию:", error)
    return data


def save_layout(data):
    with open(LAYOUT_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)