from datetime import datetime

from pydantic import BaseModel


class Event(BaseModel):
    type: str
    from_id: int
    description: str
    created_at: datetime = datetime.now()
