from __future__ import annotations

import argparse
import collections
import concurrent.futures
import datetime as dt
import json
import math
from pathlib import Path

from PIL import Image


PHOTO_SUFFIXES = {".heic", ".jpg", ".jpeg"}
DATETIME_TAGS = (36867, 36868, 306)
GPS_TAG = 34853


def read_exif(path: Path) -> Image.Exif:
    # Apple writes the TIFF/EXIF item close to the start of HEIC and JPEG files.
    # Reading a bounded header avoids pulling several gigabytes of image data
    # out of iCloud merely to inspect a few kilobytes of metadata. It also
    # avoids asking Pillow to decode the image pixels.
    with path.open("rb") as handle:
        data = handle.read(512 * 1024)
    big = data.find(bytes.fromhex("4d4d002a"))
    little = data.find(bytes.fromhex("49492a00"))
    offsets = [offset for offset in (big, little) if offset >= 0]
    if not offsets:
        raise ValueError("HEIC file does not contain an embedded TIFF header")
    exif = Image.Exif()
    exif.load(data[min(offsets) :])
    return exif


def extract_photo(path: Path) -> tuple[str, dict | None]:
    try:
        exif = read_exif(path)
        taken = parse_datetime(exif)
        if not taken:
            return "missing_date", None
        item = {"path": str(path), "taken": taken, "lat": None, "lon": None}
        gps = parse_gps(exif)
        if gps:
            item["lat"], item["lon"] = gps
            return "ok", item
        return "missing_gps", item
    except Exception as exc:  # Individual iCloud placeholders must not abort a library scan.
        return type(exc).__name__, None


def parse_datetime(exif: Image.Exif) -> dt.datetime | None:
    nested = exif.get_ifd(34665) if exif.get(34665) else {}
    for tag in DATETIME_TAGS:
        raw = nested.get(tag) or exif.get(tag)
        if not raw:
            continue
        value = str(raw).strip().split("\x00", 1)[0]
        for pattern in ("%Y:%m:%d %H:%M:%S", "%Y-%m-%d %H:%M:%S"):
            try:
                return dt.datetime.strptime(value[:19], pattern)
            except ValueError:
                pass
    return None


def decimal_degrees(values, reference: str) -> float:
    degrees, minutes, seconds = (float(value) for value in values)
    result = degrees + minutes / 60 + seconds / 3600
    return -result if reference in {"S", "W"} else result


def parse_gps(exif: Image.Exif) -> tuple[float, float] | None:
    if not exif.get(GPS_TAG):
        return None
    gps = exif.get_ifd(GPS_TAG)
    if not all(key in gps for key in (1, 2, 3, 4)):
        return None
    return decimal_degrees(gps[2], gps[1]), decimal_degrees(gps[4], gps[3])


