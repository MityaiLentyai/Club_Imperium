from starlette.concurrency import run_in_threadpool
"""Two-home comparison with explicit opt-in for external routing."""
from backend.schemas import AddressScoreRequest, RoutePoint
from backend.services.geocoding_service import geocode_address
from backend.services.routing_service import get_commute
from backend.services.scoring_service import get_location_score
from data_science.comparison import compare_results


async def get_comparison(request):
    results = []
    for location in request.locations:
        resolved = await geocode_address(location.address) if isinstance(location, AddressScoreRequest) else {
            "latitude": location.latitude, "longitude": location.longitude}
        result = await run_in_threadpool(get_location_score, resolved["latitude"], resolved["longitude"], location.radius_m, weights=request.weights)
        if "address" in resolved:
            result["location"]["address"] = resolved["address"]
        if request.destination is not None:
            result["commute"] = await get_commute(RoutePoint(**result["location"]), request.destination,
                                                  include_routes=request.include_routes)
        results.append(result)
    return {"locations": results, "comparisons": compare_results(results),
            "warnings": [
                "Advantages compare measured values only, not comprehensive residential quality.",
                "Park completeness is unverified; parking and sports cover limited listed facilities.",
                "LifeScore is partial while Mobility is the only eligible numeric score.",
                "Route durations are provider estimates; transit journeys are unavailable.",
            ]}
