# noinspection PyPackageRequirements
from telebot.async_telebot import AsyncTeleBot
# noinspection PyPackageRequirements
from telebot.asyncio_handler_backends import BaseMiddleware, CancelUpdate

from database import Database


class HandleBannedMiddleware(BaseMiddleware):
    def __init__(self, bot: AsyncTeleBot):
        super().__init__()
        self.update_sensitive = False
        self.update_types = ['message']
        self.__bot_instance = bot

    async def pre_process(self, message, data):
        try:
            user = await Database.users.find_one({"telegram_id": message.from_user.id})
            if user.banned:
                await self.__bot_instance.reply_to(message, "Вы находитесь в черном списке")
                return CancelUpdate()
        except Exception as e:
            print(e)
            return CancelUpdate()

    async def post_process(self, message, data, exception):
        pass
