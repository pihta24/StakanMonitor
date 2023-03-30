# noinspection PyPackageRequirements
from telebot.asyncio_handler_backends import BaseMiddleware, CancelUpdate

from database import Database
from database.models import User


class RegisterMiddleware(BaseMiddleware):
    def __init__(self):
        super().__init__()
        self.update_sensitive = False
        self.update_types = ['message']

    async def pre_process(self, message, data):
        try:
            user = await Database.users.find({"telegram_id": message.from_user.id})
            if not user:
                user = User(telegram_id=message.from_user.id, name=message.from_user.first_name)
                await Database.users.save(user)
        except Exception as e:
            print(e)
            return CancelUpdate()

    async def post_process(self, message, data, exception):
        pass
