"""
Build web_catalog.json from the numbered media files.
Reads notes.json for per-file descriptions/locations/overrides.
Uses EXIF DateTimeOriginal (JPEG) and ffprobe creation_time (MP4),
both converted to UTC, as the authoritative sort key.
"""
import json, os, re, glob, subprocess
from pathlib import Path
from datetime import datetime, timezone, timedelta

try:
    from PIL import Image
    from PIL.ExifTags import TAGS as PIL_TAGS
    HAS_PIL = True
except ImportError:
    HAS_PIL = False

# ── Route points ──────────────────────────────────────────────────────────────
if not os.path.exists("route_pts.json"):
    raise SystemExit("Run extract_route.py first to generate route_pts.json")

with open("route_pts.json", encoding="utf-8") as f:
    route_pts = json.load(f)

def _parse_iso(s):
    s = s.strip()
    s = re.sub(r'(\d)(Z)$', r'\1+00:00', s)
    try:
        return datetime.fromisoformat(s)
    except Exception:
        return None

route_times = [_parse_iso(p["time"]) for p in route_pts]

def nearest_gps(ts):
    if not route_pts or ts is None:
        return None, None
    best_i, best_d = 0, float("inf")
    for i, rt in enumerate(route_times):
        if rt is None:
            continue
        ts_cmp = ts.replace(tzinfo=timezone.utc) if ts.tzinfo is None else ts
        rt_cmp = rt.replace(tzinfo=timezone.utc) if rt.tzinfo is None else rt
        d = abs((ts_cmp - rt_cmp).total_seconds())
        if d < best_d:
            best_d, best_i = d, i
    return route_pts[best_i]["lat"], route_pts[best_i]["lon"]

# ── Notes ─────────────────────────────────────────────────────────────────────
notes = {}
if os.path.exists("notes.json"):
    with open("notes.json", encoding="utf-8") as f:
        notes = json.load(f)

# ── Timezone estimation from GPS ──────────────────────────────────────────────
def tz_offset_hours(lat, lon):
    """Estimate summer UTC offset from GPS coordinates.
    Uses > comparisons: larger (less negative) lon = further east.
    Handles Arizona (no DST, MST = UTC-7) and Navajo Nation (MDT = UTC-6).
    """
    if lon is None:
        return -4  # EDT default
    if lon > -87.0:
        return -4  # EDT: VA, eastern TN
    if lon > -104.0:
        return -5  # CDT: western TN, AR, OK, TX Panhandle
    if lon > -109.0:
        return -6  # MDT: NM (and western TX/CO edge)
    # West of -109: AZ, UT, NV, CA
    # Arizona (non-Navajo) uses MST (UTC-7, no DST). Navajo Nation (lat > ~36.5 in AZ
    # longitude band) observes MDT (UTC-6). Utah is MDT. NV/CA are PDT (UTC-7).
    if lat is not None and 31 <= lat <= 36.5 and lon > -114.8:
        return -7  # AZ MST (non-Navajo portion)
    if lat is not None and 36.5 < lat <= 42 and -114.5 < lon:
        return -6  # Navajo Nation AZ + Utah MDT
    return -7  # PDT: NV, CA

# ── EXIF helpers ──────────────────────────────────────────────────────────────
_tag_to_id = None

def _tag_id(name):
    global _tag_to_id
    if _tag_to_id is None and HAS_PIL:
        _tag_to_id = {v: k for k, v in PIL_TAGS.items()}
    return (_tag_to_id or {}).get(name, 0)

def jpeg_utc(path, lat, lon):
    """Return UTC datetime from EXIF DateTimeOriginal, or None."""
    if not HAS_PIL:
        return None
    try:
        img = Image.open(path)
        exif = img._getexif() or {}
        dto = exif.get(_tag_id('DateTimeOriginal'), '')
        if not dto:
            return None
        dt = datetime.strptime(str(dto), "%Y:%m:%d %H:%M:%S")
        offset = timedelta(hours=tz_offset_hours(lat, lon))
        return (dt - offset).replace(tzinfo=timezone.utc)
    except Exception:
        return None

