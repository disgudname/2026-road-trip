"""
Extract GPS route points from Timeline.json for the Jun 16-24 2026 trip
and write timeline_trip.json in the same format as 2024.
"""
import json, re, sys
from datetime import datetime, timezone

TRIP_START = "2026-06-16"
TRIP_END   = "2026-06-25"

def parse_latlng(s):
    m = re.match(r'([-\d.]+)[°°],\s*([-\d.]+)[°°]', s)
    if m:
        return float(m.group(1)), float(m.group(2))
    return None

print("Loading Timeline.json...", flush=True)
with open("Timeline.json", encoding="utf-8") as f:
    data = json.load(f)

segments = data.get("semanticSegments", [])
print(f"Total segments: {len(segments)}", flush=True)

trip_segs = []
for seg in segments:
    st = seg.get("startTime", "")
    if not st:
        continue
    day = st[:10]
    if day < TRIP_START or day >= TRIP_END:
        continue
    trip_segs.append(seg)

print(f"Trip segments (Jun 16-24): {len(trip_segs)}", flush=True)

# Build route-only JSON (same structure as timeline_trip.json)
out = {"semanticSegments": trip_segs}
with open("timeline_trip.json", "w", encoding="utf-8") as f:
    json.dump(out, f)
print("Wrote timeline_trip.json", flush=True)

# Also write a flat CSV of GPS points with timestamps for catalog lookup
pts = []
for seg in trip_segs:
    for pt in seg.get("timelinePath", []):
        ll = parse_latlng(pt.get("point", ""))
        t  = pt.get("time", "")
        if ll and t:
            pts.append({"lat": ll[0], "lon": ll[1], "time": t})

pts.sort(key=lambda p: p["time"])
with open("route_pts.json", "w", encoding="utf-8") as f:
    json.dump(pts, f)
print(f"Wrote route_pts.json ({len(pts)} points)", flush=True)
