import json
import random
import logging
from vk_api.keyboard import VkKeyboard, VkKeyboardColor
from data_manager import save_player_data

# Global dictionary to track ongoing Mines sessions
mines_sessions = {}

def start_mines(user_id, stake, player_data, vk, peer_id):
    logging.debug(f"start_mines: user {user_id} initiating Mines game with stake {stake}.")
    # Deduct the stake from player's account
    player_data[str(user_id)]["balance"] -= stake
    logging.debug(f"start_mines: Deducted stake. New balance of user {user_id}: {player_data[str(user_id)]['balance']}")
    
    # Create a new game session in the global dictionary
    mines_sessions[str(user_id)] = {"stake": stake, "state": "choose_field"}
    logging.debug(f"start_mines: Created session for user {user_id} -> {mines_sessions[str(user_id)]}")

    # Build and send an inline keyboard with options for board sizes
    keyboard = VkKeyboard(inline=True)
    board_sizes = [4, 5, 6]
    for index, size in enumerate(board_sizes):
        keyboard.add_callback_button(f"{size}x{size}", color=VkKeyboardColor.PRIMARY,
                                     payload={"command": "mines_field", "size": size})
        if index != len(board_sizes) - 1:
            keyboard.add_line()
    vk.messages.send(
        peer_id=peer_id,
        message=f"Ставка {stake} принята. Выберите размер игрового поля:",
        keyboard=keyboard.get_keyboard(),
        random_id=random.randint(1, 1000)
    )
    logging.debug("start_mines: Board size keyboard sent.")

def process_mines_field(event, user_id, size, player_data, vk, peer_id):
    logging.debug(f"process_mines_field: Received callback with size={size} for user {user_id}")
    try:
        size = int(size)
    except ValueError:
        vk.messages.send(
            peer_id=peer_id,
            message="Ошибка: некорректный размер поля.",
            random_id=random.randint(1, 1000)
        )
        return

    # Answer the callback to clear the loading indicator
    vk.messages.sendMessageEventAnswer(
        event_id=event.obj.event_id,
        user_id=user_id,
        peer_id=peer_id,
        event_data=json.dumps({"type": "show_snackbar", "text": f"Размер {size}x{size} выбран"})
    )

    session = mines_sessions.get(str(user_id))
    if not session or session.get("state") != "choose_field":
        vk.messages.send(
            peer_id=peer_id,
            message="Сессия игры не найдена. Пожалуйста, начните игру снова.",
            random_id=random.randint(1, 1000)
        )
        logging.error(f"process_mines_field: Session not found or invalid state for user {user_id}")
        return

    session["board_size"] = size
    session["state"] = "choose_option"
    logging.debug(f"process_mines_field: Updated session for user {user_id}: {session}")

    # Send an inline keyboard for game option: default with 2 mines, or custom mine count
    keyboard = VkKeyboard(inline=True)
    keyboard.add_callback_button("Начать с 2 минами", color=VkKeyboardColor.PRIMARY,
                                 payload={"command": "mines_option", "option": "default"})
    keyboard.add_callback_button("Выбрать количество мин", color=VkKeyboardColor.SECONDARY,
                                 payload={"command": "mines_option", "option": "custom"})
    vk.messages.send(
        peer_id=peer_id,
        message=f"Вы выбрали поле {size}x{size}. Выберите опцию:",
        keyboard=keyboard.get_keyboard(),
        random_id=random.randint(1, 1000)
    )
    logging.debug("process_mines_field: Option keyboard sent.")

def process_mines_option(event, user_id, option, player_data, vk, peer_id):
    logging.debug(f"process_mines_option: User {user_id} selected option {option}")
    vk.messages.sendMessageEventAnswer(
        event_id=event.obj.event_id,
        user_id=user_id,
        peer_id=peer_id,
        event_data=json.dumps({"type": "show_snackbar", "text": "Опция выбрана"})
    )

    session = mines_sessions.get(str(user_id))
    if not session or session.get("state") != "choose_option":
        vk.messages.send(
            peer_id=peer_id,
            message="Сессия игры не найдена. Пожалуйста, начните игру снова.",
            random_id=random.randint(1, 1000)
        )
        logging.error(f"process_mines_option: Session not found or invalid state for user {user_id}")
        return

    board_size = session["board_size"]
    total_cells = board_size * board_size

    if option == "default":
        mine_count = 2
        if total_cells - mine_count < 1:
            vk.messages.send(
                peer_id=peer_id,
                message="Невозможно разместить столько мин на поле.",
                random_id=random.randint(1, 1000)
            )
            logging.error(f"process_mines_option: Invalid mine count for board size {board_size}")
            return
        session["mine_count"] = mine_count
        session["state"] = "choose_cell"
        grid, grid_hash = generate_mines_grid(board_size, mine_count)
        session["grid"] = grid
        session["grid_hash"] = grid_hash
        vk.messages.send(
            peer_id=peer_id,
            message=f"Игра началась с {board_size}x{board_size} и {mine_count} минами.\nПоле:\n{format_grid(board_size)}\nВведите номер ячейки (от 1 до {total_cells}):",
            random_id=random.randint(1, 1000)
        )
    elif option == "custom":
        session["state"] = "choose_mine_count"
        vk.messages.send(
            peer_id=peer_id,
            message=f"Введите количество мин (от 1 до {total_cells - 1}):",
            random_id=random.randint(1, 1000)
        )
    else:
        vk.messages.send(
            peer_id=peer_id,
            message="Неверная опция.",
            random_id=random.randint(1, 1000)
        )
    logging.debug(f"process_mines_option: Updated session for user {user_id}: {session}")