def haversine_km(a: tuple[float, float], b: tuple[float, float]) -> float:
    lat1, lon1 = map(math.radians, a)
    lat2, lon2 = map(math.radians, b)
    dlat, dlon = lat2 - lat1, lon2 - lon1
    value = math.sin(dlat / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin(dlon / 2) ** 2
    return 6371.0088 * 2 * math.asin(math.sqrt(value))


def point_in_ring(lon: float, lat: float, ring: list[list[float]]) -> bool:
    inside = False
    previous = ring[-1]
    for current in ring:
        x1, y1 = previous[:2]
        x2, y2 = current[:2]
        if (y1 > lat) != (y2 > lat):
            intersection = (x2 - x1) * (lat - y1) / (y2 - y1) + x1
            if lon < intersection:
                inside = not inside
        previous = current
    return inside


def point_in_geometry(lon: float, lat: float, geometry: dict) -> bool:
    coordinates = geometry.get("coordinates", [])
    polygons = [coordinates] if geometry.get("type") == "Polygon" else coordinates
    for polygon in polygons:
        if polygon and point_in_ring(lon, lat, polygon[0]):
            if not any(point_in_ring(lon, lat, hole) for hole in polygon[1:]):
                return True
    return False


def geometry_bbox(geometry: dict) -> tuple[float, float, float, float]:
    points = []

    def collect(value):
        if value and isinstance(value[0], (int, float)):
            points.append(value)
            return
        for child in value:
            collect(child)

    collect(geometry.get("coordinates", []))
    longitudes = [point[0] for point in points]
    latitudes = [point[1] for point in points]
    return min(longitudes), min(latitudes), max(longitudes), max(latitudes)


def load_boundaries(path: Path, property_keys: tuple[str, ...]) -> list[tuple[str, dict, tuple[float, float, float, float]]]:
    data = json.loads(path.read_text(encoding="utf-8"))
    result = []
    for feature in data["features"]:
        properties = feature.get("properties", {})
        label = next((str(properties[key]) for key in property_keys if properties.get(key)), "Unknown")
        geometry = feature["geometry"]
        result.append((label, geometry, geometry_bbox(geometry)))
    return result


def lookup_boundary(point: tuple[float, float], boundaries: list[tuple[str, dict, tuple[float, float, float, float]]]) -> str | None:
    lat, lon = point
    for label, geometry, (min_lon, min_lat, max_lon, max_lat) in boundaries:
        if not (min_lon <= lon <= max_lon and min_lat <= lat <= max_lat):
            continue
        if point_in_geometry(lon, lat, geometry):
            return label
    return None


def choose_home(points: list[dict]) -> tuple[float, float]:
    # A ~5 km cell is small enough to isolate the habitual home area while
    # tolerating normal GPS drift and nearby errands.
    cells: dict[tuple[float, float], list[tuple[float, float]]] = collections.defaultdict(list)
    for item in points:
        lat, lon = item["lat"], item["lon"]
        cells[(round(lat / 0.05) * 0.05, round(lon / 0.05) * 0.05)].append((lat, lon))
    dominant = max(cells.values(), key=len)
    return (
        sum(point[0] for point in dominant) / len(dominant),
        sum(point[1] for point in dominant) / len(dominant),
    )


def split_candidates(points: list[dict], home: tuple[float, float], home_radius_km: float) -> list[list[dict]]:
    away = [item for item in points if haversine_km((item["lat"], item["lon"]), home) > home_radius_km]
    home_dates = {
        item["taken"].date()
        for item in points
        if haversine_km((item["lat"], item["lon"]), home) <= home_radius_km
    }
    candidates: list[list[dict]] = []
    current: list[dict] = []
    for item in away:
        if current:
            gap = item["taken"] - current[-1]["taken"]
            intervening_home = any(
                current[-1]["taken"].date() < day < item["taken"].date()
                for day in home_dates
            )
            if gap > dt.timedelta(days=5) or (intervening_home and gap > dt.timedelta(hours=18)):
                candidates.append(current)
                current = []
        current.append(item)
    if current:
        candidates.append(current)
    return candidates


def sequential_stops(points: list[dict]) -> list[dict]:
    runs: list[dict] = []
    for item in points:
        label = item.get("admin") or item.get("country") or "Unknown"
        if runs and runs[-1]["label"] == label and item["taken"] - runs[-1]["end"] < dt.timedelta(days=3):
            runs[-1]["end"] = item["taken"]
            runs[-1]["gps_photos"] += 1
        else:
            runs.append({"label": label, "start": item["taken"], "end": item["taken"], "gps_photos": 1})
    return runs


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("photo_root", type=Path)
    parser.add_argument("--countries", type=Path, required=True)
    parser.add_argument("--admin", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--home-radius-km", type=float, default=80.0)
    args = parser.parse_args()

    countries = load_boundaries(args.countries, ("code", "ISO_A2", "name"))
    admin = load_boundaries(args.admin, ("name", "id", "code"))
    dated: list[dict] = []
    errors = collections.Counter()
    paths = [
        path
        for path in args.photo_root.rglob("*")
        if path.is_file() and path.suffix.lower() in PHOTO_SUFFIXES
    ]
    scanned = len(paths)
    with concurrent.futures.ThreadPoolExecutor(max_workers=12) as executor:
        for completed, (status, item) in enumerate(executor.map(extract_photo, paths), start=1):
            if item:
                dated.append(item)
            if status != "ok":
                errors[status] += 1
            if completed % 500 == 0:
                print(f"Scanned {completed} of {scanned} photos...", flush=True)

    gps_points = [item for item in dated if item["lat"] is not None]
    gps_points.sort(key=lambda item: item["taken"])
    home = choose_home(gps_points)
    for item in gps_points:
        point = (item["lat"], item["lon"])
        item["country"] = lookup_boundary(point, countries)
        item["admin"] = lookup_boundary(point, admin) if item["country"] in {"US", "CA"} else None

    raw_candidates = split_candidates(gps_points, home, args.home_radius_km)
    candidates = []
    for number, points in enumerate(raw_candidates, start=1):
        start, end = points[0]["taken"], points[-1]["taken"]
        # Count every dated photo captured during the candidate interval, not
        # only the GPS-bearing subset used to discover it.
        all_photo_count = sum(start <= item["taken"] <= end for item in dated)
        duration = end - start
        if len(points) < 3 or (duration < dt.timedelta(hours=2) and len(points) < 8):
            continue
        stops = sequential_stops(points)
        candidates.append(
            {
                "candidate": number,
                "start": start.isoformat(sep=" "),
                "end": end.isoformat(sep=" "),
                "all_photos": all_photo_count,
                "gps_photos": len(points),
                "centroid": [
                    round(sum(item["lat"] for item in points) / len(points), 6),
                    round(sum(item["lon"] for item in points) / len(points), 6),
                ],
                "stops": [
                    {
                        **stop,
                        "start": stop["start"].isoformat(sep=" "),
                        "end": stop["end"].isoformat(sep=" "),
                    }
                    for stop in stops
                ],
            }
        )

    payload = {
        "scanned": scanned,
        "dated": len(dated),
        "gps": len(gps_points),
        "errors": dict(errors),
        "home": [round(home[0], 6), round(home[1], 6)],
        "home_radius_km": args.home_radius_km,
        "candidates": candidates,
    }
    args.output.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    print(json.dumps({key: payload[key] for key in ("scanned", "dated", "gps", "errors", "home")}, indent=2))
    print(f"Candidates: {len(candidates)}")


if __name__ == "__main__":
    main()
