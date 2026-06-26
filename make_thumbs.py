"""
Generate thumbnails for all numbered media files (001.jpg, 002.mp4, etc.)
Output: thumbs/001.jpg, thumbs/002.jpg, ...
Requires: Pillow  (pip install Pillow)
For .mp4 files, attempts to use ffmpeg to extract a frame; falls back to a placeholder.
"""
import os, sys, subprocess, glob
from pathlib import Path

try:
    from PIL import Image
except ImportError:
    sys.exit("Install Pillow first:  pip install Pillow")

THUMB_W = 180
THUMB_H = 135
QUALITY = 82

os.makedirs("thumbs", exist_ok=True)

media = sorted(glob.glob("[0-9][0-9][0-9].jpg") + glob.glob("[0-9][0-9][0-9].mp4"))
print(f"Found {len(media)} media files")

for src in media:
    stem = Path(src).stem          # "001"
    dst  = f"thumbs/{stem}.jpg"
    if os.path.exists(dst):
        print(f"  skip {dst}")
        continue

    ext = Path(src).suffix.lower()

    if ext == ".jpg":
        try:
            img = Image.open(src)
            img.thumbnail((THUMB_W, THUMB_H), Image.LANCZOS)
            img = img.convert("RGB")
            img.save(dst, "JPEG", quality=QUALITY)
            print(f"  {src} -> {dst}")
        except Exception as e:
            print(f"  ERROR {src}: {e}")

    elif ext == ".mp4":
        # Try ffmpeg: grab frame at 0.5s
        cmd = [
            "ffmpeg", "-y", "-ss", "0.5", "-i", src,
            "-vframes", "1", "-vf", f"scale={THUMB_W}:{THUMB_H}:force_original_aspect_ratio=decrease",
            dst, "-loglevel", "error"
        ]
        result = subprocess.run(cmd, capture_output=True)
        if result.returncode == 0 and os.path.exists(dst):
            print(f"  {src} -> {dst} (ffmpeg)")
        else:
            # Placeholder: dark grey square with ▶
            img = Image.new("RGB", (THUMB_W, THUMB_H), (26, 18, 8))
            img.save(dst, "JPEG", quality=QUALITY)
            print(f"  {src} -> {dst} (placeholder)")

print("Done.")
