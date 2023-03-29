from pydantic import BaseModel


class User(BaseModel):
    telegram_id: int
    name: str
    send_notif: bool = False
    banned: bool = False
    admin: bool = False
    can_add_admin: bool = False
