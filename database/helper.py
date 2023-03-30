from os import environ

from pymotyc import Collection

from database.models import *


class Database:
    __db__name__ = environ.get("DB_NAME", "stakan_test")
    coolers: Collection[Cooler]
    users: Collection[User]
    events: Collection[Event]


def get_user_from_msg(message):
    return Database.users.find_one({
        "telegram_id": message.from_user.id
    }, inject_default_id=True)
