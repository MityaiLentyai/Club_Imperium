
from typing import Annotated
import math

from fastapi import HTTPException
from pydantic import BaseModel, Field, StringConstraints, model_validator


Address = Annotated[
    str, StringConstraints(strip_whitespace=True, min_length=3, max_length=300)
]


# Same conservative envelope used by geocoding. Includes outer neighborhoods;
# this is a supported service area, not an exact municipal boundary polygon.
WARSAW_LATITUDE_RANGE = (52.0, 52.4)
WARSAW_LONGITUDE_RANGE = (20.75, 21.3)


def validate_supported_coordinates(latitude: float, longitude: float):
    # HTTPException avoids including NaN/Infinity in validation error JSON,
    # which would itself fail JSON serialization for non-standard JSON input.
    if not (math.isfinite(latitude) and math.isfinite(longitude)):
        raise HTTPException(status_code=422, detail="Coordinates must be finite numbers")
    if not (
        WARSAW_LATITUDE_RANGE[0] <= latitude <= WARSAW_LATITUDE_RANGE[1]
        and WARSAW_LONGITUDE_RANGE[0] <= longitude <= WARSAW_LONGITUDE_RANGE[1]
    ):
        raise HTTPException(
            status_code=422,
            detail=(
                "Coordinates are outside the supported Warsaw service area "
                "(latitude 52.0–52.4, longitude 20.75–21.3)"
            ),
        )


class ScoreRequest(BaseModel):
    latitude: float = Field(description="Warsaw service latitude: 52.0–52.4")
    longitude: float = Field(description="Warsaw service longitude: 20.75–21.3")
    radius_m: int = Field(default=1000, ge=1, le=2000)

    @model_validator(mode="after")
    def validate_service_area(self):
        validate_supported_coordinates(self.latitude, self.longitude)
        return self

class AddressScoreRequest(BaseModel):
    address: Address
    radius_m: int = Field(default=1000, ge=1, le=2000)
