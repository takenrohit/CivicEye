"""Geographic helpers using great-circle (haversine) distance, not degree Euclidean distance."""
import math

EARTH_RADIUS_M = 6_371_008.8  # mean Earth radius


def haversine_m(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp = p2 - p1
    dl = math.radians(lon2 - lon1)
    h = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * EARTH_RADIUS_M * math.asin(math.sqrt(h))


def bounding_box(lat: float, lon: float, radius_m: float):
    """Coarse lat/lon box used only to pre-filter rows before exact haversine checks."""
    dlat = math.degrees(radius_m / EARTH_RADIUS_M)
    dlon = math.degrees(radius_m / (EARTH_RADIUS_M * max(math.cos(math.radians(lat)), 1e-6)))
    return lat - dlat, lat + dlat, lon - dlon, lon + dlon


def valid_coordinates(lat, lon) -> bool:
    try:
        lat, lon = float(lat), float(lon)
    except (TypeError, ValueError):
        return False
    return -90 <= lat <= 90 and -180 <= lon <= 180 and math.isfinite(lat) and math.isfinite(lon)


def approximate(lat: float, lon: float, decimals: int = 3) -> tuple[float, float]:
    """Round to ~100 m for privacy-preserving public display."""
    return round(lat, decimals), round(lon, decimals)