def process_mines_text(user_id, text, player_data, vk, peer_id):
    logging.debug(f"process_mines_text: received text='{text}' for user {user_id}")
    session = mines_sessions.get(str(user_id))
    if not session:
        logging.debug(f"process_mines_text: no session found for user {user_id}")
        return False

    state = session.get("state")
    board_size = session.get("board_size")
    total_cells = board_size * board_size if board_size else 0
    logging.debug(f"process_mines_text: user {user_id} state {state} with text '{text}'")

    if state == "choose_mine_count":
        try:
            mine_count = int(text)
        except ValueError:
            vk.messages.send(
                peer_id=peer_id,
                message="Введите корректное число для количества мин.",
                random_id=random.randint(1, 1000)
            )
            return True

        if mine_count < 1 or mine_count >= total_cells:
            vk.messages.send(
                peer_id=peer_id,
                message=f"Количество мин должно быть от 1 до {total_cells - 1}.",
                random_id=random.randint(1, 1000)
            )
            return True
        
        session["mine_count"] = mine_count
        session["state"] = "choose_cell"
        grid, grid_hash = generate_mines_grid(board_size, mine_count)
        session["grid"] = grid
        session["grid_hash"] = grid_hash
        vk.messages.send(
            peer_id=peer_id,
            message=f"Игра началась с {board_size}x{board_size} и {mine_count} минами.\nПоле:\n{format_grid(board_size)}\nВведите номер ячейки (от 1 до {total_cells}):",
            random_id=random.randint(1, 1000)
        )
        return True

    elif state == "choose_cell":
        try:
            cell_number = int(text)
            logging.debug(f"process_mines_text: Parsed cell_number {cell_number} for user {user_id}")
        except ValueError:
            vk.messages.send(
                peer_id=peer_id,
                message="Введите корректный номер ячейки.",
                random_id=random.randint(1, 1000)
            )
            return True

        if cell_number < 1 or cell_number > total_cells:
            vk.messages.send(
                peer_id=peer_id,
                message=f"Номер ячейки должен быть от 1 до {total_cells}.",
                random_id=random.randint(1, 1000)
            )
            return True

        row = (cell_number - 1) // board_size
        col = (cell_number - 1) % board_size
        grid = session.get("grid")
        grid_hash = session.get("grid_hash")
        
        # End the Mines session after processing the move
        del mines_sessions[str(user_id)]
        logging.debug(f"process_mines_text: Ending session for user {user_id}")

        if grid[row][col] == 'M':
            outcome = f"Вы проиграли. Вы попали на мину. Ваш баланс: {player_data[str(user_id)]['balance']} Glitch⚡."
        else:
            winnings = session["stake"] * 2
            player_data[str(user_id)]["balance"] += winnings
            outcome = f"Поздравляем! Вы выиграли {winnings}. Ваш баланс: {player_data[str(user_id)]['balance']} Glitch⚡."
        
        vk.messages.send(
            peer_id=peer_id,
            message=(f"{outcome}\nХеш игрового поля: {grid_hash}\nПроверка честности: {''.join([''.join(r) for r in grid])}"),
            random_id=random.randint(1, 1000)
        )
        save_player_data(player_data)
        return True

    else:
        logging.debug(f"process_mines_text: Unhandled state {state} for user {user_id}")
        return False

def generate_mines_grid(board_size, mine_count):
    grid = [['0' for _ in range(board_size)] for _ in range(board_size)]
    placed = 0
    while placed < mine_count:
        r = random.randint(0, board_size - 1)
        c = random.randint(0, board_size - 1)
        if grid[r][c] != 'M':
            grid[r][c] = 'M'
            placed += 1
    grid_hash = ''.join([''.join(row) for row in grid])
    return grid, grid_hash

def format_grid(board_size):
    lines = []
    number = 1
    for _ in range(board_size):
        row_cells = []
        for _ in range(board_size):
            row_cells.append(f"[{number}]")
            number += 1
        lines.append(" ".join(row_cells))
    return "\n".join(lines)

# For backward compatibility with handlers.py
process_mines_choice = process_mines_text