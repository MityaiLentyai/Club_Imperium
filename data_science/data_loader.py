
from pathlib import Path

import geopandas as gpd
import pandas as pd


PROJECT_ROOT = Path(__file__).resolve().parent.parent
STOPS_PATH = PROJECT_ROOT / "data" / "stops_clean.csv"


def load_stops():
    df = pd.read_csv(
        STOPS_PATH,
        dtype={
            "stop_id": str,
            "platform": str,
            "street_id": str,
        }
    )

    required_columns = {
        "stop_id",
        "platform",
        "stop_name",
        "latitude",
        "longitude",
    }

    missing = required_columns - set(df.columns)

    if missing:
        raise ValueError(
            f"Missing columns: {sorted(missing)}"
        )

    df["latitude"] = pd.to_numeric(
        df["latitude"], errors="coerce"
    )
    df["longitude"] = pd.to_numeric(
        df["longitude"], errors="coerce"
    )

    df = df.dropna(
        subset=["latitude", "longitude"]
    )

    df = df.drop_duplicates(
        subset=["stop_id", "platform"]
    )

    gdf = gpd.GeoDataFrame(
        df,
        geometry=gpd.points_from_xy(
            df["longitude"],
            df["latitude"],
        ),
        crs="EPSG:4326"
    )

    return gdf.to_crs("EPSG:2180")
