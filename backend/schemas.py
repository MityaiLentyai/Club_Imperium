
from pydantic import BaseModel, Field


class ScoreRequest(BaseModel):
    latitude: float = Field(ge=-90, le=90)
    longitude: float = Field(ge=-180, le=180)

class AddressScoreRequest(BaseModel):
    address: str = Field(min_length=3, max_length=300)