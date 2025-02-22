import json
import random
import logging
from vk_api.keyboard import VkKeyboard, VkKeyboardColor
from data_manager import load_player_data, save_player_data, add_click_to_data, update_user_name, add_user
from games.coinflip import show_games_keyboard, start_coinflip, process_coinflip_choice
from games.mines import start_mines, process_mines_field, process_mines_option, process_mines_text, process_mines_choice
from config import CONFIG
from utils import format_user_tag

# Dictionaries to track waiting states outside of game sessions
awaiting_name_change = {}
awaiting_bet = {}

def is_group_chat(peer_id):
    return peer_id >= 2000000000

def handle_message(event, player_data, vk):
    # Получаем и очищаем входящее сообщение
    raw_text = event.obj.message.get('text', '')
    message_text = raw_text.replace("\xa0", " ").replace("\u200b", "").replace("\uFEFF", "").strip()
    user_id = event.obj.message.get('from_id')
    peer_id = event.obj.message.get('peer_id')
    
    # Генерируем тег для пользователя
    tag = format_user_tag(user_id, player_data.get(str(user_id), {}))
    logging.debug(f"Получено сообщение от пользователя {user_id} {tag}: raw='{raw_text}' -> processed='{message_text}' (repr: {repr(message_text)})")
    
    # Обработка смены имени
    if str(user_id) in awaiting_name_change:
        if message_text.lower() == "отмена":
            vk.messages.send(
                peer_id=peer_id,
                message=f"{tag}\nСмена имени отменена.",
                random_id=random.randint(1, 1000)
            )
        else:
            update_user_name(user_id, message_text, player_data)
            vk.messages.send(
                peer_id=peer_id,
                message=f"{tag}\nИмя изменено на {message_text}.",
                random_id=random.randint(1, 1000)
            )
        del awaiting_name_change[str(user_id)]
        add_click_to_data(user_id, "change_name", player_data)
        return

    # Если ожидается ставка для игры
    if str(user_id) in awaiting_bet:
        try:
            logging.debug(f"Преобразование ставки для пользователя {user_id} {tag}: '{message_text}'")
            amount = int(message_text)
            game_type = awaiting_bet[str(user_id)]
            del awaiting_bet[str(user_id)]
            if game_type == "coinflip":
                start_coinflip(user_id, amount, player_data, vk, peer_id)
            elif game_type == "mines":
                start_mines(user_id, amount, player_data, vk, peer_id)
        except ValueError as e:
            logging.error(f"Ошибка преобразования ставки '{message_text}' для пользователя {user_id} {tag}: {e}")
            vk.messages.send(
                peer_id=peer_id,
                message=f"{tag}\nПожалуйста, введите корректную ставку.",
                random_id=random.randint(1, 1000)
            )
        return

    # Сообщения из группового чата
    if is_group_chat(peer_id):
        lower_text = message_text.lower()
        if lower_text == "начать":
            if bot_has_admin_permissions(peer_id, vk):
                start_games_in_chat(vk, peer_id)
            else:
                vk.messages.send(
                    peer_id=peer_id,
                    message=f"{tag}\nБот требует права администратора для управления чатом и запуска игр. Дайте боту админ-права.",
                    random_id=random.randint(1, 1000)
                )
            return
        elif lower_text == "игры":
            if bot_has_admin_permissions(peer_id, vk):
                start_games_in_chat(vk, peer_id)
            else:
                vk.messages.send(
                    peer_id=peer_id,
                    message=f"{tag}\nБот требует права администратора для запуска игр. Дайте боту админ-права.",
                    random_id=random.randint(1, 1000)
                )
            return
        elif lower_text not in ["игры", "бонус"]:
            return
    else:
        # Личные сообщения
        lower_text = message_text.lower()
        if lower_text in ["начать", "меню"]:
            start_game(user_id, player_data, vk, peer_id)
        elif lower_text == "клики":
            farm_clicks(user_id, player_data, vk, peer_id)
        elif lower_text == "баланс":
            show_balance(user_id, player_data, vk, peer_id)
        elif lower_text == "профиль":
            show_profile(user_id, player_data, vk, peer_id)
        elif lower_text == "топ балансов":
            show_top_balances(user_id, player_data, vk, peer_id)
        elif lower_text == "топ майнеров":
            show_top_miners(user_id, player_data, vk, peer_id)
        else:
            # Если есть активная сессия Мины, обрабатываем ввод номера ячейки или мин
            if process_mines_text(user_id, message_text, player_data, vk, peer_id):
                return
            else:
                return
    add_click_to_data(user_id, lower_text, player_data)

