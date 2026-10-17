
from typing import Annotated

from pydantic import BaseModel, Field, StringConstraints


Address = Annotated[
    str, StringConstraints(strip_whitespace=True, min_length=3, max_length=300)
]


class ScoreRequest(BaseModel):
    latitude: float = Field(ge=-90, le=90)
    longitude: float = Field(ge=-180, le=180)

class AddressScoreRequest(BaseModel):
    address: Address
