from pymotyc import Collection
from os import environ
from database.models import *


class Database:
    __db__name__ = environ.get("DB_NAME", "stakan_test")
    coolers: Collection[Cooler]
    users: Collection[User]
    events: Collection[Event]
