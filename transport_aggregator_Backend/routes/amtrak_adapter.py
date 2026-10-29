"""Adapter for your group's Amtrak_Data.py GTFS schedule search.

Download the official GTFS ZIP locally before invoking their gtfs-kit parser;
this avoids assuming that gtfs-kit accepts a web URL as a ZIP file path.
GTFS is timetable data, not bookable fares or seat availability.
"""
import os
from pathlib import Path
import tempfile
import time
from urllib.request import Request, urlopen
from zipfile import is_zipfile

from django.conf import settings
import Amtrak_Data as amtrak

OFFICIAL_GTFS_URL = "https://content.amtrak.com/content/gtfs/GTFS.zip"
CACHE_SECONDS = 24 * 60 * 60
MAX_FEED_BYTES = 75 * 1024 * 1024


def _cached_gtfs_zip():
    cache_dir = Path(settings.BASE_DIR) / "data_cache"
    cache_dir.mkdir(parents=True, exist_ok=True)
    cache_path = cache_dir / "amtrak_gtfs.zip"
    if cache_path.exists() and is_zipfile(cache_path) and time.time() - cache_path.stat().st_mtime < CACHE_SECONDS:
        return cache_path

    # Fixed official URL only. Never accept a URL from users (prevents SSRF).
    request = Request(OFFICIAL_GTFS_URL, headers={"User-Agent": "RouteWise-student-project/1.0"})
    tmp_path = None
    try:
        with urlopen(request, timeout=30) as response:
            with tempfile.NamedTemporaryFile(dir=cache_dir, suffix=".zip", delete=False) as tmp:
                tmp_path = Path(tmp.name)
                count = 0
                while True:
                    chunk = response.read(1024 * 1024)
                    if not chunk:
                        break
                    count += len(chunk)
                    if count > MAX_FEED_BYTES:
                        raise ValueError("Amtrak GTFS feed exceeded the configured size limit.")
                    tmp.write(chunk)
        if not is_zipfile(tmp_path):
            raise ValueError("The Amtrak endpoint did not return a valid GTFS ZIP.")
        os.replace(tmp_path, cache_path)
        return cache_path
    finally:
        if tmp_path is not None:
            tmp_path.unlink(missing_ok=True)


def search_amtrak(origin, destination, travel_date, adults=1):
    origin, destination = amtrak.check_station(origin), amtrak.check_station(destination)
    if origin == destination:
        raise ValueError("Choose different Amtrak stations.")
    gtfs_file = _cached_gtfs_zip()
    # The supplied search uses its module-level GTFS_URL. Change it to the
    # downloaded file path so gtfs-kit reads the local, cacheable ZIP.
    # All requests share this same fixed local path after the first download.
    amtrak.GTFS_URL = str(gtfs_file)
    result = amtrak.search_amtrak_gtfs(origin, destination, travel_date, limit=5)
    rows = result.get("Rides", [])
    if not isinstance(rows, list):
        raise ValueError("Unexpected Amtrak schedule response.")
    for row in rows:
        row["Method"]["Priority"] = 2  # Rail is mode priority 2.
        row["Method"]["Cost"] = None  # GTFS does not publish ticket prices.
    return rows