def start_game(user_id, player_data, vk, peer_id):
    if str(user_id) not in player_data:
        add_user(user_id, player_data)
    tag = format_user_tag(user_id, player_data.get(str(user_id), {}))
    keyboard = VkKeyboard(one_time=False)
    if not is_group_chat(peer_id):
        keyboard.add_callback_button("Glitch⚡", color=VkKeyboardColor.PRIMARY, payload={"command": "get_glitch"})
        keyboard.add_line()
        keyboard.add_callback_button("Играть🎰", color=VkKeyboardColor.PRIMARY, payload={"command": "игры"})
        keyboard.add_line()
        keyboard.add_callback_button("Профиль👤", color=VkKeyboardColor.SECONDARY, payload={"command": "профиль"})
        keyboard.add_callback_button("Рефка🤝", color=VkKeyboardColor.SECONDARY, payload={"command": "рефералка"})
        keyboard.add_line()
        keyboard.add_callback_button("Топ балансов💸", color=VkKeyboardColor.POSITIVE, payload={"command": "топ балансов"})
        keyboard.add_callback_button("Топ майнеров⛏️", color=VkKeyboardColor.POSITIVE, payload={"command": "топ майнеров"})
        menu_keyboard = keyboard.get_keyboard()
    else:
        menu_keyboard = None
    vk.messages.send(
        peer_id=peer_id,
        message=f"{tag}\nПривет! Я, возможно, биткоин, а возможно – хомяк. Фармить или нет – это твоё дело. Что ты хочешь сделать?\n\n"
                "В личных сообщениях доступно меню, а в игровом чате – только игры и бонус.",
        keyboard=menu_keyboard,
        random_id=random.randint(1, 1000)
    )
    logging.info(f"Пользователю {user_id} {tag} отправлено стартовое сообщение.")

def farm_clicks(user_id, player_data, vk, peer_id):
    if str(user_id) not in player_data:
        return
    earned_glitch = random.randint(5, 17)
    player_data[str(user_id)]["balance"] += earned_glitch
    save_player_data(player_data)
    tag = format_user_tag(user_id, player_data.get(str(user_id), {}))
    logging.info(f"Пользователь {user_id} {tag}: заработано {earned_glitch} Glitch⚡. Баланс: {player_data[str(user_id)]['balance']}")
    vk.messages.send(
        peer_id=peer_id,
        message=f"{tag}\nВы заработали {earned_glitch} Glitch⚡! Ваш баланс: {player_data[str(user_id)]['balance']} Glitch⚡.",
        random_id=random.randint(1, 1000)
    )

def show_balance(user_id, player_data, vk, peer_id):
    tag = format_user_tag(user_id, player_data.get(str(user_id), {}))
    if str(user_id) in player_data:
        balance = player_data[str(user_id)]["balance"]
        vk.messages.send(
            peer_id=peer_id,
            message=f"{tag}\nВаш баланс: {balance} Glitch⚡.",
            random_id=random.randint(1, 1000)
        )
    else:
        vk.messages.send(
            peer_id=peer_id,
            message=f"{tag}\nВы ещё не начали игру. Напишите 'начать', чтобы начать!",
            random_id=random.randint(1, 1000)
        )

def show_profile(user_id, player_data, vk, peer_id):
    tag = format_user_tag(user_id, player_data.get(str(user_id), {}))
    if str(user_id) in player_data:
        profile = (f"{tag}\nПрофиль:\nБаланс: {player_data[str(user_id)]['balance']} Glitch⚡\n"
                   f"Дата начала: {player_data[str(user_id)]['start_date']}\n"
                   f"Имя: {player_data[str(user_id)]['name']}\nНажмите [Сменить имя] для изменения.")
        keyboard = VkKeyboard(inline=True)
        keyboard.add_callback_button("Сменить имя", color=VkKeyboardColor.PRIMARY, payload={"command": "change_name"})
        menu = keyboard.get_keyboard()
        vk.messages.send(
            peer_id=peer_id,
            message=profile,
            keyboard=menu,
            random_id=random.randint(1, 1000)
        )
    else:
        vk.messages.send(
            peer_id=peer_id,
            message=f"{tag}\nВы ещё не начали игру. Напишите 'начать', чтобы начать!",
            random_id=random.randint(1, 1000)
        )

def show_top_balances(user_id, player_data, vk, peer_id):
    top = sorted(player_data.items(), key=lambda x: x[1].get("balance", 0), reverse=True)[:5]
    message = "Топ 5 балансов:\n"
    for i, (uid, data) in enumerate(top, 1):
        tag_user = f"[vk.com/id{uid}|{data.get('name', f'Пользователь {uid}')}]"
        message += f"{i}. {tag_user}: {data.get('balance', 0)} Glitch⚡\n"
    vk.messages.send(
        peer_id=peer_id,
        message=message,
        random_id=random.randint(1, 1000)
    )

def show_top_miners(user_id, player_data, vk, peer_id):
    message = "Топ майнеров пока не доступен, но скоро будет!"
    vk.messages.send(
        peer_id=peer_id,
        message=message,
        random_id=random.randint(1, 1000)
    )

