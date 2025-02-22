import json
from datetime import datetime

# Файлы баз данных
PLAYER_DATA_FILE = "player_data.json"
GAMES_FILE = "games.json"
TOP_DATA_FILE = "data.json"

def load_player_data():
    try:
        with open(PLAYER_DATA_FILE, "r") as f:
            return json.load(f)
    except FileNotFoundError:
        return {}

def save_player_data(data):
    with open(PLAYER_DATA_FILE, "w") as f:
        json.dump(data, f, indent=4, ensure_ascii=False)

def add_user(user_id, data, vk_name=None):
    if str(user_id) not in data:
        if vk_name is None:
            vk_name = f"Пользователь {user_id}"
        data[str(user_id)] = {
            "balance": 0,
            "start_date": str(datetime.now().date()),
            "last_bonus": None,
            "clicks": [],
            "name": vk_name
        }

def update_user_name(user_id, new_name, data):
    if str(user_id) in data:
        data[str(user_id)]["name"] = new_name
        save_player_data(data)

def add_click_to_data(user_id, message, data):
    if str(user_id) in data:
        click_info = {
            "message": message,
            "timestamp": str(datetime.now())
        }
        data[str(user_id)]["clicks"].append(click_info)
        save_player_data(data)

# Работа с играми. В файле games.json хранятся активные игры.
def load_games():
    try:
        with open(GAMES_FILE, "r") as f:
            return json.load(f)
    except FileNotFoundError:
        return {}

def save_games(games):
    with open(GAMES_FILE, "w") as f:
        json.dump(games, f, indent=4, ensure_ascii=False)

def add_game(game_info):
    games = load_games()
    games[str(game_info["user_id"])] = game_info
    save_games(games)

def remove_game(user_id):
    games = load_games()
    key = str(user_id)
    if key in games:
        del games[key]
    save_games(games)

# Работа с топ данными (балансов и кликов)
def load_top_data():
    try:
        with open(TOP_DATA_FILE, "r") as f:
            return json.load(f)
    except FileNotFoundError:
        return {"top_balances": {}, "top_miners": {}}

def save_top_data(top_data):
    with open(TOP_DATA_FILE, "w") as f:
        json.dump(top_data, f, indent=4, ensure_ascii=False)