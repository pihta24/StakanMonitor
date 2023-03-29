from pydantic import BaseModel


class Cooler(BaseModel):
    name: str
    empty_watter: bool = False
    empty_glass: bool = False
    sent_messages: list[list]