def bot_has_admin_permissions(peer_id, vk):
    # Здесь должна быть логика проверки прав админа в чате.
    return True

def start_games_in_chat(vk, peer_id):
    keyboard = VkKeyboard(one_time=False)
    keyboard.add_callback_button("Орел-Решка", color=VkKeyboardColor.PRIMARY, payload={"command": "coinflip"})
    keyboard.add_callback_button("Мины", color=VkKeyboardColor.PRIMARY, payload={"command": "mines"})
    vk.messages.send(
        peer_id=peer_id,
        message="Выберите игру:",
        keyboard=keyboard.get_keyboard(),
        random_id=random.randint(1, 1000)
    )

def handle_callback(event, player_data, vk):
    user_id = event.obj.user_id
    payload = event.obj.payload
    peer_id = event.obj.peer_id
    command = payload.get("command")
    tag = format_user_tag(user_id, player_data.get(str(user_id), {}))
    
    if command == "get_glitch":
        farm_clicks(user_id, player_data, vk, peer_id)
        vk.messages.sendMessageEventAnswer(
            event_id=event.obj.event_id,
            user_id=user_id,
            peer_id=peer_id,
            event_data=json.dumps({"type": "show_snackbar", "text": f"{tag} Вы получили Glitch⚡!"})
        )
    elif command == "баланс":
        show_balance(user_id, player_data, vk, peer_id)
        vk.messages.sendMessageEventAnswer(
            event_id=event.obj.event_id,
            user_id=user_id,
            peer_id=peer_id,
            event_data=json.dumps({"type": "show_snackbar", "text": f"{tag} Ваш баланс!"})
        )
    elif command == "профиль":
        show_profile(user_id, player_data, vk, peer_id)
        vk.messages.sendMessageEventAnswer(
            event_id=event.obj.event_id,
            user_id=user_id,
            peer_id=peer_id,
            event_data=json.dumps({"type": "show_snackbar", "text": f"{tag} Ваш профиль!"})
        )
    elif command == "топ балансов":
        show_top_balances(user_id, player_data, vk, peer_id)
        vk.messages.sendMessageEventAnswer(
            event_id=event.obj.event_id,
            user_id=user_id,
            peer_id=peer_id,
            event_data=json.dumps({"type": "show_snackbar", "text": f"{tag} Топ балансов!"})
        )
    elif command == "топ майнеров":
        show_top_miners(user_id, player_data, vk, peer_id)
        vk.messages.sendMessageEventAnswer(
            event_id=event.obj.event_id,
            user_id=user_id,
            peer_id=peer_id,
            event_data=json.dumps({"type": "show_snackbar", "text": f"{tag} Топ майнеров!"})
        )
    elif command == "change_name":
        awaiting_name_change[str(user_id)] = True
        vk.messages.send(
            peer_id=peer_id,
            message=f"{tag}\nВведите новое имя или 'отмена' для отказа.",
            random_id=random.randint(1, 1000)
        )
        vk.messages.sendMessageEventAnswer(
            event_id=event.obj.event_id,
            user_id=user_id,
            peer_id=peer_id,
            event_data=json.dumps({"type": "show_snackbar", "text": "Смена имени"})
        )
    elif command == "coinflip":
        awaiting_bet[str(user_id)] = "coinflip"
        vk.messages.send(
            peer_id=peer_id,
            message=f"{tag}\nВведите вашу ставку для 'Орел-Решка':",
            random_id=random.randint(1, 1000)
        )
        vk.messages.sendMessageEventAnswer(
            event_id=event.obj.event_id,
            user_id=user_id,
            peer_id=peer_id,
            event_data=json.dumps({"type": "show_snackbar", "text": "Ставка для Орел-Решка"})
        )
    elif command == "mines":
        awaiting_bet[str(user_id)] = "mines"
        vk.messages.send(
            peer_id=peer_id,
            message=f"{tag}\nВведите вашу ставку для игры 'Мины':",
            random_id=random.randint(1, 1000)
        )
        vk.messages.sendMessageEventAnswer(
            event_id=event.obj.event_id,
            user_id=user_id,
            peer_id=peer_id,
            event_data=json.dumps({"type": "show_snackbar", "text": "Ставка для Мины"})
        )
    elif command == "mines_field":
        size = payload.get("size")
        from games.mines import process_mines_field
        process_mines_field(event, user_id, size, player_data, vk, peer_id)
    elif command == "mines_option":
        option = payload.get("option")
        from games.mines import process_mines_option
        process_mines_option(event, user_id, option, player_data, vk, peer_id)
    else:
        if process_coinflip_choice(user_id, payload, player_data, vk, peer_id):
            return
        elif process_mines_choice(user_id, payload, player_data, vk, peer_id):
            return
        else:
            logging.debug(f"handle_callback: Неизвестная команда {command} от пользователя {user_id} {tag}.")