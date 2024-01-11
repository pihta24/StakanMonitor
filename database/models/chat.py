from pydantic import BaseModel


class Chat(BaseModel):
    chat_id: int
    send_notif: bool = False
