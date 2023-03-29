from pymotyc import Collection

from database.models import *


class Database:
    __db__name__ = "stakan_test"
    coolers: Collection[Cooler]
    users: Collection[User]
    events: Collection[Event]
