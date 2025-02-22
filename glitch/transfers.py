import re
import json
import random
import logging
from vk_api.keyboard import VkKeyboard, VkKeyboardColor
from data_manager import save_player_data, load_player_data, add_user

# Global dictionary for tracking ongoing transfer sessions
transfer_sessions = {}

def parse_recipient(text, event):
    """
    Parse recipient ID from the text or from a forwarded message.
    Accepted formats:
      - forwarded/ reply message (takes from first fwd message)
      - vk.com/id12345/username
      - /id12345/username
      - @username/id12345 (if numeric id is present)
    Returns recipient id as a string if found, else None.
    """
    # Check for forwarded message in event
    fwd_msgs = event.obj.message.get('fwd_messages', [])
    if fwd_msgs:
        recipient_id = fwd_msgs[0].get('from_id')
        if recipient_id:
            return str(recipient_id)
    # Check for vk.com/id12345 pattern
    match = re.search(r'vk\.com/id(\d+)', text)
    if match:
        return match.group(1)
    # Check for /id12345 pattern
    match = re.search(r'/id(\d+)', text)
    if match:
        return match.group(1)
    # Check for pattern id12345 in text
    match = re.search(r'\bid(\d+)\b', text)
    if match:
        return match.group(1)
    return None

def initiate_transfer(sender_id, event, vk):
    """
    Initiates a transfer session by asking the sender for the recipient.
    """
    transfer_sessions[str(sender_id)] = {"stage": "recipient", "sender_id": str(sender_id)}
    vk.messages.send(
        peer_id=event.obj.message.get('peer_id'),
        message="Введите ссылку или тег игрока, которому вы хотите перевести Glitch:",
        random_id=random.randint(1, 1000)
    )

def process_transfer(bot_event, sender_id, text, player_data, vk):
    """
    Processes incoming text for an ongoing transfer session.
    The stages are:
      1. Recipient - parse recipient from text.
      2. Amount - validate and store transfer amount.
      3. Confirmation - send confirmation with inline buttons.
    """
    session = transfer_sessions.get(str(sender_id))
    if not session:
        return False

    stage = session.get("stage")
    peer_id = bot_event.obj.message.get('peer_id')
    
    if stage == "recipient":
        recipient = parse_recipient(text, bot_event)
        if not recipient:
            vk.messages.send(
                peer_id=peer_id,
                message="Не удалось определить получателя. Попробуйте еще раз, отправив корректную ссылку/тег.",
                random_id=random.randint(1, 1000)
            )
            return True
        session["recipient"] = recipient
        session["stage"] = "amount"
        vk.messages.send(
            peer_id=peer_id,
            message="Введите сумму Glitch для перевода:",
            random_id=random.randint(1, 1000)
        )
        return True

    elif stage == "amount":
        try:
            amount = int(text)
            if amount <= 0:
                raise ValueError()
        except ValueError:
            vk.messages.send(
                peer_id=peer_id,
                message="Введите корректное число для суммы перевода.",
                random_id=random.randint(1, 1000)
            )
            return True
        # Check if sender has enough funds
        sender_balance = int(player_data.get(str(sender_id), {}).get("balance", 0))
        if sender_balance < amount:
            vk.messages.send(
                peer_id=peer_id,
                message="Недостаточно средств для перевода.",
                random_id=random.randint(1, 1000)
            )
            del transfer_sessions[str(sender_id)]
            return True
        session["amount"] = amount
        session["stage"] = "confirm"
        # Get sender tag and recipient tag; for simplicity we echo the ids.
        sender_tag = f"vk.com/id{sender_id}"
        recipient_tag = f"vk.com/id{session['recipient']}"
        # Build confirmation inline keyboard
        keyboard = VkKeyboard(inline=True)
        keyboard.add_callback_button("Подтвердить", color=VkKeyboardColor.POSITIVE,
                                     payload={"command": "transfer_confirm", "action": "confirm"})
        keyboard.add_callback_button("Отменить", color=VkKeyboardColor.NEGATIVE,
                                     payload={"command": "transfer_confirm", "action": "cancel"})
        confirmation_msg = (f"Пожалуйста, подтвердите, что вы ({sender_tag}) хотите перевести "
                            f"{amount} Glitch игроку ({recipient_tag}).")
        vk.messages.send(
            peer_id=peer_id,
            message=confirmation_msg,
            keyboard=keyboard.get_keyboard(),
            random_id=random.randint(1, 1000)
        )
        return True

    return False

def process_transfer_confirmation(sender_id, action, player_data, vk, peer_id):
    """
    Processes the confirmation callback for a transfer.
    If confirmed, subtracts amount from sender and adds it to recipient.
    If canceled, the session is cancelled.
    """
    session = transfer_sessions.get(str(sender_id))
    if not session or session.get("stage") != "confirm":
        vk.messages.send(
            peer_id=peer_id,
            message="Сессия перевода не найдена или уже завершена.",
            random_id=random.randint(1, 1000)
        )
        return

    if action == "cancel":
        vk.messages.send(
            peer_id=peer_id,
            message="Перевод отменён.",
            random_id=random.randint(1, 1000)
        )
        del transfer_sessions[str(sender_id)]
        return

    if action == "confirm":
        amount = session.get("amount")
        recipient = session.get("recipient")
        sender_balance = int(player_data.get(str(sender_id), {}).get("balance", 0))
        if sender_balance < amount:
            vk.messages.send(
                peer_id=peer_id,
                message="Недостаточно средств для перевода.",
                random_id=random.randint(1, 1000)
            )
            del transfer_sessions[str(sender_id)]
            return
        # Deduct funds from sender
        player_data[str(sender_id)]["balance"] -= amount
        # Add funds to recipient. Ensure recipient exists in the system.
        if str(recipient) not in player_data:
            # If recipient does not exist, create a default user.
            add_user(recipient, player_data, vk_name=f"Пользователь {recipient}")
        player_data[str(recipient)]["balance"] += amount
        save_player_data(player_data)
        vk.messages.send(
            peer_id=peer_id,
            message=(f"Перевод выполнен успешно! С вашего счета списано {amount} Glitch. "
                     f"Новый баланс: {player_data[str(sender_id)]['balance']} Glitch."),
            random_id=random.randint(1, 1000)
        )
        del transfer_sessions[str(sender_id)]
        return