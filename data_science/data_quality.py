"""Offline coverage evidence and explicit score eligibility, never guessed scores."""
from datetime import datetime


def timestamp_range(values):
    valid = []
    for value in values:
        try:
            parsed = datetime.fromisoformat(value)
            if parsed.tzinfo is not None:
                valid.append((parsed, value))
        except (ValueError, TypeError):
            continue
    valid.sort(key=lambda pair: pair[0])
    return {"oldest_retrieved_at": valid[0][1] if valid else None,
            "latest_retrieved_at": valid[-1][1] if valid else None}


def score_eligibility(optional, transport_available=True):
    reasons = {
        "green": "Named park inventory has unverified completeness; proximity features do not justify a citywide Green Score",
        "sports": "Only a bounded sample of educational sports sites is located; broader sports coverage is unverified",
        "parking": "Participating operators cover only listed facilities; no calibrated Parking Score",
        "commute": "Route distance and provider duration estimates are not a calibrated residential-quality score",
    }
    result = {"mobility": {"eligible": transport_available, "reason": "Original validated stop-proximity and density formula" if transport_available else "Transport dataset is unavailable"}}
    for key, reason in reasons.items():
        if key in optional and optional[key] is None:
            reason = "Dataset unavailable; missing evidence cannot be scored"
        result[key] = {"eligible": False, "reason": reason}
    return result


def describe_data(stops, line_cache, optional):
    keys = set(zip(stops.stop_id, stops.platform)) if stops is not None else set()
    known = [r for key, r in line_cache.records.items() if key in keys and r["status"] == "success"]
    datasets = {
        "transport": {"status": "available" if stops is not None else "unavailable", "record_count": len(stops) if stops is not None else None,
                      "coverage": "Existing stop-platform snapshot; this is not a timetable", "retrieved_at": None},
        "lines": {"status": line_cache.status, "known_platforms": len(known), "total_platforms": len(keys),
                  "fraction": len(known) / len(keys) if keys else None,
                  "distinct_observed_lines": len({line for row in known for line in row["lines"]}) if known else None,
                  **timestamp_range(row["retrieved_at"] for row in known),
                  "coverage": "Observed line numbers at sampled platforms; neither a timetable nor live service availability"},
    }
    for category, data in optional.items():
        if data is None:
            datasets[category] = {"status": "unavailable", "record_count": None}
            continue
        metadata = data["metadata"]
        item = {**metadata, "status": "available", "record_count": len(data["records"])}
        if category == "sports":
            props = [row[0] for row in data["records"]]
            source_sites = metadata.get("source_sites")
            item.update(located_sites=len(props), located_fraction_of_source_sites=len(props) / source_sites if source_sites else None,
                        districts_with_located_sites=sorted({p["district"] for p in props if p.get("district")}),
                        coordinate_timestamp_count=sum(bool(p.get("coordinate_retrieved_at")) for p in props),
                        coordinate_freshness=timestamp_range(p.get("coordinate_retrieved_at") for p in props))
            dates = sorted({s["updated_at"] for p in props
                            for s in (p.get("schedules") if isinstance(p.get("schedules"), list) else [])
                            if isinstance(s, dict) and isinstance(s.get("updated_at"), str)})
            item["source_update_date_range"] = {"oldest": dates[0] if dates else None, "latest": dates[-1] if dates else None}
        datasets[category] = item
    return {"datasets": datasets, "score_eligibility": score_eligibility(optional, stops is not None),
            "external_requests": False, "freshness_note": "Retrieval times describe saved observations, not current availability. Unknown timestamps stay null."}
