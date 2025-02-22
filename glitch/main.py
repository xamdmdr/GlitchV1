import vk_api
import logging
from vk_api.bot_longpoll import VkBotLongPoll, VkBotEventType
from config import CONFIG
from data_manager import load_player_data
from handlers import handle_message, handle_callback

vk_session = vk_api.VkApi(token=CONFIG["TOKEN"])
vk = vk_session.get_api()

logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger()
logging.getLogger("urllib3").setLevel(logging.WARNING)

def main():
    player_data = load_player_data()
    longpoll = VkBotLongPoll(vk_session, CONFIG["GROUP_ID"])
    logger.debug("Бот запущен и ожидает сообщений...")
    for event in longpoll.listen():
        if event.type == VkBotEventType.MESSAGE_NEW:
            handle_message(event, player_data, vk)
        elif event.type == VkBotEventType.MESSAGE_EVENT:
            handle_callback(event, player_data, vk)

if __name__ == "__main__":
    main()