def mp4_info(path):
    """Return (creation_time UTC, lat, lon) from MP4 metadata."""
    try:
        out = subprocess.check_output(
            ['ffprobe', '-v', 'quiet', '-print_format', 'json', '-show_format', path],
            stderr=subprocess.DEVNULL
        ).decode()
        tags = json.loads(out).get('format', {}).get('tags', {})

        ct = None
        ct_str = tags.get('creation_time', '')
        if ct_str:
            ct_str = ct_str.rstrip('Z').split('.')[0]
            ct = datetime.strptime(ct_str, "%Y-%m-%dT%H:%M:%S").replace(tzinfo=timezone.utc)

        lat = lon = None
        loc = tags.get('location', '')
        if loc:
            nums = re.findall(r'[+-][\d.]+', loc)
            if len(nums) >= 2:
                lat, lon = float(nums[0]), float(nums[1])

        return ct, lat, lon
    except Exception:
        return None, None, None

# ── Day from UTC ──────────────────────────────────────────────────────────────
def day_from_utc(utc_dt, tz_off):
    if utc_dt is None:
        return None
    local = utc_dt + timedelta(hours=tz_off)
    if local.hour < 6:
        local -= timedelta(days=1)
    return local.strftime("%Y-%m-%d")

# ── Main loop ─────────────────────────────────────────────────────────────────
media = sorted(glob.glob("[0-9][0-9][0-9].jpg") + glob.glob("[0-9][0-9][0-9].mp4"))
catalog = []

for src in media:
    stem     = Path(src).stem
    ext      = Path(src).suffix.lower()
    is_video = ext == ".mp4"
    note     = notes.get(stem, {})

    # GPS: notes.json overrides; MP4s also pull from embedded metadata
    note_lat = note.get("lat") or None
    note_lon = note.get("lon") or None

    if is_video:
        ct_utc, mp4_lat, mp4_lon = mp4_info(src)
        lat = note_lat if note_lat is not None else mp4_lat
        lon = note_lon if note_lon is not None else mp4_lon
        sort_utc = ct_utc
    else:
        lat = note_lat
        lon = note_lon
        sort_utc = jpeg_utc(src, lat, lon)

    # notes.json sort_ts override (e.g. when re-encoding strips creation_time)
    note_sort_ts = note.get("sort_ts", "")
    if note_sort_ts:
        try:
            sort_utc = datetime.strptime(note_sort_ts.rstrip("Z"), "%Y-%m-%dT%H:%M:%S").replace(tzinfo=timezone.utc)
        except Exception:
            pass

    # Fallback: mtime (last resort, may be inaccurate)
    if sort_utc is None:
        mtime = datetime.fromtimestamp(os.stat(src).st_mtime)
        sort_utc = mtime.replace(tzinfo=timezone.utc)

    sort_ts = sort_utc.strftime("%Y-%m-%dT%H:%M:%SZ")

    # Display timestamp in local time
    tz_off   = tz_offset_hours(lat, lon)
    local_dt = sort_utc + timedelta(hours=tz_off)
    ts_str   = local_dt.strftime("%Y-%m-%dT%H:%M:%S")

    day = note.get("day") or day_from_utc(sort_utc, tz_off) or ""

    # GPS fallback to nearest route point
    if not lat or not lon:
        lat, lon = nearest_gps(sort_utc)

    catalog.append({
        "src":         src,
        "filename":    src,
        "timestamp":   ts_str,
        "sort_ts":     sort_ts,
        "day":         day,
        "location":    note.get("location", ""),
        "description": note.get("description", ""),
        "now_playing": note.get("now_playing", ""),
        "is_video":    is_video,
        "lat":         lat,
        "lon":         lon,
    })

catalog.sort(key=lambda e: e["sort_ts"])

with open("web_catalog.json", "w", encoding="utf-8") as f:
    json.dump(catalog, f, indent=2)

print(f"Wrote web_catalog.json ({len(catalog)} entries)")
