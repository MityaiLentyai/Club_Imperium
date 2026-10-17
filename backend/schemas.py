
from typing import Annotated, Literal
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


class PersonalizedRequest(BaseModel):
    weights: dict[Literal["mobility", "green", "parking", "sports", "commute"], float] | None = None

    @model_validator(mode="after")
    def validate_weights(self):
        if self.weights is not None and any(not math.isfinite(v) or not 0 <= v <= 100 for v in self.weights.values()):
            raise HTTPException(status_code=422, detail="Weights must be finite values between 0 and 100")
        return self


class ScoreRequest(PersonalizedRequest):
    latitude: float = Field(description="Warsaw service latitude: 52.0–52.4")
    longitude: float = Field(description="Warsaw service longitude: 20.75–21.3")
    radius_m: int = Field(default=1000, ge=1, le=2000)

    @model_validator(mode="after")
    def validate_service_area(self):
        validate_supported_coordinates(self.latitude, self.longitude)
        return self

class AddressScoreRequest(PersonalizedRequest):
    address: Address
    radius_m: int = Field(default=1000, ge=1, le=2000)


class RoutePoint(BaseModel):
    latitude: float
    longitude: float

    @model_validator(mode="after")
    def validate_coordinates(self):
        validate_supported_coordinates(self.latitude, self.longitude)
        return self


class CommuteRequest(BaseModel):
    origin: RoutePoint
    destination: RoutePoint


class ComparisonRequest(PersonalizedRequest):
    locations: list[ScoreRequest | AddressScoreRequest] = Field(min_length=2, max_length=2)
    destination: RoutePoint | None = None
    include_routes: bool = False

    @model_validator(mode="before")
    @classmethod
    def reject_ambiguous_locations(cls, values):
        if isinstance(values, dict) and isinstance(values.get("locations"), list):
            for location in values["locations"]:
                if isinstance(location, dict) and "address" in location and ("latitude" in location or "longitude" in location):
                    raise HTTPException(status_code=422, detail="Each location must use either an address or coordinates")
        return values

    @model_validator(mode="after")
    def validate_comparison(self):
        if any(location.weights is not None for location in self.locations):
            raise HTTPException(status_code=422, detail="Set shared comparison weights at the top level")
        if self.include_routes and self.destination is None:
            raise HTTPException(status_code=422, detail="A destination is required to compare routes")
        return self
